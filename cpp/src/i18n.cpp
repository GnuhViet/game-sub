#include "i18n.h"
#include <QDir>
#include <QFile>
#include <QHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocale>

namespace {
const QString BASE = "vi";
QString g_dir, g_lang = BASE;
QHash<QString, QString> g_base, g_table;
QList<QPair<QString, QString>> g_langs;

QHash<QString, QString> read(const QString& code) {
    QHash<QString, QString> out;
    QFile f(g_dir + "/" + code + ".json");
    if (!f.open(QIODevice::ReadOnly)) return out;
    const QJsonObject o = QJsonDocument::fromJson(f.readAll()).object();
    for (auto it = o.begin(); it != o.end(); ++it) out.insert(it.key(), it.value().toString());
    return out;
}

QString format(QString s, TxArgs args) {
    if (args.size() == 0 && !s.contains("{{") && !s.contains("}}")) return s;
    QString out; out.reserve(s.size() + 16);
    for (qsizetype i = 0; i < s.size(); ++i) {
        const QChar c = s[i];
        if (c == '{' && i + 1 < s.size() && s[i + 1] == '{') { out += '{'; ++i; continue; }
        if (c == '}' && i + 1 < s.size() && s[i + 1] == '}') { out += '}'; ++i; continue; }
        if (c == '{') {
            const qsizetype j = s.indexOf('}', i);
            if (j > i) {
                const QString name = s.mid(i + 1, j - i - 1); bool hit = false;
                for (const auto& [k, v] : args) if (name == QLatin1String(k)) { out += v; hit = true; break; }
                if (hit) { i = j; continue; }
            }
        }
        out += c;
    }
    return out;
}
}  // namespace

namespace i18n {
void init(const QString& localesDir) {
    g_dir = localesDir; g_base = read(BASE); g_langs.clear();
    g_langs.append({BASE, g_base.value("_name", BASE)});
    for (const QString& fn : QDir(localesDir).entryList({"*.json"}, QDir::Files, QDir::Name)) {
        const QString code = fn.chopped(5);
        if (code != BASE) g_langs.append({code, read(code).value("_name", code)});
    }
}
QList<QPair<QString, QString>> langs() { return g_langs; }
QString systemLang() {
    const QString code = QLocale::system().name().section('_', 0, 0);
    bool has = false, en = false;
    for (const auto& l : g_langs) { has |= l.first == code; en |= l.first == "en"; }
    return has ? code : (en ? "en" : BASE);
}
void setLang(const QString& code) {
    bool has = false;
    for (const auto& l : g_langs) has |= l.first == code;
    g_lang = has ? code : systemLang();
    g_table = g_lang == BASE ? QHash<QString, QString>() : read(g_lang);
}
QString lang() { return g_lang; }
}  // namespace i18n

QString tx(const QString& key, TxArgs args) {
    QString s = g_table.value(key);
    if (s.isEmpty()) s = g_base.value(key);
    if (s.isEmpty()) s = key;
    return format(s, args);
}
QString tx(const char* key, TxArgs args) { return tx(QString::fromUtf8(key), args); }
