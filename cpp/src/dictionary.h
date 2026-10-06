#pragma once
// Từ điển offline (StarDict / TSV / CSV / JSON) + tra online (Google dịch, dictionaryapi.dev Anh-Anh) — giống dictionary.py.
#include <QByteArray>
#include <QHash>
#include <QList>
#include <QPair>
#include <QString>
#include <QStringList>
#include <functional>
#include <memory>
#include <optional>

class BaseDict {
public:
    virtual ~BaseDict() = default;
    QString name;
    virtual std::optional<QString> get(const QString& w) const = 0;
};

class Dictionaries {
public:
    void load(const QStringList& files);
    std::optional<QPair<QString, QString>> lookup(const QString& word) const;    // (từ gốc tìm thấy, html)
    bool empty() const { return dicts_.empty(); }
    QStringList errors;
private:
    std::vector<std::unique_ptr<BaseDict>> dicts_;
};

// ngôn ngữ đích Google dịch: (mã, key tên ngôn ngữ) — tên hiện bằng chữ Latin (tên bản địa bắt Qt nạp font CJK/Thái ~45 MB RAM)
const QList<QPair<QString, QString>>& targetLangs();

using LookupDone = std::function<void(std::optional<QPair<QString, QString>>)>;   // (nghĩa chính / từ, html) hoặc không có
void googleLookup(const QString& word, const QString& tl, int timeoutS, LookupDone done, std::function<void(const QString&)> err);
void onlineLookup(const QString& word, int timeoutS, LookupDone done, std::function<void(const QString&)> err);
QByteArray gunzip(const QByteArray& gz);
