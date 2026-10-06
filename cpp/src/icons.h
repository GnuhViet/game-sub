#pragma once
// Icon đơn sắc vẽ từ font Material Design Icons (:/mdi6.ttf — chỉ chứa các icon app dùng; tạo bằng tools/make_icon_font.py).
// mdi("mdi6.pause", màu, màu khi rê chuột): màu khi rê chuột dùng cho QIcon::Active (nút autoRaise).
#include <QColor>
#include <QIcon>
#include <QString>

QIcon mdi(const QString& name, const QColor& color = QColor("#c8c8c8"), const QColor& active = QColor());
