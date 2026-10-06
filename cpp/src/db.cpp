#include "db.h"
#include <QDateTime>
#include <QFile>
#include <QRegularExpression>
#include <QSqlError>
#include <QSqlQuery>
#include <QVariant>

static const char* SCHEMA[] = {
    "CREATE TABLE IF NOT EXISTS subs(id INTEGER PRIMARY KEY, file TEXT, src TEXT NOT NULL, vi TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS ix_subs_file ON subs(file)",
    "CREATE TABLE IF NOT EXISTS glossary(term TEXT PRIMARY KEY COLLATE NOCASE, vi TEXT DEFAULT '', mode TEXT DEFAULT 'keep', note TEXT DEFAULT '')",
    "CREATE TABLE IF NOT EXISTS vocab(word TEXT PRIMARY KEY COLLATE NOCASE, meaning TEXT DEFAULT '', sentence TEXT DEFAULT '', "
    "sentence_vi TEXT DEFAULT '', added TEXT, reviews INTEGER DEFAULT 0, last_review TEXT)",
    "CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, v TEXT)",
};

static QString now() { return QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm"); }

QString migrateDb(const QString& dir) {
    const QString nw = dir + "/gamesub.db", old = dir + "/wuwasub.db";
    if (QFile::exists(nw) || !QFile::exists(old)) return nw;
    if (!QFile::rename(old, nw)) return old;                       // bản cũ đang mở -> dùng tạm file cũ
    for (const char* suf : {"-wal", "-shm"})
        if (QFile::exists(old + suf)) QFile::rename(old + suf, nw + suf);
    return nw;
}

DB::DB(const QString& path) {
    db_ = QSqlDatabase::addDatabase("QSQLITE", "main");
    db_.setDatabaseName(path);
    if (!db_.open()) { qWarning("DB: %s", qPrintable(db_.lastError().text())); return; }
    QSqlQuery q(db_);
    q.exec("PRAGMA journal_mode=WAL"); q.exec("PRAGMA synchronous=NORMAL");      // ít fsync khi lưu cache tra từ
    for (const char* s : SCHEMA) q.exec(s);
}

void DB::addSubs(const QString& file, const QList<QPair<QString, QString>>& pairs) {
    db_.transaction();
    QSqlQuery q(db_); q.prepare("DELETE FROM subs WHERE file=?"); q.addBindValue(file); q.exec();
    q.prepare("INSERT INTO subs(file,src,vi) VALUES(?,?,?)");
    for (const auto& [s, v] : pairs) { q.addBindValue(file); q.addBindValue(s); q.addBindValue(v); q.exec(); }
    db_.commit();
}

QList<QPair<QString, int>> DB::subFiles() {
    QList<QPair<QString, int>> out; QSqlQuery q("SELECT file, COUNT(*) FROM subs GROUP BY file ORDER BY MIN(id)", db_);
    while (q.next()) out.append({q.value(0).toString(), q.value(1).toInt()});
    return out;
}
void DB::delSubFile(const QString& file) { QSqlQuery q(db_); q.prepare("DELETE FROM subs WHERE file=?"); q.addBindValue(file); q.exec(); }
QList<QPair<QString, QString>> DB::allSubs() {
    QList<QPair<QString, QString>> out; QSqlQuery q("SELECT src, vi FROM subs ORDER BY id", db_);
    while (q.next()) out.append({q.value(0).toString(), q.value(1).toString()});
    return out;
}

const QList<Term>& DB::glossary() {
    if (!gl_) {
        gl_.emplace(); QSqlQuery q("SELECT term,vi,mode,note FROM glossary ORDER BY length(term) DESC", db_);
        while (q.next()) gl_->append({q.value(0).toString(), q.value(1).toString(), q.value(2).toString(), q.value(3).toString()});
    }
    return *gl_;
}
void DB::setTerm(const QString& term, const QString& vi, const QString& mode, const QString& note) {
    QSqlQuery q(db_); q.prepare("INSERT OR REPLACE INTO glossary(term,vi,mode,note) VALUES(?,?,?,?)");
    q.addBindValue(term.trimmed()); q.addBindValue(vi.trimmed()); q.addBindValue(mode); q.addBindValue(note); q.exec();
    gl_.reset();
}
void DB::delTerm(const QString& term) { QSqlQuery q(db_); q.prepare("DELETE FROM glossary WHERE term=?"); q.addBindValue(term); q.exec(); gl_.reset(); }

QList<Term> DB::termsIn(const QString& text) {
    QList<Term> out;                      // khớp nguyên từ, không phân biệt hoa thường
    for (const Term& g : glossary()) {
        QRegularExpression re("(?<!\\w)" + QRegularExpression::escape(g.term) + "(?!\\w)",
                              QRegularExpression::CaseInsensitiveOption | QRegularExpression::UseUnicodePropertiesOption);
        if (re.match(text).hasMatch()) out.append(g);
    }
    return out;
}

void DB::addVocab(const QString& word, const QString& meaning, const QString& sentence, const QString& sentenceVi) {
    QSqlQuery q(db_);
    q.prepare("INSERT INTO vocab(word,meaning,sentence,sentence_vi,added) VALUES(?,?,?,?,?) "
              "ON CONFLICT(word) DO UPDATE SET meaning=COALESCE(NULLIF(excluded.meaning,''),meaning), "
              "sentence=COALESCE(NULLIF(excluded.sentence,''),sentence), sentence_vi=COALESCE(NULLIF(excluded.sentence_vi,''),sentence_vi)");
    q.addBindValue(word.trimmed()); q.addBindValue(meaning); q.addBindValue(sentence); q.addBindValue(sentenceVi); q.addBindValue(now()); q.exec();
}
QList<VocabRow> DB::vocab() {
    QList<VocabRow> out; QSqlQuery q("SELECT word,meaning,sentence,sentence_vi,added,reviews FROM vocab ORDER BY added DESC", db_);
    while (q.next()) out.append({q.value(0).toString(), q.value(1).toString(), q.value(2).toString(), q.value(3).toString(), q.value(4).toString(), q.value(5).toInt()});
    return out;
}
bool DB::hasVocab(const QString& word) { QSqlQuery q(db_); q.prepare("SELECT 1 FROM vocab WHERE word=?"); q.addBindValue(word); q.exec(); return q.next(); }
void DB::delVocab(const QString& word) { QSqlQuery q(db_); q.prepare("DELETE FROM vocab WHERE word=?"); q.addBindValue(word); q.exec(); }
void DB::reviewed(const QString& word) {
    QSqlQuery q(db_); q.prepare("UPDATE vocab SET reviews=reviews+1, last_review=? WHERE word=?"); q.addBindValue(now()); q.addBindValue(word); q.exec();
}

std::optional<QString> DB::cacheGet(const QString& k) {
    QSqlQuery q(db_); q.prepare("SELECT v FROM cache WHERE k=?"); q.addBindValue(k); q.exec();
    if (q.next()) return q.value(0).toString();
    return std::nullopt;
}
void DB::cacheSet(const QString& k, const QString& v) {
    QSqlQuery q(db_); q.prepare("INSERT OR REPLACE INTO cache(k,v) VALUES(?,?)"); q.addBindValue(k); q.addBindValue(v); q.exec();
}

// ---- CSV (RFC 4180: ngoặc kép, xuống dòng trong ô)
QList<QStringList> parseCsv(const QString& text, QChar delim) {
    QList<QStringList> rows; QStringList row; QString cell; bool quoted = false;
    for (qsizetype i = 0; i < text.size(); ++i) {
        const QChar c = text[i];
        if (quoted) {
            if (c == '"') { if (i + 1 < text.size() && text[i + 1] == '"') { cell += '"'; ++i; } else quoted = false; }
            else cell += c;
        } else if (c == '"') quoted = true;
        else if (c == delim) { row << cell; cell.clear(); }
        else if (c == '\n' || c == '\r') {
            if (c == '\r' && i + 1 < text.size() && text[i + 1] == '\n') ++i;
            row << cell; cell.clear(); rows << row; row.clear();
        } else cell += c;
    }
    if (!cell.isEmpty() || !row.isEmpty()) { row << cell; rows << row; }
    return rows;
}

QString csvLine(const QStringList& cells) {
    QStringList out;
    for (QString c : cells) {
        if (c.contains(',') || c.contains('"') || c.contains('\n') || c.contains('\r')) c = '"' + c.replace("\"", "\"\"") + '"';
        out << c;
    }
    return out.join(',') + "\r\n";
}

bool DB::exportCsv(const QString& table, const QString& path) {
    const QString cols = table == "glossary" ? "term,vi,mode,note" : "word,meaning,sentence,sentence_vi,added,reviews";
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly)) return false;
    f.write("\xEF\xBB\xBF");                                        // utf-8-sig cho Excel
    f.write(csvLine(cols.split(',')).toUtf8());
    QSqlQuery q("SELECT " + cols + " FROM " + table, db_);
    const int n = int(cols.count(',')) + 1;
    while (q.next()) { QStringList r; for (int i = 0; i < n; ++i) r << q.value(i).toString(); f.write(csvLine(r).toUtf8()); }
    return true;
}

int DB::importGlossaryCsv(const QString& path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) return 0;
    QString text = QString::fromUtf8(f.readAll());
    if (text.startsWith(QChar(0xFEFF))) text.remove(0, 1);
    const auto rows = parseCsv(text);
    if (rows.isEmpty()) return 0;
    const QStringList hdr = rows[0]; int n = 0;
    auto col = [&](const QStringList& r, const char* name) { const int i = int(hdr.indexOf(name)); return i >= 0 && i < r.size() ? r[i] : QString(); };
    for (int i = 1; i < rows.size(); ++i) {
        const QString t = col(rows[i], "term").trimmed();
        if (t.isEmpty()) continue;
        const QString vi = col(rows[i], "vi"); QString mode = col(rows[i], "mode");
        if (mode.isEmpty()) mode = vi.isEmpty() ? "keep" : "translate";
        setTerm(t, vi, mode, col(rows[i], "note")); ++n;
    }
    return n;
}
