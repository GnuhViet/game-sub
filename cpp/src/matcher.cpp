#include "matcher.h"
#include "textnorm.h"
#include <algorithm>
#include <rapidfuzz_amalgamated.hpp>

using namespace textnorm;

static std::u16string u16(const QString& s) { return std::u16string(reinterpret_cast<const char16_t*>(s.utf16()), size_t(s.size())); }

int SubIndex::build(const QList<QPair<QString, QString>>& pairs, const QString& gender, const QStringList& nameTokens, const QString& playerName) {
    player_ = playerName; exact_.clear(); items_.clear();
    for (const auto& [src, vi] : pairs) {
        const QString k = norm(resolve(src, gender, nameTokens, {}, true));
        if (k.isEmpty()) continue;
        const QString v = resolve(vi, gender, nameTokens, playerName);
        exact_.insert(k, {v, src});                                  // bản import sau ghi đè
        items_.push_back({int(k.size()), {}, v, src, u16(k)});
    }
    std::stable_sort(items_.begin(), items_.end(), [](const Item& a, const Item& b) { return a.len < b.len; });
    lens_.clear(); lens_.reserve(items_.size());
    for (const Item& it : items_) lens_.push_back(it.len);
    return size();
}

std::optional<SubMatch> SubIndex::one(const QString& q, double th) const {
    if (q.isEmpty()) return std::nullopt;
    if (auto it = exact_.constFind(q); it != exact_.cend()) return SubMatch{it->first, 100.0, it->second};
    const auto lo = std::lower_bound(lens_.begin(), lens_.end(), int(q.size() * 0.7)) - lens_.begin();
    const auto hi = std::upper_bound(lens_.begin(), lens_.end(), int(q.size() * 1.3) + 2) - lens_.begin();
    if (lo >= hi) return std::nullopt;
    const std::u16string qq = u16(q);
    rapidfuzz::fuzz::CachedRatio<char16_t> scorer(qq.begin(), qq.end());
    double best = -1; qsizetype bi = -1;
    for (auto i = lo; i < hi; ++i) {
        const double s = scorer.similarity(items_[i].k16.begin(), items_[i].k16.end(), th);
        if (s >= th && s > best) { best = s; bi = i; if (s >= 100) break; }
    }
    if (bi < 0) return std::nullopt;
    return SubMatch{items_[bi].vi, best, items_[bi].src};
}

std::optional<SubMatch> SubIndex::best(const QString& text, double th) const {
    // thử cả bản thay tên người chơi -> § và bản giữ nguyên (tên trùng chữ thường, vd "Rover")
    const QString a = ocrForMatch(text, player_), b = norm(text);
    auto m1 = one(a, th);
    if (b == a) return m1;
    auto m2 = one(b, th);
    if (m1 && m2) return m1->score >= m2->score ? m1 : m2;
    return m1 ? m1 : m2;
}

std::optional<SubMatch> SubIndex::match(const QString& text, double threshold) const {
    if (items_.empty()) return std::nullopt;
    if (auto m = best(text, threshold)) return m;
    const QStringList sents = splitSentences(text);                 // màn hình gộp nhiều câu sub
    if (sents.size() > 1) {
        QStringList vi, src; double score = 100;
        for (const QString& s : sents) {
            auto p = best(s, threshold);
            if (!p) return std::nullopt;
            vi << p->vi; src << p->src; score = std::min(score, p->score);
        }
        return SubMatch{vi.join(' '), score, src.join(' ')};
    }
    return std::nullopt;
}
