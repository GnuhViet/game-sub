#pragma once
// Tách từ bị OCR dính liền ("youfinallywoke" -> "you finally woke") theo tần suất từ tiếng Anh — viết lại thuật toán wordninja.
// Danh sách 126k từ nằm trong 1 khối byte + bảng (từ, cost) sắp xếp (~4 MB), không phải dict Python (~15 MB).
#include <QByteArray>
#include <QSet>
#include <QString>
#include <string>
#include <string_view>
#include <vector>

class Spacer {
public:
    void setKnown(const QStringList& words);
    QString fix(const QString& text);
    std::vector<std::string> split(const std::string& s);       // wordninja.split (đã hạ chữ thường)
    double cost(std::string_view w) const;                       // 9e999 nếu không có

private:
    void load();
    std::vector<std::string> splitPart(const std::string& s);
    QString splitToken(const QString& tok);

    bool loaded_ = false;
    QByteArray buf_;
    std::vector<std::pair<std::string_view, double>> words_;    // sắp theo từ
    size_t maxWord_ = 0;
    QSet<QString> known_;
};
