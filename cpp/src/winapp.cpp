#include "winapp.h"
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QMap>
#include <QWidget>
#include <windows.h>
#include <shellapi.h>
#include <shlobj.h>

#ifndef WDA_EXCLUDEFROMCAPTURE
#define WDA_EXCLUDEFROMCAPTURE 0x11
#endif

namespace winapp {
static QString exeOf(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return {};
    wchar_t buf[1024]; DWORD n = 1024; QString out;
    if (QueryFullProcessImageNameW(h, 0, buf, &n)) out = QFileInfo(QString::fromWCharArray(buf, int(n))).fileName().toLower();
    CloseHandle(h);
    return out;
}

Fg foreground() {
    HWND w = GetForegroundWindow();
    if (!w) return {};
    DWORD pid = 0; GetWindowThreadProcessId(w, &pid);
    return {pid, exeOf(pid)};
}

bool selfElevated() { return IsUserAnAdmin(); }

int elevated(unsigned long pid) {
    if (!pid) return -1;
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return -1;
    HANDLE tok = nullptr; int res = -1;
    if (!OpenProcessToken(h, TOKEN_QUERY, &tok)) res = 1;                // bị chặn -> tiến trình cao quyền hơn
    else {
        TOKEN_ELEVATION e{}; DWORD n = 0;
        if (GetTokenInformation(tok, TokenElevation, &e, sizeof e, &n)) res = e.TokenIsElevated ? 1 : 0;
        CloseHandle(tok);
    }
    CloseHandle(h);
    return res;
}

bool relaunchAsAdmin() {
    const std::wstring exe = QDir::toNativeSeparators(QCoreApplication::applicationFilePath()).toStdWString();
    return reinterpret_cast<INT_PTR>(ShellExecuteW(nullptr, L"runas", exe.c_str(), nullptr, nullptr, SW_SHOWNORMAL)) > 32;
}

void forceForeground(void* hwnd) {
    HWND w = static_cast<HWND>(hwnd);
    if (!w) return;
    HWND fg = GetForegroundWindow(); DWORD me = GetCurrentThreadId();
    DWORD other = fg ? GetWindowThreadProcessId(fg, nullptr) : 0;
    const bool attached = other && other != me && AttachThreadInput(me, other, TRUE);     // mượn quyền nhập của cửa sổ đang focus
    SetWindowPos(w, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW);
    BringWindowToTop(w); SetForegroundWindow(w); SetFocus(w);
    if (attached) AttachThreadInput(me, other, FALSE);
}

bool isTarget(const QString& target) {
    if (target.isEmpty()) return true;
    const Fg f = foreground();
    return f.exe.isEmpty() || f.pid == GetCurrentProcessId() || f.exe == target.toLower();
}

QList<QPair<QString, QString>> windows() {
    struct Ctx { QMap<QString, QString> out; DWORD me; } ctx{{}, GetCurrentProcessId()};
    EnumWindows([](HWND w, LPARAM lp) -> BOOL {
        auto* c = reinterpret_cast<Ctx*>(lp);
        if (IsWindowVisible(w) && GetWindowTextLengthW(w)) {
            DWORD pid = 0; GetWindowThreadProcessId(w, &pid);
            if (pid != c->me) {
                wchar_t t[256]; GetWindowTextW(w, t, 256); const QString exe = exeOf(pid);
                if (!exe.isEmpty() && !c->out.contains(exe)) c->out.insert(exe, QString::fromWCharArray(t));
            }
        }
        return TRUE;
    }, reinterpret_cast<LPARAM>(&ctx));
    QList<QPair<QString, QString>> out;
    for (auto it = ctx.out.begin(); it != ctx.out.end(); ++it) out.append({it.key(), it.value()});
    return out;
}

void excludeFromCapture(QWidget* w, bool on) {
    if (!w || !w->isVisible()) return;
    SetWindowDisplayAffinity(reinterpret_cast<HWND>(w->winId()), on ? WDA_EXCLUDEFROMCAPTURE : WDA_NONE);
}

void setPassthrough(QWidget* w, bool on) {
    // WS_EX_TRANSPARENT (+LAYERED). Không dùng Qt::WindowTransparentForInput: Qt bỏ luôn sự kiện chuột nên giữ phím mở khóa
    // cũng không bấm được, và đổi flag tạo lại cửa sổ (nháy).
    HWND h = reinterpret_cast<HWND>(w->winId());
    const LONG ex = GetWindowLongW(h, GWL_EXSTYLE);
    SetWindowLongW(h, GWL_EXSTYLE, on ? (ex | WS_EX_TRANSPARENT | WS_EX_LAYERED) : (ex & ~WS_EX_TRANSPARENT));
}

bool keyDown(int vk) { return GetAsyncKeyState(vk) & 0x8000; }
}  // namespace winapp
