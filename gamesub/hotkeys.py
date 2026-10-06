"""Hotkey toàn cục qua Win32 RegisterHotKey (không cần quyền admin, không hook bàn phím)."""
import sys
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
VK = {**{f"f{i}": 0x6F + i for i in range(1, 13)}, "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
      "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "pgup": 0x21, "pgdn": 0x22, "`": 0xC0, "home": 0x24, "end": 0x23,
      "pgdown": 0x22, "return": 0x0D, "ins": 0x2D, "insert": 0x2D}         # tên Qt (QKeySequence.toString) của PgDown / Enter / Insert

HOLD = {"alt": 0x12, "ctrl": 0x11, "control": 0x11, "shift": 0x10, "win": 0x5B, "meta": 0x5B, "capslock": 0x14, "backspace": 0x08,
        "return": 0x0D, "pgdown": 0x22, "ins": 0x2D, "del": 0x2E, "mouse3": 0x04, "mouse4": 0x05, "mouse5": 0x06}

def held_vks(seq):
    """'Ctrl+Mouse4' -> [VK…] để dò phím đang giữ (GetAsyncKeyState); None nếu có phần không hiểu, [] nếu rỗng."""
    out = []
    for p in seq.lower().replace(" ", "").split("+"):
        if not p: continue
        vk = HOLD.get(p) or VK.get(p) or (ord(p.upper()) if len(p) == 1 and p.isalnum() else None)
        if vk is None: return None
        out.append(vk)
    return out

def parse(seq):
    mods, vk = 0, None
    for p in seq.lower().replace(" ", "").split("+"):
        if p in MODS: mods |= MODS[p]
        elif p in VK: vk = VK[p]
        elif len(p) == 1 and p.isalnum(): vk = ord(p.upper())
    return mods, vk

class _Filter(QAbstractNativeEventFilter):
    def __init__(self, cb, show): super().__init__(); self.cb = cb; self.show = show
    def nativeEventFilter(self, etype, message):
        if etype == b"windows_generic_MSG":
            import ctypes.wintypes as wt
            from .winapp import SHOW_MSG
            msg = wt.MSG.from_address(int(message))
            if msg.message == 0x0312: self.cb(int(msg.wParam)); return True, 0
            if msg.message == SHOW_MSG: self.show(); return True, 0          # winapp.show_running() từ bản mở sau
        return False, 0

class Hotkeys(QObject):
    triggered = Signal(str)
    show_requested = Signal()

    def __init__(self, app):
        super().__init__(); self.app, self.ids, self.ok = app, {}, sys.platform == "win32"
        if self.ok:
            self.filter = _Filter(lambda i: self.triggered.emit(self.ids.get(i, "")), self.show_requested.emit); app.installNativeEventFilter(self.filter)

    def register(self, mapping):
        """mapping: {action: 'Alt+T'} -> list lỗi."""
        if not self.ok: return []
        import ctypes; u32 = ctypes.windll.user32
        for i in list(self.ids): u32.UnregisterHotKey(None, i)
        self.ids.clear(); errs = []
        for n, (action, seq) in enumerate(mapping.items(), 1):
            if not seq: continue
            mods, vk = parse(seq)
            if vk is None or not u32.RegisterHotKey(None, n, mods | 0x4000, vk): errs.append(f"{action}={seq}")
            else: self.ids[n] = action
        return errs
