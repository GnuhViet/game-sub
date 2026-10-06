#include "dictionary.h"
#include "db.h"
#include "i18n.h"
#include "net.h"
#include "textnorm.h"
#include "translator.h"
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QtEndian>
#include <QtZlib/zlib.h>
#include <stdexcept>

QByteArray gunzip(const QByteArray& gz) {
    QByteArray out; z_stream s{};
    if (inflateInit2(&s, 16 + MAX_WBITS) != Z_OK) return {};
    s.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(gz.constData())); s.avail_in = uInt(gz.size());
    char buf[1 << 16]; int rc;
    do {
        s.next_out = reinterpret_cast<Bytef*>(buf); s.avail_out = sizeof buf;
        rc = inflate(&s, Z_NO_FLUSH);
        if (rc != Z_OK && rc != Z_STREAM_END) break;
        out.append(buf, qsizetype(sizeof buf - s.avail_out));
        if (rc == Z_STREAM_END && s.avail_in > 0) inflateReset(&s);      // .dz có thể gồm nhiều member gzip
    } while (s.avail_in > 0 || rc == Z_OK);
    inflateEnd(&s);
    return out;
}

static QByteArray readFile(const QString& p) { QFile f(p); return f.open(QIODevice::ReadOnly) ? f.readAll() : QByteArray(); }
static QString esc(const QString& s) { return s.toHtmlEscaped(); }

static QString fmt(QChar t, const QString& s) {
    if (t == 'h' || t == 'g') return s;
    if (t == 'x') { QString x = s; x.remove(QRegularExpression("<[^>]+>")); return x.replace("\n", "<br>"); }
    return esc(s).replace("\n", "<br>");
}

namespace {
class StarDict : public BaseDict {
public:
    explicit StarDict(const QString& ifo) {
        QHash<QString, QString> info;
        for (const QString& l : QString::fromUtf8(readFile(ifo)).split('\n')) if (l.contains('=')) info.insert(l.section('=', 0, 0).trimmed(), l.section('=', 1).trimmed());
        name = info.value("bookname", QFileInfo(ifo).completeBaseName()); sts_ = info.value("sametypesequence");
        const bool b64 = info.value("idxoffsetbits") == "64";
        const QString base = ifo.chopped(4);
        QByteArray raw;
        if (QFileInfo::exists(base + ".idx")) raw = readFile(base + ".idx");
        else if (QFileInfo::exists(base + ".idx.gz")) raw = gunzip(readFile(base + ".idx.gz"));
        else throw std::runtime_error(tx("dict.missing_idx_file_for_name", {{"name", QFileInfo(ifo).fileName()}}).toStdString());
        data_ = QFileInfo::exists(base + ".dict.dz") ? gunzip(readFile(base + ".dict.dz")) : readFile(base + ".dict");
        const int step = b64 ? 12 : 8; qsizetype i = 0;
        while (i < raw.size()) {
            const qsizetype j = raw.indexOf('\0', i);
            if (j < 0 || j + 1 + step > raw.size()) break;
            const QString w = QString::fromUtf8(raw.constData() + i, j - i).toLower();
            const uchar* p = reinterpret_cast<const uchar*>(raw.constData() + j + 1);
            const quint64 off = b64 ? qFromBigEndian<quint64>(p) : qFromBigEndian<quint32>(p);
            const quint32 size = qFromBigEndian<quint32>(p + (b64 ? 8 : 4));
            if (!index_.contains(w)) index_.insert(w, {off, size});
            i = j + 1 + step;
        }
    }
    std::optional<QString> get(const QString& w) const override {
        auto it = index_.constFind(w.toLower());
        if (it == index_.cend()) return std::nullopt;
        const QByteArray b = data_.mid(qsizetype(it->first), it->second);
        if (sts_.size() == 1) return fmt(sts_[0], QString::fromUtf8(b));
        QStringList out; qsizetype i = 0; QString types = sts_;               // nhiều field: (kiểu) + dữ liệu\0
        while (i < b.size()) {
            QChar t;
            if (!sts_.isEmpty()) { if (types.isEmpty()) break; t = types[0]; types.remove(0, 1); }
            else t = QChar(b[i++]);
            QByteArray seg;
            if (!sts_.isEmpty() && types.isEmpty()) { seg = b.mid(i); i = b.size(); }    // field cuối không có \0
            else { qsizetype j = b.indexOf('\0', i); if (j < 0) j = b.size(); seg = b.mid(i, j - i); i = j + 1; }
            const QString f = fmt(t, QString::fromUtf8(seg));
            if (!f.isEmpty()) out << f;
        }
        return out.join("<br>");
    }
private:
    QString sts_;
    QByteArray data_;
    QHash<QString, QPair<quint64, quint32>> index_;
};

class TableDict : public BaseDict {
public:
    explicit TableDict(const QString& p) {
        name = QFileInfo(p).completeBaseName();
        QString text = QString::fromUtf8(readFile(p));
        if (text.startsWith(QChar(0xFEFF))) text.remove(0, 1);
        auto add = [&](const QString& w, const QString& m) { const QString k = w.trimmed().toLower(); if (!k.isEmpty() && !m.isEmpty() && !index_.contains(k)) index_.insert(k, m); };
        if (QFileInfo(p).suffix().toLower() == "json") {
            const QJsonDocument d = QJsonDocument::fromJson(text.toUtf8());
            if (d.isObject()) for (auto it = d.object().begin(); it != d.object().end(); ++it) add(it.key(), it->toVariant().toString());
            else for (const auto& r : d.array()) add(r.toObject().value("word").toString(), r.toObject().value("meaning").toVariant().toString());
        } else {
            const QChar delim = text.left(5000).contains('\t') ? QChar('\t') : QChar(',');
            for (const QStringList& r : parseCsv(text, delim)) if (r.size() >= 2) add(r[0], r[1]);
        }
    }
    std::optional<QString> get(const QString& w) const override {
        auto it = index_.constFind(w.toLower());
        if (it == index_.cend()) return std::nullopt;
        return esc(*it).replace("\\n", "<br>").replace("\n", "<br>");
    }
private:
    QHash<QString, QString> index_;
};
}  // namespace

void Dictionaries::load(const QStringList& files) {
    dicts_.clear(); errors.clear();
    for (const QString& f : files) {
        try {
            if (QFileInfo(f).suffix().toLower() == "ifo") dicts_.push_back(std::make_unique<StarDict>(f));
            else dicts_.push_back(std::make_unique<TableDict>(f));
        } catch (const std::exception& e) { errors << QFileInfo(f).fileName() + ": " + QString::fromUtf8(e.what()); }
    }
}

std::optional<QPair<QString, QString>> Dictionaries::lookup(const QString& word) const {
    for (const QString& cand : textnorm::lemmas(word)) {
        QList<QPair<QString, QString>> parts;
        for (const auto& d : dicts_) if (auto m = d->get(cand)) parts.append({d->name, *m});
        if (parts.isEmpty()) continue;
        if (parts.size() == 1) return QPair<QString, QString>{cand, parts[0].second};
        QString body;
        for (const auto& [n, m] : parts) body += "<div style='margin-top:4px'><i style='opacity:.6'>" + esc(n) + "</i><br>" + m + "</div>";
        return QPair<QString, QString>{cand, body};
    }
    return std::nullopt;
}

const QList<QPair<QString, QString>>& targetLangs() {
    static const QList<QPair<QString, QString>> L{{"vi", N_("lang.vi")}, {"en", N_("lang.en")}, {"ja", N_("lang.ja")}, {"zh-CN", N_("lang.zh-CN")},
                                                  {"zh-TW", N_("lang.zh-TW")}, {"ko", N_("lang.ko")}, {"fr", N_("lang.fr")}, {"de", N_("lang.de")},
                                                  {"es", N_("lang.es")}, {"ru", N_("lang.ru")}, {"th", N_("lang.th")}, {"id", N_("lang.id")}};
    return L;
}

void googleLookup(const QString& word, const QString& tl, int timeoutS, LookupDone done, std::function<void(const QString&)> err) {
    // Google Translate (gtx, free): nghĩa chính + phiên âm + nghĩa theo từ loại
    net::get(net::url("https://translate.googleapis.com/translate_a/single",
                      {{"client", "gtx"}, {"sl", "auto"}, {"tl", tl}, {"dt", "t"}, {"dt", "bd"}, {"dt", "rm"}, {"q", word}}),
             timeoutS, [=](const net::Response& r) {
        if (r.status == 429) {                                       // bị chặn tạm -> endpoint dự phòng (chỉ có nghĩa chính)
            return googleFree(word, tl, timeoutS, nullptr, [=](const QString& main) {
                if (main.isEmpty()) return done(std::nullopt);
                done(QPair<QString, QString>{main, "<b style='font-size:15px'>" + esc(main) + "</b>"});
            }, err);
        }
        if (r.status != 200) return err(r.status ? QString("HTTP %1").arg(r.status) : r.error);
        const QJsonArray d = QJsonDocument::fromJson(r.body).array();
        QString main, ph;
        for (const auto& s : d.at(0).toArray()) {
            const QJsonArray a = s.toArray();
            if (a.at(0).isString()) main += a.at(0).toString();
            if (ph.isEmpty() && a.size() > 3 && a.at(3).isString()) ph = a.at(3).toString();
        }
        main = main.trimmed();
        if (main.isEmpty()) return done(std::nullopt);
        QStringList out{"<b style='font-size:15px'>" + esc(main) + "</b>" + (ph.isEmpty() ? "" : " &nbsp;<span style='opacity:.65'>/" + esc(ph) + "/</span>")};
        const QJsonArray pos = d.size() > 1 ? d.at(1).toArray() : QJsonArray();
        for (int i = 0; i < std::min<qsizetype>(4, pos.size()); ++i) {
            const QJsonArray p = pos.at(i).toArray(); QStringList ws;
            const QJsonArray w = p.at(1).toArray();
            for (int k = 0; k < std::min<qsizetype>(6, w.size()); ++k) ws << esc(w.at(k).toString());
            out << "<i>" + esc(p.at(0).toString()) + "</i>: " + ws.join(", ");
        }
        done(QPair<QString, QString>{main, out.join("<br>")});
    });
}

static void onlineAt(const QStringList& cands, int i, int timeoutS, LookupDone done) {
    if (i >= cands.size()) return done(std::nullopt);
    const QString cand = cands[i];
    net::get(QUrl("https://api.dictionaryapi.dev/api/v2/entries/en/" + QString::fromLatin1(QUrl::toPercentEncoding(cand))), timeoutS,
             [=](const net::Response& r) {
        if (r.status != 200) return onlineAt(cands, i + 1, timeoutS, done);
        const QJsonObject e = QJsonDocument::fromJson(r.body).array().at(0).toObject();
        QString ph = e.value("phonetic").toString();
        if (ph.isEmpty()) for (const auto& p : e.value("phonetics").toArray()) if (!p.toObject().value("text").toString().isEmpty()) { ph = p.toObject().value("text").toString(); break; }
        QStringList out{"<b>" + esc(e.value("word").toString(cand)) + "</b> " + esc(ph)};
        const QJsonArray ms = e.value("meanings").toArray();
        for (int k = 0; k < std::min<qsizetype>(3, ms.size()); ++k) {
            const QJsonObject m = ms.at(k).toObject(); out << "<i>" + esc(m.value("partOfSpeech").toString()) + "</i>";
            const QJsonArray ds = m.value("definitions").toArray();
            for (int j = 0; j < std::min<qsizetype>(2, ds.size()); ++j) {
                const QJsonObject d = ds.at(j).toObject(); const QString ex = d.value("example").toString();
                out << QString::fromUtf8("• ") + esc(d.value("definition").toString()) +
                           (ex.isEmpty() ? "" : "<br>&nbsp;&nbsp;<span style='opacity:.65'>e.g. " + esc(ex) + "</span>");
            }
        }
        done(QPair<QString, QString>{cand, out.join("<br>")});
    });
}

void onlineLookup(const QString& word, int timeoutS, LookupDone done, std::function<void(const QString&)>) {
    QStringList cands = textnorm::lemmas(word).mid(1, 2);
    if (cands.isEmpty()) cands = {word};
    onlineAt(cands, 0, timeoutS, done);
}
