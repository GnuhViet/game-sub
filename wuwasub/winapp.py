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
