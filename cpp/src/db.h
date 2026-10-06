#pragma once
// SQLite data/gamesub.db — cùng schema với bản Python (subs, glossary, vocab, cache). Chỉ dùng ở luồng chính.
#include <QList>
#include <QPair>
#include <QSqlDatabase>
#include <QString>
#include <QStringList>
#include <optional>

struct Term { QString term, vi, mode, note; };
struct VocabRow { QString word, meaning, sentence, sentenceVi, added; int reviews = 0; };

class DB {
public:
    explicit DB(const QString& path);
    // subs
    void addSubs(const QString& file, const QList<QPair<QString, QString>>& pairs);
    QList<QPair<QString, int>> subFiles();
    void delSubFile(const QString& file);
    QList<QPair<QString, QString>> allSubs();
    // glossary
    const QList<Term>& glossary();
    void setTerm(const QString& term, const QString& vi = {}, const QString& mode = "keep", const QString& note = {});
    void delTerm(const QString& term);
    QList<Term> termsIn(const QString& text);
    // vocab
    void addVocab(const QString& word, const QString& meaning, const QString& sentence, const QString& sentenceVi);
    QList<VocabRow> vocab();
    bool hasVocab(const QString& word);
    void delVocab(const QString& word);
    void reviewed(const QString& word);
    // cache (tra từ / dịch)
    std::optional<QString> cacheGet(const QString& k);
    void cacheSet(const QString& k, const QString& v);
    // CSV
    bool exportCsv(const QString& table, const QString& path);
    int importGlossaryCsv(const QString& path);

private:
    QSqlDatabase db_;
    std::optional<QList<Term>> gl_;
};

QString migrateDb(const QString& dataDir);    // wuwasub.db (bản cũ) -> gamesub.db; -> đường dẫn db
QList<QStringList> parseCsv(const QString& text, QChar delim = ',');
QString csvLine(const QStringList& cells);
