from PySide6.QtCore import Qt, Signal, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QFont, QFontMetrics, QImage
from PySide6.QtWidgets import QWidget, QApplication, QHBoxLayout, QPushButton, QFrame, QMenu, QInputDialog
from .i18n import tr, N_

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

SPK_COLOR = "#6ab7e8"

def _font(pt, bold=False):
    f = QFont(); f.setPointSize(pt); f.setBold(bold); return f

class _Item:
    """1 vùng trong chế độ sửa. rect = toạ độ trong cửa sổ sửa (logical); None = vùng ở màn hình khác (giữ nguyên)."""
    def __init__(self, meta, rect, spk=False): self.meta, self.rect, self.spk, self.preview = dict(meta), rect, spk, None

class RegionEditor(QWidget):
    """Chế độ sửa vùng: đóng băng màn hình, hiện mọi vùng thoại (thứ tự = ưu tiên) + vùng tên nhân vật.
    Kéo chỗ trống = thêm vùng; kéo vùng = di chuyển; kéo ô ở góc/cạnh = đổi cỡ; nút trên nhãn: ▲▼ ưu tiên, ⏸ nhường, 👁 bật/tắt, ✕ xóa.
    Phím: Del xóa, mũi tên dịch 1px (Shift 10px), 1-9 đặt ưu tiên, Tab chọn vùng kế, F2 đổi tên, Enter lưu, Esc hủy.
    Vùng nào đổi xong thì OCR thử trên ảnh đóng băng (signal preview -> app chạy OCR -> set_preview)."""
    saved = Signal(list, object)           # regions (pixel vật lý + name/on/yield), speaker_region | None
    cancelled = Signal()
    preview = Signal(int, object)          # mã yêu cầu, ảnh RGB (numpy) cần OCR thử
    H, TAB_H, BTN = 5, 22, 18              # nửa cạnh ô kéo, cao nhãn, cỡ nút trên nhãn

    def __init__(self, regions, speaker=None, accent="#e8c26a", max_regions=6, draw_speaker=False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.scr = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self.bg = self.scr.grabWindow(0); self.setGeometry(self.scr.geometry()); self.setMouseTracking(True)
        self.accent, self.max = QColor(accent), max_regions
        self.items = [self._item(r) for r in regions]; self.spk = self._item(speaker, True) if speaker else None
        self.sel = self.drag = None; self.draw_spk = draw_speaker; self.msg = ""; self._seq = 0; self._req = {}
        self.pv_t = QTimer(self, singleShot=True, interval=300, timeout=lambda: self.sel and self._ask_preview(self.sel))   # dịch bằng phím: đợi xong mới OCR
        self._toolbar()

    # ---------- dữ liệu
    def _item(self, r, spk=False):
        g = to_logical(r).translated(-self.scr.geometry().topLeft())
        return _Item(r, g if QRect(QPoint(0, 0), self.scr.geometry().size()).intersects(g) else None, spk)

    def _out(self, it):
        d = dict(it.meta)
        if it.rect is not None: d.update(to_physical(self.scr, it.rect.normalized()))
        return d

    def result(self):
        from .config import region
        spk = {k: v for k, v in self._out(self.spk).items() if k in ("x", "y", "w", "h")} if self.spk else None
        return [region(self._out(it)) for it in self.items], spk

    def all_items(self): return ([self.spk] if self.spk else []) + self.items

    # ---------- giao diện
    def _toolbar(self):
        from .icons import icon
        bar = QFrame(self); bar.setObjectName("bar"); lay = QHBoxLayout(bar); lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(6)
        bar.setStyleSheet("QFrame#bar{background:rgba(16,20,24,230);border:1px solid #555;border-radius:8px}"
                          "QPushButton{color:#eee;background:#2a2f36;border:1px solid #444;border-radius:5px;padding:4px 10px}"
                          "QPushButton:hover{background:#39404a}QPushButton:checked{background:#3d5a73;border-color:%s}" % SPK_COLOR)
        self.btn_spk = QPushButton(icon("mdi6.account-plus", SPK_COLOR), tr("regions.speaker_area")); self.btn_spk.setCheckable(True)
        self.btn_spk.setChecked(self.draw_spk); self.btn_spk.toggled.connect(lambda v: (setattr(self, "draw_spk", v), self.update()))
        self.btn_suggest = QPushButton(icon("mdi6.auto-fix", self.accent.name()), tr("regions.suggest")); self.btn_suggest.hide()
        ok = QPushButton(icon("mdi6.check", "#8fd18f"), tr("regions.save")); ok.clicked.connect(self.save)
        no = QPushButton(icon("mdi6.close"), tr("regions.cancel")); no.clicked.connect(self.cancel)
        for b in (self.btn_spk, self.btn_suggest, ok, no): b.setFocusPolicy(Qt.NoFocus); b.setCursor(Qt.ArrowCursor); lay.addWidget(b)
        self.bar = bar; self._place_bar()

    def _place_bar(self): self.bar.adjustSize(); self.bar.move((self.width() - self.bar.width()) // 2, 12)

    def start(self):
        self.show(); self.activateWindow(); self.raise_(); self.setFocus()
        from .winapp import force_foreground; force_foreground(int(self.winId()))
        for it in self.all_items(): self._ask_preview(it)

    def _col(self, it):
        if it.spk: return QColor(SPK_COLOR)
        return QColor(self.accent) if it.meta.get("on", True) else QColor("#8a8a8a")

    def _label(self, it):
        if it.spk: return tr("regions.speaker_area")
        i = self.items.index(it); name = it.meta.get("name") or (tr("app.dialogue_area") if i == 0 else tr("regions.default_name", n=i + 1))
        return f"{i + 1} · {name}"

    def _buttons(self, it):
        if it.spk: return [("close", "mdi6.close")]
        return [("up", "mdi6.arrow-up"), ("down", "mdi6.arrow-down"), ("yield", "mdi6.pause-circle-outline"),
                ("on", "mdi6.eye" if it.meta.get("on", True) else "mdi6.eye-off"), ("close", "mdi6.close")]

    def _label_box(self, it):
        """Nhãn trên vùng (hoặc ngay trong mép trên nếu vùng sát đỉnh màn hình) + toạ độ các nút trên nhãn."""
        r = it.rect.normalized(); w = QFontMetrics(_font(9, True)).horizontalAdvance(self._label(it)); bts = self._buttons(it)
        y = r.top() - self.TAB_H if r.top() >= self.TAB_H else r.top()
        tab = QRect(r.left(), y, w + 14 + len(bts) * (self.BTN + 2), self.TAB_H)
        x = tab.left() + w + 12; out = []
        for k, name in bts: out.append((k, name, QRect(x, y + (self.TAB_H - self.BTN) // 2, self.BTN, self.BTN))); x += self.BTN + 2
        return tab, out

    def _handles(self, r):
        r = r.normalized(); xs = (r.left(), r.center().x(), r.right()); ys = (r.top(), r.center().y(), r.bottom())
        return {(i, j): QRect(xs[i] - self.H, ys[j] - self.H, 2 * self.H, 2 * self.H) for i in range(3) for j in range(3) if (i, j) != (1, 1)}

    def _src(self, r):
        sx, sy = self.bg.width() / max(1, self.width()), self.bg.height() / max(1, self.height())
        return QRect(round(r.x() * sx), round(r.y() * sy), max(1, round(r.width() * sx)), max(1, round(r.height() * sy)))

    def paintEvent(self, e):
        from .icons import icon
        p = QPainter(self); p.drawPixmap(self.rect(), self.bg); p.fillRect(self.rect(), QColor(0, 0, 0, 130))
        draw = [it for it in reversed(self.items) if it.rect is not None] + ([self.spk] if self.spk and self.spk.rect is not None else [])
        if self.sel in draw: draw.remove(self.sel); draw.append(self.sel)         # vùng đang chọn vẽ trên cùng
        if self.drag and self.drag[0] == "new": draw.append(_Item({}, QRect(self.drag[1], self.drag[2]).normalized(), self.draw_spk))
        known = self.all_items()
        for it in draw:
            r = it.rect.normalized(); c = self._col(it)
            p.drawPixmap(r, self.bg, self._src(r))
            p.setPen(QPen(c, 3 if it is self.sel else 2, Qt.SolidLine if it.meta.get("on", True) else Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(r)
            if it not in known:                                         # vùng đang kéo: chỉ hiện cỡ
                d = self.scr.devicePixelRatio(); p.setFont(_font(9)); p.setPen(QColor("white"))
                p.drawText(r.bottomLeft() + QPoint(2, 16), f"{round(r.width() * d)}×{round(r.height() * d)}"); continue
            tab, bts = self._label_box(it); p.fillRect(tab, c); p.setFont(_font(9, True)); p.setPen(QColor("#111"))
            p.drawText(tab.adjusted(7, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, self._label(it))
            for k, name, br in bts: icon(name, "#666" if k == "yield" and not it.meta.get("yield", True) else "#111").paint(p, br)
            if it is self.sel:
                p.setBrush(QColor("white")); p.setPen(QPen(c, 1))
                for h in self._handles(r).values(): p.drawRect(h)
            if it.preview is not None: self._draw_preview(p, it, r)
        p.setFont(_font(10)); hint = self.msg or (tr("regions.hint_speaker") if self.draw_spk else tr("regions.hint"))
        box = p.fontMetrics().boundingRect(hint).adjusted(-10, -4, 10, 4); box.moveCenter(QPoint(self.width() // 2, self.bar.geometry().bottom() + 20))
        p.setPen(Qt.NoPen); p.setBrush(QColor(16, 20, 24, 220)); p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor(self.accent) if self.msg else QColor("white")); p.drawText(box, Qt.AlignCenter, hint)

    def _draw_preview(self, p, it, r):
        """Kết quả OCR thử ngay dưới vùng (sát đáy màn hình thì nằm trong vùng)."""
        p.setFont(_font(9)); fm = p.fontMetrics(); w = max(180, min(r.width(), 700))
        txt = fm.elidedText(it.preview or tr("regions.no_text"), Qt.ElideRight, w * 2 - 30)
        box = fm.boundingRect(QRect(0, 0, w - 12, 400), Qt.TextWordWrap, txt).adjusted(-6, -3, 6, 3)
        box.moveTo(r.left(), r.bottom() + 5 if r.bottom() + box.height() + 8 < self.height() else r.top() + 4)
        p.fillRect(box, QColor(10, 12, 16, 225)); p.setPen(QColor("#ddd") if it.preview else QColor("#999"))
        p.drawText(box.adjusted(6, 3, -6, -3), Qt.TextWordWrap, txt)

    # ---------- chuột
    def _hit(self, pos):
        """-> ("btn", item, key) | ("handle", item, (i, j)) | ("body", item, None) | None. Vùng đang chọn được ưu tiên."""
        for it in ([self.sel] if self.sel else []) + self.all_items():
            if it.rect is None: continue
            tab, bts = self._label_box(it)
            for k, _, br in bts:
                if br.adjusted(-1, -1, 1, 1).contains(pos): return ("btn", it, k)
            if it is self.sel:
                for h, hr in self._handles(it.rect).items():
                    if hr.adjusted(-2, -2, 2, 2).contains(pos): return ("handle", it, h)
            if tab.contains(pos) or it.rect.normalized().contains(pos): return ("body", it, None)
        return None

    CURSORS = {(0, 0): Qt.SizeFDiagCursor, (2, 2): Qt.SizeFDiagCursor, (2, 0): Qt.SizeBDiagCursor, (0, 2): Qt.SizeBDiagCursor,
               (1, 0): Qt.SizeVerCursor, (1, 2): Qt.SizeVerCursor, (0, 1): Qt.SizeHorCursor, (2, 1): Qt.SizeHorCursor}

    def mousePressEvent(self, e):
        pos = e.position().toPoint(); h = self._hit(pos); self.msg = ""
        if e.button() == Qt.RightButton:
            if h: self.sel = h[1]; self.update(); self._menu(h[1], e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton: return
        if h and h[0] == "btn": self._button(h[1], h[2]); return
        if h and not self.draw_spk: self.sel = h[1]; self.drag = (h[0], pos, QRect(h[1].rect.normalized()), h[2])
        else: self.sel = None; self.drag = ("new", pos, pos)
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if not self.drag:
            h = None if self.draw_spk else self._hit(pos)
            self.setCursor(Qt.CrossCursor if not h else Qt.PointingHandCursor if h[0] == "btn" else self.CURSORS[h[2]] if h[0] == "handle" else Qt.SizeAllCursor)
            return
        kind, p0, r0 = self.drag[:3]; d = pos - p0
        if kind == "new": self.drag = ("new", p0, pos)
        elif kind == "body": self.sel.rect = self._clamp(r0.translated(d))
        else:
            i, j = self.drag[3]; r = QRect(r0)
            if i == 0: r.setLeft(min(r0.left() + d.x(), r0.right() - 8))
            if i == 2: r.setRight(max(r0.right() + d.x(), r0.left() + 8))
            if j == 0: r.setTop(min(r0.top() + d.y(), r0.bottom() - 8))
            if j == 2: r.setBottom(max(r0.bottom() + d.y(), r0.top() + 8))
            self.sel.rect = r.intersected(self.rect())
        self.update()

    def mouseReleaseEvent(self, e):
        if not self.drag or e.button() != Qt.LeftButton: return
        kind, p0, r0 = self.drag[:3]; self.drag = None
        if kind == "new":
            r = QRect(p0, e.position().toPoint()).normalized().intersected(self.rect())
            if r.width() >= 8 and r.height() >= 8: self.add(r, self.draw_spk)
        elif self.sel and self.sel.rect != r0: self._ask_preview(self.sel)
        self.update()

    def mouseDoubleClickEvent(self, e):
        h = self._hit(e.position().toPoint())
        if h and h[0] == "body" and not h[1].spk: self.drag = None; self.rename(h[1])

    def _menu(self, it, gpos):
        m = QMenu(self)
        if not it.spk:
            m.addAction(tr("regions.rename"), lambda: self.rename(it))
            for k, key in (("on", N_("regions.enabled")), ("yield", N_("regions.yield"))):
                a = m.addAction(tr(key), lambda k=k: self._button(it, k)); a.setCheckable(True); a.setChecked(it.meta.get(k, True))
            m.addAction(tr("regions.use_as_speaker"), lambda: self.make_speaker(it)); m.addSeparator()
        m.addAction(tr("regions.delete"), lambda: self.remove(it))
        m.exec(gpos)

    # ---------- thao tác (test gọi thẳng được)
    def add(self, rect, spk=False):
        if spk:
            it = self.spk = _Item({}, rect, True); self.btn_spk.setChecked(False)
        elif len(self.items) >= self.max: self.msg = tr("regions.max_n", n=self.max); self.update(); return None
        else: it = _Item({"name": "", "on": True, "yield": True}, rect); self.items.append(it)
        self.sel = it; self._ask_preview(it); self.update(); return it

    def remove(self, it):
        if it is self.spk: self.spk = None
        elif it in self.items: self.items.remove(it)
        if self.sel is it: self.sel = None
        self.update()

    def move_to(self, it, k):
        if it in self.items: self.items.remove(it); self.items.insert(max(0, min(k, len(self.items))), it); self.update()

    def make_speaker(self, it):
        if it not in self.items: return
        self.items.remove(it); self.spk = _Item({}, it.rect, True); self.spk.preview = it.preview; self.sel = self.spk; self.update()

    def rename(self, it):
        d = QInputDialog(self); d.setWindowFlag(Qt.WindowStaysOnTopHint, True); d.setWindowTitle(tr("regions.rename"))
        d.setLabelText(tr("regions.name_label")); d.setTextValue(it.meta.get("name", ""))
        if d.exec(): it.meta["name"] = d.textValue().strip(); self.update()

    def _button(self, it, k):
        if k == "close": self.remove(it); return
        if k == "up": self.move_to(it, self.items.index(it) - 1)
        elif k == "down": self.move_to(it, self.items.index(it) + 1)
        elif k in ("on", "yield"): it.meta[k] = not it.meta.get(k, True)
        if k == "yield": self.msg = tr("regions.yield_on") if it.meta["yield"] else tr("regions.yield_off")
        self.sel = it; self.update()

    def _clamp(self, r):
        r.moveLeft(max(0, min(r.left(), self.width() - r.width()))); r.moveTop(max(0, min(r.top(), self.height() - r.height()))); return r

    def keyPressEvent(self, e):
        k, it = e.key(), self.sel
        if k == Qt.Key_Escape: (self.btn_spk.setChecked(False) if self.draw_spk else self.cancel()); return
        if k in (Qt.Key_Return, Qt.Key_Enter): self.save(); return
        if k == Qt.Key_Tab:
            its = [x for x in self.all_items() if x.rect is not None]
            if its: self.sel = its[(its.index(it) + 1) % len(its)] if it in its else its[0]; self.update()
            return
        if not it: return
        if k in (Qt.Key_Delete, Qt.Key_Backspace): self.remove(it)
        elif k == Qt.Key_F2 and not it.spk: self.rename(it)
        elif Qt.Key_1 <= k <= Qt.Key_9 and not it.spk: self.move_to(it, k - Qt.Key_1)
        elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down) and it.rect is not None:
            n = 10 if e.modifiers() & Qt.ShiftModifier else 1
            dx, dy = {Qt.Key_Left: (-n, 0), Qt.Key_Right: (n, 0), Qt.Key_Up: (0, -n), Qt.Key_Down: (0, n)}[k]
            it.rect = self._clamp(it.rect.normalized().translated(dx, dy)); it.preview = None; self.pv_t.start(); self.update()

    # ---------- OCR thử
    def crop(self, r):
        """Ảnh RGB (numpy) của vùng r trên màn hình đóng băng, đủ điểm ảnh vật lý."""
        import numpy as np
        img = self.bg.copy(self._src(r.normalized())).toImage().convertToFormat(QImage.Format_RGB888)
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        return np.frombuffer(img.constBits(), np.uint8, bpl * h).reshape(h, bpl)[:, :w * 3].reshape(h, w, 3).copy()

    def _ask_preview(self, it):
        if it.rect is None: return
        it.preview = None; self._seq += 1; self._req[self._seq] = it; self.preview.emit(self._seq, self.crop(it.rect))

    def set_preview(self, seq, text):
        it = self._req.pop(seq, None)
        if it is None or any(x is it for x in self._req.values()): return      # vùng này còn yêu cầu mới hơn đang chờ
        it.preview = text; self.update()

    # ---------- xong
    def save(self):
        regs, spk = self.result(); self.close(); self.saved.emit(regs, spk)

    def cancel(self): self.close(); self.cancelled.emit()

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
