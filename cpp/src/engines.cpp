#include "engines.h"
#include "config.h"
#include "i18n.h"
#include "net.h"
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QPointer>
#include <QRegularExpression>
#include <QThread>
#include <memory>
#include <windows.h>
#include <shellapi.h>

namespace engines {
QString dir() { return appDir() + "/engines"; }
QString tessDir() { return dir() + "/tesseract"; }
bool hasTesseract() { return QFile::exists(tessDir() + "/tesseract.exe"); }

double sizeMb(const QString& d) {
    qint64 n = 0;
    for (QDirIterator it(d, QDir::Files, QDirIterator::Subdirectories); it.hasNext();) { it.next(); n += it.fileInfo().size(); }
    return n / 1e6;
}

static bool runWait(const QString& exe, const QString& args) {
    // ShellExecuteEx để Windows tự hỏi UAC nếu bộ cài cần quyền admin, rồi chờ xong
    const std::wstring e = QDir::toNativeSeparators(exe).toStdWString(), a = args.toStdWString();
    SHELLEXECUTEINFOW sei{}; sei.cbSize = sizeof sei; sei.fMask = SEE_MASK_NOCLOSEPROCESS; sei.lpVerb = L"open";
    sei.lpFile = e.c_str(); sei.lpParameters = a.c_str(); sei.nShow = SW_HIDE;
    if (!ShellExecuteExW(&sei)) return false;
    WaitForSingleObject(sei.hProcess, INFINITE); CloseHandle(sei.hProcess);
    return true;
}

std::function<void()> installTesseract(std::function<void(const QString&, int)> progress, std::function<void(const QString&)> done) {
    auto cancelled = std::make_shared<bool>(false);
    auto reply = std::make_shared<QPointer<QNetworkReply>>();
    net::get(QUrl("https://api.github.com/repos/UB-Mannheim/tesseract/releases/latest"), 20, [=](const net::Response& r) {
        if (*cancelled) return done("cancel");
        if (r.status != 200) return done(r.status ? QString("HTTP %1").arg(r.status) : r.error);
        static const QRegularExpression re(R"(w64-setup.*\.exe$)");
        QJsonObject asset;
        for (const auto& a : QJsonDocument::fromJson(r.body).object().value("assets").toArray())
            if (re.match(a.toObject().value("name").toString()).hasMatch()) { asset = a.toObject(); break; }
        if (asset.isEmpty()) return done(tx("engines.couldnt_find_tesseract_installer_on"));
        QDir().mkpath(dir());
        const QString setup = dir() + "/" + asset.value("name").toString();
        QNetworkRequest req(QUrl(asset.value("browser_download_url").toString()));
        req.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
        QNetworkReply* rep = net::nam().get(req); *reply = rep;
        auto file = std::make_shared<QFile>(setup); file->open(QIODevice::WriteOnly);
        QObject::connect(rep, &QNetworkReply::readyRead, rep, [rep, file] { file->write(rep->readAll()); });
        QObject::connect(rep, &QNetworkReply::downloadProgress, rep, [progress](qint64 got, qint64 total) {
            progress(QString("Tesseract — %1/%2 MB").arg(got / 1e6, 0, 'f', 1).arg(total / 1e6, 0, 'f', 1), total > 0 ? int(got * 100 / total) : 0);
        });
        QObject::connect(rep, &QNetworkReply::finished, rep, [=] {
            file->write(rep->readAll()); file->close(); rep->deleteLater();
            if (*cancelled) { QFile::remove(setup); return done("cancel"); }
            if (rep->error() != QNetworkReply::NoError) { QFile::remove(setup); return done(rep->errorString()); }
            progress(tx("engines.installing_tesseract_accept_if_windows"), 100);
            QThread* t = QThread::create([=] {
                const bool ok = runWait(setup, "/S /D=" + QDir::toNativeSeparators(tessDir()));
                QFile::remove(setup);
                QMetaObject::invokeMethod(&net::nam(), [=] {
                    if (!ok) return done(tx("engines.couldnt_run_installer_permission_denied"));
                    done(hasTesseract() ? QString() : tx("engines.tesseract_installation_failed_administrator_prompt"));
                });
            });
            QObject::connect(t, &QThread::finished, t, &QObject::deleteLater); t->start();
        });
    });
    return [=] { *cancelled = true; if (*reply) (*reply)->abort(); };
}

bool removeTesseract() {
    QDir d(tessDir());
    const QStringList un = d.entryList({"unins*.exe", "uninstall*.exe"}, QDir::Files);
    if (!un.isEmpty()) runWait(d.filePath(un.first()), "/S");          // gỡ bằng bộ gỡ của Tesseract để dọn cả registry
    d.removeRecursively();
    return !d.exists();
}
}  // namespace engines
