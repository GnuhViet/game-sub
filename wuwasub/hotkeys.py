"""Hotkey toàn cục qua Win32 RegisterHotKey (không cần quyền admin, không hook bàn phím)."""
import sys
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
VK = {**{f"f{i}": 0x6F + i for i in range(1, 13)}, "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
      "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "pgup": 0x21, "pgdn": 0x22, "`": 0xC0, "home": 0x24, "end": 0x23}

def parse(seq):
    mods, vk = 0, None
    for p in seq.lower().replace(" ", "").split("+"):
        if p in MODS: mods |= MODS[p]
        elif p in VK: vk = VK[p]
        elif len(p) == 1 and p.isalnum(): vk = ord(p.upper())
    return mods, vk

class _Filter(QAbstractNativeEventFilter):
    def __init__(self, cb): super().__init__(); self.cb = cb
    def nativeEventFilter(self, etype, message):
        if etype == b"windows_generic_MSG":
            import ctypes.wintypes as wt
            msg = wt.MSG.from_address(int(message))
            if msg.message == 0x0312: self.cb(int(msg.wParam)); return True, 0
        return False, 0

class Hotkeys(QObject):
    triggered = Signal(str)

    def __init__(self, app):
        super().__init__(); self.app, self.ids, self.ok = app, {}, sys.platform == "win32"
        if self.ok:
            self.filter = _Filter(lambda i: self.triggered.emit(self.ids.get(i, ""))); app.installNativeEventFilter(self.filter)

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
