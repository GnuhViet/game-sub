"""Icon đơn sắc vẽ từ font Material Design Icons (assets/mdi6.ttf — chỉ chứa các icon app dùng, tạo bằng tools/make_icon_font.py).
Thay qtawesome: thư viện đó nạp ~7 bộ font icon + bảng tên (~40 MB RAM) dù app chỉ dùng vài chục icon MDI6.
icon("mdi6.pause", color=…, color_active=…): color_active là màu khi rê chuột (QIcon.Active, nút autoRaise)."""
import json
from pathlib import Path
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QIcon, QIconEngine, QPixmap, QPainter, QColor, QFont, QFontDatabase

ASSETS = Path(__file__).resolve().parent / "assets"
CODES = json.loads((ASSETS / "mdi6.json").read_text("utf-8"))
_family = None

def _font_family():
    global _family
    if _family is None:                                     # nạp font lần đầu cần icon (sau khi đã có QApplication)
        fams = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(ASSETS / "mdi6.ttf")))
        _family = fams[0] if fams else ""
    return _family

class _Engine(QIconEngine):
    def __init__(self, ch, color, active):
        super().__init__(); self.ch, self.color, self.active = ch, QColor(color), QColor(active or color)

    def paint(self, p, rect, mode, state):
        col = QColor(self.active if mode in (QIcon.Active, QIcon.Selected) else self.color)
        if mode == QIcon.Disabled: col.setAlphaF(col.alphaF() * 0.4)
        f = QFont(_font_family()); f.setPixelSize(max(1, min(rect.width(), rect.height())))
        p.save(); p.setRenderHint(QPainter.TextAntialiasing); p.setFont(f); p.setPen(col)
        p.drawText(rect, Qt.AlignCenter, self.ch); p.restore()

    def pixmap(self, size, mode, state): return self.scaledPixmap(size, mode, state, 1.0)

    def scaledPixmap(self, size, mode, state, scale):       # màn hình HiDPI: vẽ đủ điểm ảnh, không bị mờ
        pm = QPixmap(size * scale); pm.setDevicePixelRatio(scale); pm.fill(Qt.transparent)
        p = QPainter(pm); self.paint(p, QRect(QPoint(0, 0), size), mode, state); p.end(); return pm

    def clone(self): return _Engine(self.ch, self.color, self.active)

def icon(name, color="#c8c8c8", color_active=None):
    return QIcon(_Engine(chr(CODES[name.split(".", 1)[-1]]), color, color_active))
