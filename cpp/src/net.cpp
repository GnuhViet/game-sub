#include "net.h"
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrlQuery>

namespace net {
QNetworkAccessManager& nam() { static QNetworkAccessManager m; return m; }

QUrl url(const QString& base, const QList<QPair<QString, QString>>& query) {
    QUrl u(base); QUrlQuery q;
    for (const auto& [k, v] : query) q.addQueryItem(k, QString::fromLatin1(QUrl::toPercentEncoding(v)));
    u.setQuery(q.query(QUrl::FullyEncoded), QUrl::StrictMode);
    return u;
}

static QNetworkRequest request(const QUrl& u, int timeoutS, const QList<QPair<QByteArray, QByteArray>>& headers) {
    QNetworkRequest r(u);
    r.setTransferTimeout(timeoutS * 1000);
    r.setHeader(QNetworkRequest::UserAgentHeader, "Mozilla/5.0 GameSub");
    for (const auto& [k, v] : headers) r.setRawHeader(k, v);
    return r;
}

static void wire(QNetworkReply* rep, Done done, Chunk chunk) {
    if (chunk) QObject::connect(rep, &QNetworkReply::readyRead, rep, [rep, chunk] {
        chunk(rep->readAll(), rep->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt());
    });
    QObject::connect(rep, &QNetworkReply::finished, rep, [rep, done, chunk] {
        Response r; r.status = rep->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const QByteArray rest = rep->readAll();
        if (chunk && !rest.isEmpty()) chunk(rest, r.status);
        r.body = rest;
        if (r.status == 0) r.error = rep->error() == QNetworkReply::OperationCanceledError || rep->error() == QNetworkReply::TimeoutError
                                         ? QStringLiteral("Timeout") : rep->errorString();
        rep->deleteLater();
        done(r);
    });
}

void get(const QUrl& u, int timeoutS, Done done, const QList<QPair<QByteArray, QByteArray>>& headers) {
    wire(nam().get(request(u, timeoutS, headers)), std::move(done), {});
}

void post(const QUrl& u, const QByteArray& body, int timeoutS, Done done, const QList<QPair<QByteArray, QByteArray>>& headers, Chunk chunk) {
    QNetworkRequest r = request(u, timeoutS, headers);
    r.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    wire(nam().post(r, body), std::move(done), std::move(chunk));
}
}  // namespace net
