#pragma once
// Chuẩn hóa chữ cho khớp sub / tách từ / tra từ (giống gamesub/textnorm.py).
#include <QRegularExpression>
#include <QString>
#include <QStringList>

namespace textnorm {
extern const QString WILD;                       // "§" thay placeholder / tên người chơi khi so khớp
const QRegularExpression& wordRe();              // một từ tiếng Anh (link tra từ)

QString resolve(const QString& text, const QString& gender, const QStringList& nameTokens, const QString& playerName, bool forMatch = false);
QString norm(const QString& text);
QString ocrForMatch(const QString& text, const QString& playerName);
QString joinLines(const QStringList& lines);
QString paragraphs(const QStringList& lines);
QStringList splitSentences(const QString& text);
QStringList lemmas(const QString& word);
}
