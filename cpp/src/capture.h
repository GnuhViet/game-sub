#pragma once
// Luồng chụp vùng thoại -> phát hiện thay đổi -> chờ chữ ổn định (hiệu ứng chữ chạy) -> OCR (giống capture.py).
// Cài đặt được chép sang luồng này qua setSettings() (không đọc Config từ luồng khác).
#include <QImage>
#include <QMutex>
#include <QThread>
#include <atomic>
#include <vector>
#include "config.h"

struct CaptureSettings {
    Region region, speaker;
    QString ocrEngine = "windows", ocrLang = "en-US", targetApp;
    double ocrScale = 1, diffThreshold = 3;
    int intervalMs = 250, stableMs = 350;
};
CaptureSettings captureSettings(const Config& c);

QImage grabScreen(const Region& r);                                 // pixel vật lý, Format_RGB32
struct Signature { int w = 0, h = 0; std::vector<float> v; };
Signature signature(const QImage& img);                             // ảnh xám thu nhỏ ~96 điểm chiều ngang
double sigDiff(const Signature& a, const Signature& b);             // độ lệch sáng trung bình; -1 nếu khác kích thước

class CaptureWorker : public QThread {
    Q_OBJECT
public:
    explicit CaptureWorker(const CaptureSettings& s);
    void setSettings(const CaptureSettings& s);
    void stop();
    std::atomic<bool> paused{false}, force{false}, reloadEngine{false};
    void requestSnapshot(const QString& path);
signals:
    void textReady(const QString& speaker, const QString& text);
    void status(const QString& msg);
    void error(const QString& msg);
protected:
    void run() override;
private:
    CaptureSettings settings();
    QMutex m_;
    CaptureSettings s_;
    QString snapshot_;
    std::atomic<bool> running_{true};
};
