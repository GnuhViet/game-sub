from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QFont
from PySide6.QtWidgets import QWidget, QApplication
from .i18n import tr

class RegionSelector(QWidget):
    """Đóng băng màn hình dưới con trỏ, kéo chuột để chọn vùng. Trả về rect theo pixel vật lý (cho mss)."""
    selected = Signal(dict)
    cancelled = Signal()

    def __init__(self, title=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.scr = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self.bg = self.scr.grabWindow(0); self.title = title or tr("region.drag_select_area_esc_cancel")
        self.setGeometry(self.scr.geometry()); self.setCursor(Qt.CrossCursor)
        self.p0 = self.p1 = None

    def start(self):
        self.show(); self.activateWindow(); self.raise_(); self.setFocus()
        from .winapp import force_foreground; force_foreground(int(self.winId()))    # gọi bằng hotkey khi game đang focus

    def paintEvent(self, e):
        p = QPainter(self); p.drawPixmap(self.rect(), self.bg); p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if self.p0 and self.p1:
            r = QRect(self.p0, self.p1).normalized()
            src = QRect(int(r.x() * self.bg.width() / self.width()), int(r.y() * self.bg.height() / self.height()),
                        int(r.width() * self.bg.width() / self.width()), int(r.height() * self.bg.height() / self.height()))
            p.drawPixmap(r, self.bg, src); p.setPen(QPen(QColor("#e8c26a"), 2)); p.drawRect(r)
            p.drawText(r.bottomLeft() + QPoint(2, 16), f"{round(r.width() * self.scr.devicePixelRatio())}×{round(r.height() * self.scr.devicePixelRatio())}")
        f = QFont(); f.setPointSize(14); p.setFont(f); p.setPen(QColor("white"))
        p.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignHCenter | Qt.AlignTop, self.title)

    def mousePressEvent(self, e): self.p0 = self.p1 = e.position().toPoint(); self.update()
    def mouseMoveEvent(self, e):
        if self.p0: self.p1 = e.position().toPoint(); self.update()
    def mouseReleaseEvent(self, e):
        if not self.p0: return
        r = QRect(self.p0, e.position().toPoint()).normalized(); self.close()
        if r.width() < 8 or r.height() < 8: self.cancelled.emit(); return
        self.selected.emit(to_physical(self.scr, r))
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape: self.close(); self.cancelled.emit()

class RegionFlash(QWidget):
    """Viền sáng + nhãn quanh vùng đang chọn. Chuột xuyên qua; vô hình với ảnh chụp nên OCR không đọc phải."""
    PAD, LABEL_H = 3, 22
    def __init__(self, rect, label, color):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.label, self.color = label, QColor(color)
        self.setGeometry(rect.adjusted(-self.PAD, -self.PAD - self.LABEL_H, self.PAD, self.PAD))

    def showEvent(self, e):
        super().showEvent(e)
        from .ui_overlay import exclude_from_capture; exclude_from_capture(self)

    def paintEvent(self, e):
        p = QPainter(self); c = self.color
        box = self.rect().adjusted(1, self.LABEL_H + 1, -1, -1)
        p.setPen(QPen(c, 2)); p.setBrush(QColor(c.red(), c.green(), c.blue(), 35)); p.drawRect(box)
        f = QFont(); f.setPointSize(9); f.setBold(True); p.setFont(f)
        tab = QRect(box.x() - 1, 0, p.fontMetrics().horizontalAdvance(self.label) + 14, self.LABEL_H)
        p.fillRect(tab, c); p.setPen(QColor("#111")); p.drawText(tab, Qt.AlignCenter, self.label)

def to_logical(r):
    """Ngược với to_physical: rect pixel vật lý (mss) -> QRect toạ độ Qt."""
    for s in QApplication.screens():
        g, d = s.geometry(), s.devicePixelRatio()
        if g.x() <= r["x"] < g.x() + g.width() * d and g.y() <= r["y"] < g.y() + g.height() * d:
            return QRect(round(g.x() + (r["x"] - g.x()) / d), round(g.y() + (r["y"] - g.y()) / d), round(r["w"] / d), round(r["h"] / d))
    return QRect(r["x"], r["y"], r["w"], r["h"])

def to_physical(screen, local_rect):
    """Qt6/Windows: gốc màn hình giữ nguyên pixel vật lý, phần bên trong scale theo DPR."""
    g, d = screen.geometry(), screen.devicePixelRatio()
    return {"x": round(g.x() + local_rect.x() * d), "y": round(g.y() + local_rect.y() * d),
            "w": round(local_rect.width() * d), "h": round(local_rect.height() * d)}
