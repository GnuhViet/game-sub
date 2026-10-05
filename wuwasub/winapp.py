"""Cửa sổ đang focus thuộc app nào (để chỉ chụp/dịch khi game đang mở trên cùng)."""
import ctypes, os, sys
from ctypes import wintypes as wt

WIN = sys.platform == "win32"
if WIN:
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    k32.OpenProcess.restype = wt.HANDLE

def _exe(pid):
    h = k32.OpenProcess(0x1000, False, pid)                  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h: return ""
    try:
        buf = ctypes.create_unicode_buffer(1024); n = wt.DWORD(1024)
        return os.path.basename(buf.value).lower() if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally: k32.CloseHandle(h)

def _pid(hwnd):
    pid = wt.DWORD(); u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)); return pid.value

def foreground():
    """-> (pid, exe) của cửa sổ đang focus; (0, '') nếu không xác định."""
    if not WIN: return 0, ""
    hwnd = u32.GetForegroundWindow()
    if not hwnd: return 0, ""
    pid = _pid(hwnd); return pid, _exe(pid)

def self_elevated():
    return bool(WIN and ctypes.windll.shell32.IsUserAnAdmin())

def elevated(pid):
    """Tiến trình chạy quyền admin? True/False; None nếu không xác định. Không mở được token (bị từ chối) -> coi là admin."""
    if not WIN or not pid: return None
    adv = ctypes.windll.advapi32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h: return None
    try:
        tok = wt.HANDLE()
        if not adv.OpenProcessToken(h, 0x0008, ctypes.byref(tok)): return True        # TOKEN_QUERY bị chặn -> tiến trình cao quyền hơn
        try:
            val, n = wt.DWORD(), wt.DWORD()
            return bool(val.value) if adv.GetTokenInformation(tok, 20, ctypes.byref(val), 4, ctypes.byref(n)) else None   # TokenElevation
        finally: k32.CloseHandle(tok)
    finally: k32.CloseHandle(h)

def relaunch_as_admin():
    """Mở lại WuWaSub với quyền admin (Windows hỏi UAC). -> True nếu đã mở."""
    if getattr(sys, "frozen", False): exe, args = sys.executable, ""
    else: exe, args = sys.executable, f'"{os.path.abspath(sys.argv[0])}"'
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, os.getcwd(), 1) > 32

def force_foreground(hwnd):
    """Đưa cửa sổ lên trên cùng + lấy focus kể cả khi game đang giữ tiền cảnh (Windows chặn SetForegroundWindow thường)."""
    if not WIN or not hwnd: return
    fg = u32.GetForegroundWindow(); me = k32.GetCurrentThreadId()
    other = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and u32.AttachThreadInput(me, other, True))   # mượn quyền nhập của cửa sổ đang focus
    try:
        u32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)               # HWND_TOPMOST, NOSIZE|NOMOVE|SHOWWINDOW
        u32.BringWindowToTop(hwnd); u32.SetForegroundWindow(hwnd); u32.SetFocus(hwnd)
    finally:
        if attached: u32.AttachThreadInput(me, other, False)

def is_target(target):
    """True nếu không lọc, app đích đang focus, hoặc đang thao tác trên chính WuWaSub."""
    if not target or not WIN: return True
    pid, exe = foreground()
    return not exe or pid == os.getpid() or exe == target.lower()

def windows():
    """Các app có cửa sổ đang mở: [(exe, tiêu đề)] (bỏ chính WuWaSub)."""
    if not WIN: return []
    out, me = {}, os.getpid()
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if u32.IsWindowVisible(hwnd) and u32.GetWindowTextLengthW(hwnd):
            pid = _pid(hwnd)
            if pid != me:
                t = ctypes.create_unicode_buffer(256); u32.GetWindowTextW(hwnd, t, 256); exe = _exe(pid)
                if exe and exe not in out: out[exe] = t.value
        return True
    u32.EnumWindows(cb, 0)
    return sorted(out.items())
