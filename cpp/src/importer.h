#pragma once
// Đọc bộ sub từ CSV/TSV/TXT/XLSX/JSON thành bảng (tiêu đề, các dòng) và đoán cột gốc / cột dịch (giống importer.py).
#include <QList>
#include <QPair>
#include <QString>
#include <QStringList>

namespace importer {
struct Table { QStringList hdr; QList<QStringList> rows; };
Table readTable(const QString& path);                              // ném std::runtime_error khi lỗi
QPair<int, int> guessCols(const QStringList& hdr, const QList<QStringList>& rows);
QList<QPair<QString, QString>> extractPairs(const QList<QStringList>& rows, int srcIdx, int viIdx);
}
