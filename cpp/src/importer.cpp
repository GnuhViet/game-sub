#include "importer.h"
#include "db.h"
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMap>
#include <QRegularExpression>
#include <QSet>
#include <QXmlStreamReader>
#include <QtCore/private/qzipreader_p.h>
#include <stdexcept>
#include <windows.h>

namespace importer {
namespace {
const QRegularExpression VI_CHARS(QString::fromUtf8("[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹáàãéèíìóòõúùýĂÂĐÊÔƠƯ]"));
const QStringList SRC_NAMES{"en", "eng", "english", "source", "src", "original", "goc", QString::fromUtf8("gốc"), "text_en", "en_us", "content"};
const QStringList VI_NAMES{"vi", "vn", "viet", "vietnamese", QString::fromUtf8("tiếng việt"), "dich", QString::fromUtf8("dịch"), "translation",
                           "target", "text_vi", "vi_vn"};

QString decode(const QByteArray& raw) {
    if (raw.startsWith("\xFF\xFE")) return QString::fromUtf16(reinterpret_cast<const char16_t*>(raw.constData() + 2), (raw.size() - 2) / 2);
    if (raw.startsWith("\xFE\xFF")) {
        QByteArray sw = raw.mid(2); for (qsizetype i = 0; i + 1 < sw.size(); i += 2) std::swap(sw[i], sw[i + 1]);
        return QString::fromUtf16(reinterpret_cast<const char16_t*>(sw.constData()), sw.size() / 2);
    }
    QByteArray b = raw.startsWith("\xEF\xBB\xBF") ? raw.mid(3) : raw;
    auto dec = QStringDecoder(QStringDecoder::Utf8, QStringDecoder::Flag::Stateless);
    QString s = dec(b);
    if (!dec.hasError()) return s;
    const int n = MultiByteToWideChar(1258, MB_ERR_INVALID_CHARS, b.constData(), int(b.size()), nullptr, 0);    // cp1258 (tiếng Việt Windows)
    if (n > 0) {
        std::wstring w(size_t(n), L'\0'); MultiByteToWideChar(1258, 0, b.constData(), int(b.size()), w.data(), n);
        return QString::fromStdWString(w);
    }
    return QString::fromLatin1(b);
}

bool blank(const QStringList& r) { for (const QString& x : r) if (!x.trimmed().isEmpty()) return false; return true; }

Table withHeader(QList<QStringList> rows) {
    Table t;
    rows.removeIf(blank);
    if (rows.isEmpty()) return t;
    QStringList first; for (const QString& x : rows[0]) first << x.trimmed().toLower();
    bool named = false; for (const QString& n : SRC_NAMES + VI_NAMES) named |= first.contains(n);
    bool vi = false, shortCells = true;
    for (const QString& x : rows[0]) { vi |= VI_CHARS.match(x).hasMatch(); shortCells &= x.size() < 30; }
    QList<QStringList> body;
    if (named || (rows.size() > 1 && !vi && shortCells)) {
        for (int i = 0; i < rows[0].size(); ++i) t.hdr << (rows[0][i].trimmed().isEmpty() ? QString("col%1").arg(i + 1) : rows[0][i].trimmed());
        body = rows.mid(1);
    } else {
        qsizetype w = 0; for (const auto& r : rows) w = std::max(w, r.size());
        for (int i = 0; i < w; ++i) t.hdr << QString("col%1").arg(i + 1);
        body = rows;
    }
    for (QStringList r : body) { while (r.size() < t.hdr.size()) r << ""; t.rows << r.mid(0, t.hdr.size()); }
    return t;
}

QChar sniff(const QString& sample) {
    QChar best = ','; int bestScore = -1;
    const QStringList lines = sample.split('\n', Qt::SkipEmptyParts).mid(0, 50);
    for (QChar d : {QChar(','), QChar(';'), QChar('|')}) {
        QMap<int, int> freq;                                          // số lần xuất hiện mỗi dòng -> số dòng
        for (const QString& l : lines) if (int c = int(l.count(d))) freq[c]++;
        int score = 0; for (int v : freq) score = std::max(score, v);
        if (score > bestScore) { bestScore = score; best = d; }
    }
    return bestScore > 0 ? best : QChar(',');
}

QMap<QString, QString> flatten(const QJsonValue& v, const QString& prefix = {}) {
    QMap<QString, QString> out;
    if (v.isObject()) {
        const QJsonObject o = v.toObject();
        for (auto it = o.begin(); it != o.end(); ++it) {
            if (it->isObject() || it->isArray()) out.insert(flatten(*it, prefix + it.key() + "."));
            else out.insert(prefix + it.key(), it->isString() ? it->toString() : it->toVariant().toString());
        }
        return out;
    }
    QString k = prefix; if (k.endsWith('.')) k.chop(1);
    out.insert(k.isEmpty() ? "value" : k, v.isString() ? v.toString() : v.toVariant().toString());
    return out;
}

Table readJson(const QString& text) {
    const QJsonDocument doc = QJsonDocument::fromJson(text.toUtf8());
    QList<QMap<QString, QString>> recs; QStringList order;
    auto add = [&](const QMap<QString, QString>& r, const QStringList& keys) { recs << r; for (const QString& k : keys) if (!order.contains(k)) order << k; };
    if (doc.isObject()) {
        const QJsonObject o = doc.object(); bool allStr = !o.isEmpty();
        for (const auto& v : o) allStr &= v.isString();
        if (allStr) { Table t; t.hdr = {"key", "value"}; for (auto it = o.begin(); it != o.end(); ++it) t.rows << QStringList{it.key(), it->toString()}; return t; }
        for (auto it = o.begin(); it != o.end(); ++it) {
            QMap<QString, QString> r = it->isObject() ? flatten(*it) : QMap<QString, QString>{{"value", it->toVariant().toString()}};
            r.insert("_id", it.key());
            add(r, it->isObject() ? QStringList(flatten(*it).keys()) << "_id" : QStringList{"_id", "value"});
        }
    } else {
        const QJsonArray a = doc.array();
        if (!a.isEmpty() && a[0].isArray()) {
            QList<QStringList> rows;
            for (const auto& r : a) { QStringList row; for (const auto& x : r.toArray()) row << (x.isString() ? x.toString() : x.toVariant().toString()); rows << row; }
            return withHeader(rows);
        }
        for (const auto& r : a) { auto f = flatten(r); add(f, f.keys()); }
    }
    Table t; t.hdr = order;
    for (const auto& r : recs) { QStringList row; for (const QString& h : order) row << r.value(h); t.rows << row; }
    return t;
}

int colIndex(const QString& ref) {                                    // "BC12" -> 54
    int n = 0;
    for (QChar c : ref) { if (!c.isLetter()) break; n = n * 26 + (c.toUpper().unicode() - 'A' + 1); }
    return n - 1;
}

Table readXlsx(const QString& path) {
    QZipReader zip(path);
    if (!zip.isReadable()) throw std::runtime_error("xlsx");
    QStringList shared;
    { QXmlStreamReader x(zip.fileData("xl/sharedStrings.xml")); QString cur; bool inSi = false;
      while (!x.atEnd()) {
          x.readNext();
          if (x.isStartElement() && x.name() == u"si") { inSi = true; cur.clear(); }
          else if (x.isStartElement() && x.name() == u"t" && inSi) cur += x.readElementText();
          else if (x.isEndElement() && x.name() == u"si") { inSi = false; shared << cur; }
      } }
    QStringList sheets;
    for (const auto& fi : zip.fileInfoList())
        if (fi.filePath.startsWith("xl/worksheets/sheet") && fi.filePath.endsWith(".xml")) sheets << fi.filePath;
    std::sort(sheets.begin(), sheets.end(), [](const QString& a, const QString& b) {
        return a.mid(19).chopped(4).toInt() < b.mid(19).chopped(4).toInt(); });
    QList<QStringList> firstRows;
    for (const QString& sh : sheets) {
        QList<QStringList> rows; QXmlStreamReader x(zip.fileData(sh)); QStringList row; int col = 0; QString type, val;
        while (!x.atEnd()) {
            x.readNext();
            if (x.isStartElement() && x.name() == u"row") row.clear();
            else if (x.isStartElement() && x.name() == u"c") { col = colIndex(x.attributes().value("r").toString()); type = x.attributes().value("t").toString(); val.clear(); }
            else if (x.isStartElement() && (x.name() == u"v" || (x.name() == u"t" && type == "inlineStr"))) val += x.readElementText();
            else if (x.isEndElement() && x.name() == u"c") {
                if (type == "s") val = shared.value(val.toInt());
                else if (type == "b") val = val == "1" ? "True" : "False";
                while (row.size() <= col) row << "";
                row[col] = val;
            } else if (x.isEndElement() && x.name() == u"row") rows << row;
        }
        qsizetype w = 0; for (const auto& r : rows) w = std::max(w, r.size());
        for (auto& r : rows) while (r.size() < w) r << "";
        if (firstRows.isEmpty()) firstRows = rows;
        if (rows.size() > 1) return withHeader(rows);                // sheet đầu tiên có dữ liệu
    }
    return withHeader(firstRows);
}
}  // namespace

Table readTable(const QString& path) {
    const QString ext = QFileInfo(path).suffix().toLower();
    if (ext == "xlsx" || ext == "xlsm") return readXlsx(path);
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) throw std::runtime_error(f.errorString().toStdString());
    const QString text = decode(f.readAll());
    if (ext == "json") return readJson(text);
    const QString sample = text.left(20000);
    const QChar delim = (ext == "tsv" || sample.contains('\t')) ? QChar('\t') : sniff(sample);
    return withHeader(parseCsv(text, delim));
}

QPair<int, int> guessCols(const QStringList& hdr, const QList<QStringList>& rows) {
    QStringList low; for (const QString& h : hdr) low << h.toLower().section('.', -1);
    int src = -1, vi = -1;
    for (int i = 0; i < low.size(); ++i) { if (src < 0 && SRC_NAMES.contains(low[i])) src = i; if (vi < 0 && VI_NAMES.contains(low[i])) vi = i; }
    if (src >= 0 && vi >= 0 && src != vi) return {src, vi};
    const auto sample = rows.mid(0, 300); const int n = int(hdr.size());
    static const QRegularExpression two(R"([A-Za-z]{2})");
    QList<double> viR, asR;
    for (int i = 0; i < n; ++i) {
        int v = 0, a = 0;
        for (const auto& r : sample) {
            const QString c = r.value(i);
            v += VI_CHARS.match(c).hasMatch();
            bool ascii = true; for (QChar ch : c) ascii &= ch.unicode() < 128;
            a += !c.trimmed().isEmpty() && ascii && two.match(c).hasMatch();
        }
        viR << double(v) / std::max<qsizetype>(1, sample.size()); asR << double(a) / std::max<qsizetype>(1, sample.size());
    }
    if (vi < 0) { vi = 0; for (int i = 1; i < n; ++i) if (viR[i] > viR[vi]) vi = i; }
    if (src < 0) { src = -1; for (int i = 0; i < n; ++i) if (i != vi && (src < 0 || asR[i] > asR[src])) src = i; if (src < 0) src = 0; }
    return {src, vi};
}

QList<QPair<QString, QString>> extractPairs(const QList<QStringList>& rows, int s, int v) {
    QList<QPair<QString, QString>> out;
    for (const auto& r : rows) {
        const QString a = r.value(s).trimmed(), b = r.value(v).trimmed();
        if (!a.isEmpty() && !b.isEmpty()) out.append({a, b});
    }
    return out;
}
}  // namespace importer
