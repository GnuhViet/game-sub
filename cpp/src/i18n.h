#pragma once
// Đa ngôn ngữ giao diện: locales/<mã>.json = {"_name": "Tên ngôn ngữ", "key": "chữ"} đặt cạnh exe (dùng chung với bản Python).
// tx("key") / tx("key", {{"n", "5"}}): biến trong chữ dạng {n}, "{{" "}}" là ngoặc thật. vi.json là gốc; thiếu key -> tiếng Việt -> key.
// Tên hàm là tx (không phải tr) để khỏi bị QObject::tr che mất trong các lớp con QObject.
#include <QList>
#include <QPair>
#include <QString>
#include <initializer_list>
#include <utility>

#define N_(key) key   // đánh dấu key dịch lúc dùng (bảng tooltip, menu…)

namespace i18n {
void init(const QString& localesDir);
void setLang(const QString& code);              // "" = theo Windows
QString lang();
QList<QPair<QString, QString>> langs();          // [(mã, tên)], tiếng Việt đầu tiên
QString systemLang();
}

using TxArgs = std::initializer_list<std::pair<const char*, QString>>;
QString tx(const char* key, TxArgs args = {});
QString tx(const QString& key, TxArgs args = {});
