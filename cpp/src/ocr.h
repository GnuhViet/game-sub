#pragma once
// OCR engine: recognize(ảnh) -> các dòng chữ từ trên xuống. Windows OCR (WinRT) / Tesseract (tesseract.exe).
// Windows OCR gọi đồng bộ (.get()) nên phải chạy ở luồng MTA (luồng chụp / luồng phụ), không chạy ở luồng giao diện.
#include <QImage>
#include <QString>
#include <QStringList>
#include <memory>

class OcrEngine {
public:
    virtual ~OcrEngine() = default;
    virtual QString name() const = 0;
    virtual QStringList recognize(const QImage& img) = 0;
};

std::unique_ptr<OcrEngine> createOcr(const QString& name, const QString& lang, QString* error);
QString tesseractExe();         // engines/tesseract > PATH > Program Files; "" nếu không có
void initWinrtThread();         // gọi 1 lần ở đầu luồng sẽ dùng Windows OCR
