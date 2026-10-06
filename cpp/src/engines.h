#pragma once
// OCR engine tải thêm vào <exe>/engines: Tesseract (bộ cài UB-Mannheim chạy im lặng). Giống engines.py (bản C++ chưa có RapidOCR).
#include <QString>
#include <functional>

namespace engines {
QString dir();                        // <exe>/engines
QString tessDir();
bool hasTesseract();
double sizeMb(const QString& d);
// tải + cài: progress(chữ, %), done("" = xong / "cancel" / lỗi). Trả về hàm hủy.
std::function<void()> installTesseract(std::function<void(const QString&, int)> progress, std::function<void(const QString&)> done);
bool removeTesseract();               // true nếu xóa ngay
}
