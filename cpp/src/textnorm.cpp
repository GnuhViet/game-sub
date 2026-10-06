#include "textnorm.h"
#include <QSet>

namespace textnorm {
const QString WILD = QString::fromUtf8("§");

namespace {
using RO = QRegularExpression;
RO mk(const QString& pat, RO::PatternOptions o = RO::NoPatternOption) {
    RO r(pat, o | RO::UseUnicodePropertiesOption); r.optimize(); return r;
}
const RO TAG_RE = mk(R"(</?[A-Za-z][^<>]{0,60}>)");
const RO GENDER_RE = mk(R"(\{\s*(?:Male|M)\s*=\s*([^;{}]*?)\s*;\s*(?:Female|F)\s*=\s*([^{}]*?)\s*\})", RO::CaseInsensitiveOption);
const RO PH_RE = mk(R"(\{[^{}]{0,40}\}|%[sdf]|\{\d+\})");
const RO NON_WORD = mk(QString::fromUtf8(R"([^\w§]+)"));
const RO SPACES = mk(R"(\s+)");
const RO PARA_END = mk(QString::fromUtf8(R"([.!?:;,"'”’)…]$)"));
const RO SENT_RE = mk(QString::fromUtf8(R"((?<=[.!?…])\s+(?=["'A-Z“]))"));

QString quotes(QString t) {
    static const QList<QPair<QString, QString>> m = {
        {QString::fromUtf8("‘"), "'"}, {QString::fromUtf8("’"), "'"}, {QString::fromUtf8("‚"), "'"}, {QString::fromUtf8("“"), "\""},
        {QString::fromUtf8("”"), "\""}, {QString::fromUtf8("„"), "\""}, {QString::fromUtf8("…"), "..."}, {QString::fromUtf8("—"), "-"},
        {QString::fromUtf8("–"), "-"}, {QString::fromUtf8("｜"), "|"}};
    for (const auto& [a, b] : m) t.replace(a, b);
    return t;
}
}  // namespace

const QRegularExpression& wordRe() {
    static const RO r = mk(R"([A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z])");
    return r;
}

QString resolve(const QString& text, const QString& gender, const QStringList& nameTokens, const QString& playerName, bool forMatch) {
    if (text.isEmpty()) return {};
    QString t = text; t.remove(TAG_RE); t.replace("\\n", " ");
    QString out; qsizetype last = 0;                          // macro giới tính {Male=he;Female=she}
    for (auto it = GENDER_RE.globalMatch(t); it.hasNext();) {
        auto m = it.next();
        out += t.mid(last, m.capturedStart() - last) + (gender == "male" ? m.captured(1) : m.captured(2));
        last = m.capturedEnd();
    }
    t = out + t.mid(last);
    for (const QString& tok : nameTokens)
        if (!tok.isEmpty()) t.replace(tok, forMatch ? WILD : (playerName.isEmpty() ? tok : playerName));
    if (forMatch) t.replace(PH_RE, WILD);
    return t;
}

QString norm(const QString& text) {
    QString t = quotes(text.normalized(QString::NormalizationForm_KC)).toLower();
    t.replace(NON_WORD, " ");
    return t.replace(SPACES, " ").trimmed();
}

QString ocrForMatch(const QString& text, const QString& playerName) {
    QString t = text;
    if (playerName.size() > 1)
        t.replace(mk("(?<!\\w)" + RO::escape(playerName) + "(?!\\w)", RO::CaseInsensitiveOption), WILD);
    return norm(t);
}

QString joinLines(const QStringList& lines) {
    QString out;
    for (QString l : lines) {
        l = l.trimmed();
        if (l.isEmpty()) continue;
        if (out.endsWith('-') && l[0].isLower()) out = out.chopped(1) + l;
        else out = out.isEmpty() ? l : out + " " + l;
    }
    return out.replace(SPACES, " ").trimmed();
}

QString paragraphs(const QStringList& lines) {
    QStringList ls;
    for (const QString& l : lines) if (!l.trimmed().isEmpty()) ls << l.trimmed();
    if (ls.isEmpty()) return {};
    qsizetype full = 0; for (const QString& l : ls) full = std::max(full, l.size());
    QStringList paras, cur;
    for (const QString& l : ls) {
        cur << l;
        if (PARA_END.match(l).hasMatch() && l.size() < 0.75 * full) { paras << joinLines(cur); cur.clear(); }
    }
    if (!cur.isEmpty()) paras << joinLines(cur);
    return paras.join('\n');
}

QStringList splitSentences(const QString& text) {
    QStringList out;
    for (const QString& s : text.split(SENT_RE)) if (!s.trimmed().isEmpty()) out << s;
    return out;
}

QStringList lemmas(const QString& word) {
    QString w = word.toLower();
    while (!w.isEmpty() && (w.front() == '\'' || w.front() == '-')) w.remove(0, 1);
    while (!w.isEmpty() && (w.back() == '\'' || w.back() == '-')) w.chop(1);
    QStringList c{word, w}; const auto n = w.size();
    auto ends = [&](const char* s) { return w.endsWith(QLatin1String(s)); };
    if (ends("'s")) c << w.chopped(2);
    if (ends("ies") && n > 4) c << w.chopped(3) + "y";
    if (ends("es") && n > 3) c << w.chopped(2);
    if (ends("s") && !ends("ss") && n > 3) c << w.chopped(1);
    if (ends("ied") && n > 4) c << w.chopped(3) + "y";
    if (ends("ed") && n > 3) { c << w.chopped(2) << w.chopped(1); if (n > 4 && w[n - 3] == w[n - 4]) c << w.chopped(3); }
    if (ends("ing") && n > 4) { c << w.chopped(3) << w.chopped(3) + "e"; if (w[n - 4] == w[n - 5]) c << w.chopped(4); }
    if (ends("ly") && n > 4) c << w.chopped(2);
    if (ends("er") && n > 4) c << w.chopped(2);
    if (ends("est") && n > 5) c << w.chopped(3);
    QStringList out; QSet<QString> seen;
    for (const QString& x : c) if (!x.isEmpty() && !seen.contains(x)) { seen.insert(x); out << x; }
    return out;
}
}  // namespace textnorm
