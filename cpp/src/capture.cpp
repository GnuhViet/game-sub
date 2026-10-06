#include "capture.h"
#include "i18n.h"
#include "ocr.h"
#include "textnorm.h"
#include "winapp.h"
#include <QDateTime>
#include <QMutexLocker>
#include <cmath>
#include <windows.h>
#include <winrt/base.h>

CaptureSettings captureSettings(const Config& c) {
    CaptureSettings s;
    s.region = c.region("region"); s.speaker = c.region("speaker_region");
    s.ocrEngine = c.str("ocr_engine"); s.ocrLang = c.str("ocr_lang"); s.targetApp = c.str("target_app");
    s.ocrScale = c.d("ocr_scale") > 0 ? c.d("ocr_scale") : 1; s.diffThreshold = c.d("diff_threshold");
    s.intervalMs = c.i("interval_ms"); s.stableMs = c.i("stable_ms");
    return s;
}

QImage grabScreen(const Region& r) {
    const int w = std::max(1, r.w), h = std::max(1, r.h);
    HDC screen = GetDC(nullptr), mem = CreateCompatibleDC(screen);
    BITMAPINFO bi{}; bi.bmiHeader = {sizeof(BITMAPINFOHEADER), w, -h, 1, 32, BI_RGB};
    void* bits = nullptr;
    HBITMAP dib = CreateDIBSection(screen, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    HGDIOBJ old = SelectObject(mem, dib);
    BitBlt(mem, 0, 0, w, h, screen, r.x, r.y, SRCCOPY | CAPTUREBLT);
    GdiFlush();
    QImage img(static_cast<const uchar*>(bits), w, h, w * 4, QImage::Format_RGB32);
    QImage out = img.copy();                                          // tách khỏi bộ nhớ DIB trước khi giải phóng
    SelectObject(mem, old); DeleteObject(dib); DeleteDC(mem); ReleaseDC(nullptr, screen);
    return out;
}

Signature signature(const QImage& img) {
    Signature s; const int step = std::max(1, img.width() / 96);
    s.w = (img.width() + step - 1) / step; s.h = (img.height() + step - 1) / step; s.v.reserve(size_t(s.w) * s.h);
    for (int y = 0; y < img.height(); y += step) {
        const QRgb* row = reinterpret_cast<const QRgb*>(img.constScanLine(y));
        for (int x = 0; x < img.width(); x += step) s.v.push_back((qRed(row[x]) + qGreen(row[x]) + qBlue(row[x])) / 3.0f);
    }
    return s;
}

double sigDiff(const Signature& a, const Signature& b) {
    if (a.w != b.w || a.h != b.h || a.v.empty()) return -1;
    double sum = 0;
    for (size_t i = 0; i < a.v.size(); ++i) sum += std::fabs(a.v[i] - b.v[i]);
    return sum / double(a.v.size());
}

CaptureWorker::CaptureWorker(const CaptureSettings& s) : s_(s) {}
void CaptureWorker::setSettings(const CaptureSettings& s) { QMutexLocker l(&m_); s_ = s; }
CaptureSettings CaptureWorker::settings() { QMutexLocker l(&m_); return s_; }
void CaptureWorker::requestSnapshot(const QString& path) { QMutexLocker l(&m_); snapshot_ = path; }
void CaptureWorker::stop() { running_ = false; wait(3000); }

void CaptureWorker::run() {
    initWinrtThread();
    std::unique_ptr<OcrEngine> eng;
    auto load = [&](const CaptureSettings& s) {
        QString err; eng = createOcr(s.ocrEngine, s.ocrLang, &err);
        if (eng) emit status("OCR: " + eng->name());
        else emit error(tx("ocr.couldnt_start_ocr_eng_e", {{"eng", s.ocrEngine}, {"e", err}}));
    };
    auto ocr = [&](const CaptureSettings& s, QImage img) {
        if (std::fabs(s.ocrScale - 1) > 0.01) img = img.scaled(int(img.width() * s.ocrScale), int(img.height() * s.ocrScale), Qt::IgnoreAspectRatio, Qt::SmoothTransformation);
        return textnorm::joinLines(eng->recognize(img));
    };
    load(settings());
    Signature prev, lastOcr; bool pending = false, waiting = false; qint64 lastChange = 0;
    while (running_) {
        const qint64 t0 = QDateTime::currentMSecsSinceEpoch();
        CaptureSettings s = settings();
        try {
            if (reloadEngine.exchange(false)) load(s);
            QString snap; { QMutexLocker l(&m_); snap.swap(snapshot_); }
            if (!snap.isEmpty() && s.region.valid()) { grabScreen(s.region).save(snap); emit status(tx("ocr.saved_region_image_path", {{"path", snap}})); }
            if (paused || !s.region.valid() || !eng) { msleep(200); continue; }
            if (!winapp::isTarget(s.targetApp)) {                       // đang ở app khác -> không chụp
                if (!waiting) { waiting = true; emit status(tx("ocr.waiting_for_app", {{"app", s.targetApp}})); }
                msleep(300); continue;
            }
            if (waiting) { waiting = false; emit status(""); }
            const QImage img = grabScreen(s.region); const Signature sig = signature(img);
            const double d = sigDiff(sig, prev);
            if (d < 0 || d > s.diffThreshold) { prev = sig; pending = true; lastChange = QDateTime::currentMSecsSinceEpoch(); }
            if (force || (pending && QDateTime::currentMSecsSinceEpoch() - lastChange >= s.stableMs)) {
                pending = false;
                const double dl = sigDiff(sig, lastOcr);
                const bool same = dl >= 0 && dl <= s.diffThreshold;     // ảnh y như lần OCR trước (nền nhấp nháy rồi về cũ) -> khỏi OCR lại
                if (!same || force) {
                    force = false; lastOcr = sig;
                    const QString text = ocr(s, img);
                    const QString spk = !text.isEmpty() && s.speaker.valid() ? ocr(s, grabScreen(s.speaker)) : QString();
                    emit textReady(spk, text);
                }
            }
        } catch (const winrt::hresult_error& e) {
            emit error(tx("ocr.capture_ocr_error_e", {{"e", QString::fromWCharArray(e.message().c_str())}})); msleep(1000);
        } catch (const std::exception& e) {
            emit error(tx("ocr.capture_ocr_error_e", {{"e", QString::fromUtf8(e.what())}})); msleep(1000);
        }
        const qint64 spent = QDateTime::currentMSecsSinceEpoch() - t0;
        msleep(ulong(std::max<qint64>(20, s.intervalMs - spent)));
    }
}
