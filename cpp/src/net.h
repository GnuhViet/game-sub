#pragma once
// HTTP bất đồng bộ (QNetworkAccessManager dùng chung, TLS qua Schannel của Windows). Chỉ gọi từ luồng chính.
#include <QByteArray>
#include <QList>
#include <QPair>
#include <QString>
#include <QUrl>
#include <functional>

class QNetworkAccessManager;

namespace net {
struct Response { int status = 0; QByteArray body; QString error; };     // status 0 = lỗi mạng (error = mô tả)
using Done = std::function<void(const Response&)>;
using Chunk = std::function<void(const QByteArray& data, int status)>;   // dữ liệu tới dần (stream)

QNetworkAccessManager& nam();
QUrl url(const QString& base, const QList<QPair<QString, QString>>& query);
void get(const QUrl& u, int timeoutS, Done done, const QList<QPair<QByteArray, QByteArray>>& headers = {});
void post(const QUrl& u, const QByteArray& body, int timeoutS, Done done, const QList<QPair<QByteArray, QByteArray>>& headers = {}, Chunk chunk = {});
}
