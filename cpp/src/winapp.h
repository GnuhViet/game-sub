#pragma once
// Win32: cửa sổ đang focus thuộc app nào, quyền admin, đưa cửa sổ lên trước, ẩn khỏi ảnh chụp, chuột xuyên qua (giống winapp.py).
#include <QList>
#include <QPair>
#include <QString>

class QWidget;

namespace winapp {
struct Fg { unsigned long pid = 0; QString exe; };
Fg foreground();                                   // cửa sổ đang focus; exe chữ thường
bool selfElevated();
int elevated(unsigned long pid);                    // 1 admin / 0 không / -1 không xác định (bị chặn đọc token -> coi là admin: 1)
bool relaunchAsAdmin();
void forceForeground(void* hwnd);
bool isTarget(const QString& target);               // không lọc / app đích đang focus / đang thao tác trên chính GameSub
QList<QPair<QString, QString>> windows();           // [(exe, tiêu đề)] các app có cửa sổ, bỏ chính GameSub
void excludeFromCapture(QWidget* w, bool on = true); // vô hình với mọi ảnh chụp (Windows 10 2004+)
void setPassthrough(QWidget* w, bool on);           // chuột xuyên qua (WS_EX_TRANSPARENT)
bool keyDown(int vk);
}
