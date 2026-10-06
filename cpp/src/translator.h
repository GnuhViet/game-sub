#pragma once
// Dịch máy: Gemini (AI) / Google free, bất đồng bộ. Mỗi mục đích (thoại, vùng chụp) chọn engine riêng; fallback + cooldown khi 429
// (giống translator.py). Kết quả trả qua callback ở luồng chính.
#include <QHash>
#include <QJsonObject>
#include <QUrl>
#include <QList>
#include <QString>
#include <QStringList>
#include <functional>

class Config;
class DB;

struct CtxLine { QString speaker, src, vi; };
struct TrResult { QString vi, provider, note; };
using StrFn = std::function<void(const QString&)>;

class Translator {
public:
    Translator(Config& cfg, DB* db) : cfg_(cfg), db_(db) {}
    void translate(const QString& text, const QString& speaker, const QList<CtxLine>& ctx, StrFn partial,
                   std::function<void(const TrResult&)> done, StrFn err, const QString& engine = {});
    void explain(const QString& word, const QString& sentence, StrFn done, StrFn err);
    void google(const QString& text, StrFn done, StrFn err);
    void gemini(const QString& system, const QString& user, StrFn partial, StrFn done, StrFn err, const QByteArray& png = {}, int maxTokens = 1024);
    void readImage(const QByteArray& png, StrFn partial, std::function<void(const QString& src, const QString& vi)> done, StrFn err);
    void listModels(const QString& key, std::function<void(const QStringList&)> done, StrFn err);
    static QString pickModel(const QStringList& names);
    QString label(const QString& provider) const;

    QString systemPrompt(const QString& text);
    QString userPrompt(const QString& text, const QString& speaker, const QList<CtxLine>& ctx) const;

private:
    void chain(const QStringList& names, int i, QStringList errs, const QString& text, const QString& speaker, const QList<CtxLine>& ctx,
               StrFn partial, std::function<void(const TrResult&)> done, StrFn err);
    QString glossaryBlock(const QString& text);
    bool cooling(const QString& name) const;
    QString checkError(const QString& name, int status, const QByteArray& body);     // "" nếu không lỗi
    void geminiSend(const QUrl& u, const QList<QPair<QByteArray, QByteArray>>& hdr, const QJsonObject& body, bool stream,
                    StrFn partial, StrFn done, StrFn err, bool retried);

    Config& cfg_;
    DB* db_;
    QHash<QString, qint64> cool_;          // nhà cung cấp -> hết nghỉ lúc (ms)
};

// Google Translate free (gtx), bị chặn 429 thì thử endpoint dict-chrome-ex; dùng chung cho tra từ
void googleFree(const QString& text, const QString& tl, int timeoutS, QHash<QString, qint64>* cool, StrFn done, StrFn err);
