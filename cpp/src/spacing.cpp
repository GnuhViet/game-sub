#include "spacing.h"
#include <QFile>
#include <QRegularExpression>
#include <algorithm>
#include <cmath>
#include <limits>

namespace {
const double INF = std::numeric_limits<double>::infinity();
const double MAX_COST = 12.5;               // cost ~ log(hạng): <= 12.5 ≈ từ thông dụng
const QRegularExpression TOKEN_RE(R"([A-Za-z]{6,})");
const QRegularExpression PUNCT_RE(R"(([,!?;:]|(?<=[a-z])\.)(?=[A-Za-z]))");     // "Rover,you" -> "Rover, you"
}

void Spacer::setKnown(const QStringList& words) {
    known_.clear();
    for (const QString& w : words) if (!w.isEmpty()) known_.insert(w.toLower());
}

void Spacer::load() {
    if (loaded_) return;
    loaded_ = true;
    QFile f(":/words.qz");
    if (!f.open(QIODevice::ReadOnly)) return;
    buf_ = qUncompress(f.readAll());
    std::vector<std::string_view> list;
    const char* p = buf_.constData(); const char* end = p + buf_.size();
    while (p < end) {                                  // từ cách nhau bởi khoảng trắng, sắp theo tần suất giảm dần
        while (p < end && std::isspace(uchar(*p))) ++p;
        const char* s = p;
        while (p < end && !std::isspace(uchar(*p))) ++p;
        if (p > s) list.emplace_back(s, size_t(p - s));
    }
    const double logN = std::log(double(list.size()));
    words_.reserve(list.size());
    for (size_t i = 0; i < list.size(); ++i) {
        words_.emplace_back(list[i], std::log((i + 1) * logN));
        maxWord_ = std::max(maxWord_, list[i].size());
    }
    // từ trùng: wordninja (dict Python) giữ cost của lần xuất hiện sau cùng
    std::stable_sort(words_.begin(), words_.end(), [](auto& a, auto& b) { return a.first < b.first; });
    std::vector<std::pair<std::string_view, double>> uniq; uniq.reserve(words_.size());
    for (auto& w : words_) {
        if (!uniq.empty() && uniq.back().first == w.first) uniq.back() = w;
        else uniq.push_back(w);
    }
    words_.swap(uniq);
}

double Spacer::cost(std::string_view w) const {
    auto it = std::lower_bound(words_.begin(), words_.end(), w, [](auto& a, std::string_view b) { return a.first < b; });
    return it != words_.end() && it->first == w ? it->second : INF;
}

std::vector<std::string> Spacer::splitPart(const std::string& s) {
    const size_t n = s.size();
    std::vector<double> cost(n + 1, 0.0);
    std::string low = s; for (char& c : low) c = char(std::tolower(uchar(c)));
    auto best = [&](size_t i) {                        // (cost, độ dài từ cuối) nhỏ nhất, hòa thì từ ngắn hơn
        double bc = INF; size_t bk = 1;
        for (size_t k = 0; k < std::min(i, maxWord_); ++k) {
            const double c = cost[i - k - 1] + this->cost(std::string_view(low).substr(i - k - 1, k + 1));
            if (c < bc || (c == bc && k + 1 < bk)) { bc = c; bk = k + 1; }
        }
        return std::pair{bc, bk};
    };
    for (size_t i = 1; i <= n; ++i) cost[i] = best(i).first;
    std::vector<std::string> out;
    size_t i = n;
    while (i > 0) {
        const size_t k = best(i).second;
        const std::string tok = s.substr(i - k, k);
        bool fresh = true;
        if (tok != "'" && !out.empty()) {
            if (out.back() == "'s" || (std::isdigit(uchar(s[i - 1])) && std::isdigit(uchar(out.back()[0])))) {
                out.back() = tok + out.back(); fresh = false;         // gộp với token trước
            }
        }
        if (fresh) out.push_back(tok);
        i -= k;
    }
    std::reverse(out.begin(), out.end());
    return out;
}

std::vector<std::string> Spacer::split(const std::string& s) {
    load();
    std::vector<std::string> out; std::string cur;
    auto flush = [&] { for (auto& t : splitPart(cur)) out.push_back(t); cur.clear(); };
    for (char c : s) {
        if (std::isalnum(uchar(c)) || c == '\'') cur += c;
        else flush();
    }
    flush();
    return out;
}

QString Spacer::splitToken(const QString& tok) {
    const QString lo = tok.toLower(); const std::string l = lo.toStdString();
    if (cost(l) < INF || known_.contains(lo)) return tok;
    const auto parts = split(l);
    if (parts.size() < 2) return tok;
    for (const auto& p : parts) {
        if (p.size() == 1 && p != "a" && p != "i") return tok;
        if (cost(p) > MAX_COST) return tok;
    }
    if (tok[0].isUpper() && parts.size() < 3 && tok.size() < 10) return tok;     // nhiều khả năng là tên riêng
    QStringList out; qsizetype i = 0;
    for (const auto& p : parts) { out << tok.mid(i, qsizetype(p.size())); i += qsizetype(p.size()); }   // giữ hoa/thường gốc
    return out.join(' ');
}

QString Spacer::fix(const QString& text) {
    load();
    if (words_.empty()) return text;
    QString t = text; t.replace(PUNCT_RE, "\\1 ");
    QString out; qsizetype last = 0;
    for (auto it = TOKEN_RE.globalMatch(t); it.hasNext();) {
        auto m = it.next();
        out += t.mid(last, m.capturedStart() - last) + splitToken(m.captured());
        last = m.capturedEnd();
    }
    return out + t.mid(last);
}
