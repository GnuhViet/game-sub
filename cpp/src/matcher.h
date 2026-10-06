#pragma once
// Tra câu OCR trong bộ sub: khớp tuyệt đối -> gần đúng (rapidfuzz ratio, lọc theo độ dài) -> tách câu (giống matcher.py).
#include <QHash>
#include <QList>
#include <QPair>
#include <QString>
#include <QStringList>
#include <optional>
#include <vector>

struct SubMatch { QString vi; double score = 0; QString src; };

class SubIndex {
public:
    int build(const QList<QPair<QString, QString>>& pairs, const QString& gender, const QStringList& nameTokens, const QString& playerName);
    int size() const { return int(exact_.size()); }
    std::optional<SubMatch> match(const QString& text, double threshold = 86) const;

private:
    struct Item { int len; QString key, vi, src; std::u16string k16; };
    std::optional<SubMatch> one(const QString& q, double th) const;
    std::optional<SubMatch> best(const QString& text, double th) const;

    QHash<QString, QPair<QString, QString>> exact_;   // key -> (vi, src)
    std::vector<Item> items_;                          // sắp theo độ dài key
    std::vector<int> lens_;
    QString player_;
};
