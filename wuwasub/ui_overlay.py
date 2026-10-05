import ctypes, html, sys
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QRect, QEvent, QSize
from PySide6.QtGui import QColor, QPainter, QCursor, QFont
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QToolButton, QSizeGrip, QFrame, QMenu,
                               QPushButton, QApplication, QComboBox, QGraphicsEffect, QLayout)
from .textnorm import WORD_RE
from .dictionary import LANGS

FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool

def exclude_from_capture(widget, on=True):
    """Windows 10 2004+: cửa sổ vẫn hiện trên màn hình nhưng vô hình với mọi ảnh chụp (kể cả mss của app)
    -> đặt overlay đè lên vùng OCR không bị OCR đọc lại chính bản dịch."""
    if sys.platform != "win32" or not widget.isVisible(): return
    try: ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), 0x11 if on else 0)   # WDA_EXCLUDEFROMCAPTURE / WDA_NONE
    except Exception: pass

def outline_offsets(w):
    """Các điểm lệch tạo viền dày w px (gần tròn)."""
    return [(dx, dy) for dx in range(-w, w + 1) for dy in range(-w, w + 1) if (dx or dy) and dx * dx + dy * dy <= w * w + 1]

class OutlineEffect(QGraphicsEffect):
    """Viền đen quanh chữ kiểu phụ đề: vẽ bóng đen lệch quanh mọi hướng rồi vẽ chữ gốc đè lên."""
    def __init__(self, width, parent=None): super().__init__(parent); self.w = width; self.offs = outline_offsets(width)
    def boundingRectFor(self, r): return r.adjusted(-self.w, -self.w, self.w, self.w)
    def draw(self, p):
        pm = self.sourcePixmap(Qt.LogicalCoordinates, QPoint(), QGraphicsEffect.PadToEffectiveBoundingRect)
        if pm.isNull(): return
        off = self.boundingRect().topLeft().toPoint()            # PySide6 không trả offset -> tự tính
        sh = pm.copy(); q = QPainter(sh); q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        q.fillRect(QRect(0, 0, sh.width(), sh.height()), QColor(0, 0, 0, 230)); q.end()
        for dx, dy in self.offs: p.drawPixmap(off + QPoint(dx, dy), sh)
        p.drawPixmap(off, pm)

TOOLBAR = [("prev", "◀"), ("next", "▶"), ("pause", "⏸"), ("translate", "🌐"), ("rescan", "⟳"), ("clear", "⌫"), ("scan", "📷"),
           ("region", "⬚"), ("speaker", "👤"), ("subs", "📂"), ("glossary", "🏷"), ("vocab", "📖"), ("lock", "🔒")]   # chọn hiện/ẩn trong Cài đặt
RIGHT_BTNS = [("settings", "⚙"), ("hide", "—"), ("quit", "✕")]                                               # luôn hiện, ghim phải

# tooltip toolbar; hotkey (nếu có) được ghép vào lúc apply_style
TIPS = {"prev": "Câu trước", "next": "Câu sau", "pause": "Tạm dừng / tiếp tục nhận dạng", "translate": "Bật/tắt dịch (tắt = chỉ câu gốc để tra từ)",
        "rescan": "Quét lại vùng thoại", "clear": "Xóa chữ trên overlay", "scan": "Chụp & dịch 1 vùng (thư, bảng…)",
        "region": "Chọn vùng thoại", "speaker": "Chọn vùng tên nhân vật", "subs": "Bộ sub Việt hóa", "glossary": "Glossary (tên riêng, thuật ngữ)",
        "vocab": "Sổ từ", "lock": "Khóa overlay (chuột xuyên qua để chơi game)", "settings": "Cài đặt", "hide": "Ẩn overlay", "quit": "Thoát"}
BUSY = ("Đang", "Lỗi", "Chưa", "Không khớp", "Không đọc")          # trạng thái luôn hiện ở góc (nguồn dịch chỉ hiện khi rê chuột)

class FlowLayout(QLayout):
    """Xếp widget theo hàng, hết chỗ thì xuống dòng (toolbar không bị bóp khi overlay hẹp)."""
    def __init__(self, parent=None, spacing=2):
        super().__init__(parent); self.items = []; self.setSpacing(spacing); self.setContentsMargins(0, 0, 0, 0)
    def addItem(self, it): self.items.append(it)
    def count(self): return len(self.items)
    def itemAt(self, i): return self.items[i] if 0 <= i < len(self.items) else None
    def takeAt(self, i): return self.items.pop(i) if 0 <= i < len(self.items) else None
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, w): return self._place(QRect(0, 0, w, 0), True)
    def setGeometry(self, r): super().setGeometry(r); self._place(r, False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        s = QSize()
        for it in self.items: s = s.expandedTo(it.minimumSize())
        return s
    def _place(self, r, test):
        x, y, line_h, sp = r.x(), r.y(), 0, self.spacing()
        for it in self.items:
            if it.isEmpty(): continue
            h = it.sizeHint()
            if x > r.x() and x + h.width() > r.right() + 1: x, y, line_h = r.x(), y + line_h + sp, 0     # xuống dòng
            if not test: it.setGeometry(QRect(QPoint(x, y), h))
            x += h.width() + sp; line_h = max(line_h, h.height())
        return y + line_h - r.y()

def esc(s): return html.escape(s, quote=False)      # không mã hóa ' " (Qt không hiểu &#x27; -> bôi đen ra chuỗi lạ)

def tokens_html(text, link_color):
    """Text -> HTML với mỗi từ là 1 link w:<start>:<end>."""
    out, i = [], 0
    for m in WORD_RE.finditer(text):
        out.append(esc(text[i:m.start()]))
        out.append(f'<a href="w:{m.start()}:{m.end()}" style="color:{link_color};text-decoration:none">{esc(m.group())}</a>')
        i = m.end()
    out.append(esc(text[i:]))
    return "".join(out)

class Overlay(QWidget):
    word_hover = Signal(str, QPoint)           # word ("" = rời), vị trí con trỏ
    word_click = Signal(str, QPoint)
    phrase_action = Signal(str, str)           # action, phrase
    action = Signal(str)                       # prev/next/pause/region/vocab/glossary/subs/settings/quit/rescan

    def __init__(self, cfg):
        super().__init__(None, FLAGS); self.cfg = cfg; self.src = ""; self._tag = ""; self._auto = False; self._alt = False
        self.alt_t = QTimer(self, interval=60, timeout=self._poll_alt)        # đang khóa: giữ Alt -> overlay nhận chuột
        self.setAttribute(Qt.WA_TranslucentBackground); self.setMouseTracking(True)
        self.setAttribute(Qt.WA_AlwaysShowToolTips)          # cửa sổ Tool không focus: Windows mặc định không hiện tooltip
        self.setWindowTitle("WuWa Sub"); self.setMinimumSize(320, 90)
        v = QVBoxLayout(self); v.setContentsMargins(14, 6, 14, 8); v.setSpacing(3)
        # toolbar
        # toolbar: nút tùy chọn (cfg["toolbar"]) xếp tự xuống dòng bên trái; ⚙ — ✕ luôn ghim bên phải
        self.bar = QWidget(); hb = QHBoxLayout(self.bar); hb.setContentsMargins(0, 0, 0, 0); hb.setSpacing(6)
        left = QWidget(); flow = FlowLayout(left); right = QHBoxLayout(); right.setSpacing(2)
        self.btns = {}
        for key, txt in TOOLBAR + RIGHT_BTNS:
            b = QToolButton(); b.setText(txt); b.setAutoRaise(True); b.clicked.connect(lambda _=0, k=key: self.action.emit(k))
            (right if (key, txt) in RIGHT_BTNS else flow).addWidget(b); self.btns[key] = b
        self.status = QLabel(""); flow.addWidget(self.status)
        hb.addWidget(left, 1); hb.addLayout(right); hb.setAlignment(right, Qt.AlignTop)
        sp = self.bar.sizePolicy(); sp.setRetainSizeWhenHidden(True); self.bar.setSizePolicy(sp)   # ẩn vẫn giữ chỗ: chữ không xê dịch khi rê chuột
        v.addWidget(self.bar)
        self.speaker = QLabel(); self.src_lbl = QLabel(); self.vi = QLabel(); self.tag = QLabel(); self.tag.setToolTip("Nguồn bản dịch: Bộ sub / Gemini / OpenAI / Google Translate")
        for l in (self.speaker, self.src_lbl, self.vi): l.setWordWrap(True)
        self.src_lbl.setTextFormat(Qt.RichText)
        self.src_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.src_lbl.linkHovered.connect(self._hover); self.src_lbl.linkActivated.connect(self._click)
        self.src_lbl.installEventFilter(self)                 # bôi đen xong (thả chuột) -> dịch đoạn bôi đen
        self.src_lbl.setContextMenuPolicy(Qt.CustomContextMenu); self.src_lbl.customContextMenuRequested.connect(self._menu)
        self.vi.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.vi.setContextMenuPolicy(Qt.CustomContextMenu); self.vi.customContextMenuRequested.connect(self._menu_vi)
        v.addWidget(self.speaker); v.addWidget(self.src_lbl); v.addWidget(self.vi, 1)
        self.grip = QSizeGrip(self)
        foot = QHBoxLayout(); foot.addWidget(self.tag); foot.addStretch(1); foot.addWidget(self.grip, 0, Qt.AlignBottom | Qt.AlignRight)
        v.addLayout(foot)
        self.hide_bar = QTimer(self, singleShot=True, interval=1200, timeout=lambda: self._set_bar(False))
        self._drag = None
        g = cfg.get("overlay_geom")
        if not g:
            sc = QApplication.primaryScreen().availableGeometry()
            g = [sc.x() + sc.width() // 2 - 380, sc.y() + int(sc.height() * 0.70), 760, 150]
        self.base_h = g[3]; self._auto = True; self.setGeometry(QRect(*g)); self._auto = False   # base_h = cỡ người dùng đặt; khung tự giãn khi chữ dài
        self.bar.setVisible(False); self.apply_style()

    def apply_style(self):
        c = self.cfg
        self.setStyleSheet(f"""
            QLabel {{ color:{c['fg']}; }} QToolButton {{ color:{c['src_fg']}; border:none; padding:2px 5px; font-size:13px; }}
            QToolButton:hover {{ color:{c['accent']}; background:rgba(255,255,255,0.08); border-radius:4px; }}""")
        f = QFont(); f.setPointSize(int(c["font_size"])); self.vi.setFont(f)
        fs = QFont(); fs.setPointSize(int(c["src_font_size"])); self.src_lbl.setFont(fs); self.speaker.setFont(fs)
        self.speaker.setStyleSheet(f"color:{c['accent']}; font-weight:600")
        self.tag.setStyleSheet(f"color:{c['src_fg']}; font-size:10px"); self.status.setStyleSheet(f"color:{c['src_fg']}; font-size:10px")
        w = int(c["text_outline"])
        for l in (self.speaker, self.src_lbl, self.vi, self.tag): l.setGraphicsEffect(OutlineEffect(w, l) if w > 0 else None)
        self._apply_display(); self.update(); self._render_src()
        self.btns["translate"].setText("🌐" if c["translate"] else "🔤")
        for k, _ in TOOLBAR: self.btns[k].setVisible(k in c["toolbar"])           # nút ghim trên toolbar (Cài đặt → Giao diện)
        for k, b in self.btns.items():
            tip = TIPS.get(k, ""); hk = c["hotkeys"].get(k) or c["hotkeys"].get({"hide": "toggle"}.get(k, ""), "")
            if k == "translate": tip = "Đang dịch — bấm để tắt (chỉ câu gốc để tra từ)" if c["translate"] else "Đang TẮT dịch — bấm để bật"
            b.setToolTip(tip + (f"  [{hk}]" if hk else ""))
        self.set_locked(c["locked"]); self._fit(); exclude_from_capture(self, c["hide_from_capture"])

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        if self.cfg["show_frame"]: a = max(0.05, min(1.0, float(self.cfg["opacity"])))
        else: a = 0.35 if self.bar.isVisible() else 1 / 255     # không khung: gần trong suốt (alpha 0 thì Windows cho chuột xuyên qua), rê chuột thì hiện mờ để kéo/đổi cỡ
        col = QColor(self.cfg["bg"]); col.setAlphaF(a)
        p.setBrush(col); p.setPen(Qt.NoPen); p.drawRoundedRect(self.rect(), 10, 10)

    # ---- nội dung
    def show_line(self, speaker, src, vi, tag):
        self.speaker.setText(speaker or ""); self.speaker.setVisible(bool(speaker) and self.cfg["show_speaker"])
        if src != self.src: self.src = src; self._render_src()
        self.vi.setText(vi or ""); self._tag = tag or ""; self._tag_vis(); self._fit()

    def _tag_vis(self):
        """Nguồn dịch (Google/Gemini/Bộ sub…) chỉ hiện khi rê chuột; trạng thái đang dịch / lỗi thì luôn hiện."""
        self.tag.setText(self._tag if self.bar.isVisible() or self._tag.startswith(BUSY) else "")

    def _fit(self):
        """Khung tự giãn lên trên (giữ mép dưới) khi chữ dài, co về cỡ người dùng đặt khi chữ ngắn."""
        need = self.layout().totalHeightForWidth(self.width())          # toolbar ẩn vẫn giữ chỗ nên đã tính sẵn
        h = max(self.base_h, need)
        if h == self.height(): return
        g = self.geometry(); top = g.bottom() + 1 - h
        scr = QApplication.screenAt(g.center()) or QApplication.primaryScreen(); top = max(top, scr.availableGeometry().top())
        self._auto = True; self.setGeometry(g.x(), top, g.width(), h); self._auto = False

    def _render_src(self):   # bọc cả dòng để dấu câu (ngoài link) cùng màu với chữ
        self.src_lbl.setText(f"<span style='color:{self.cfg['src_fg']}'>{tokens_html(self.src, self.cfg['src_fg'])}</span>")

    def _word(self, href):
        try: _, a, b = href.split(":"); return self.src[int(a):int(b)]
        except ValueError: return ""

    def eventFilter(self, obj, e):
        if obj is self.src_lbl and e.type() == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton:
            QTimer.singleShot(0, self._selected)
        return super().eventFilter(obj, e)

    def _selected(self):
        sel = " ".join(self.src_lbl.selectedText().split())
        if len(sel) >= 2: self.phrase_action.emit("lookup", sel)

    def _hover(self, href): self.word_hover.emit(self._word(href) if href else "", QCursor.pos())
    def _click(self, href): self.word_click.emit(self._word(href), QCursor.pos())

    def _menu(self, pos):
        sel = self.src_lbl.selectedText().strip(); m = QMenu(self)
        if sel:
            for k, t in [("lookup", f"Tra «{sel[:30]}»"), ("vocab", "Lưu vào sổ từ"), ("keep", "Glossary: giữ nguyên"),
                         ("translate", "Glossary: dịch là…"), ("explain", "Giải nghĩa theo ngữ cảnh (AI)")]:
                m.addAction(t, lambda k=k: self.phrase_action.emit(k, sel))
            m.addSeparator()
        m.addAction("Copy câu gốc", lambda: QApplication.clipboard().setText(self.src))
        m.exec(self.src_lbl.mapToGlobal(pos))

    def _menu_vi(self, pos):
        m = QMenu(self); m.addAction("Copy bản dịch", lambda: QApplication.clipboard().setText(self.vi.text()))
        m.addAction("Dịch lại bằng máy", lambda: self.action.emit("retranslate")); m.exec(self.vi.mapToGlobal(pos))

    def set_click_through(self, on): self.cfg["click_through"] = on; self._apply_input()

    def passthrough_wanted(self):
        return bool((self.cfg["locked"] and not self._alt) or self.cfg["click_through"])

    def _apply_input(self):
        """Chuột xuyên qua overlay khi khóa (trừ lúc giữ Alt) hoặc bật click-through (không chắn chuột game)."""
        want = self.passthrough_wanted()
        if want: self.bar.setVisible(False)
        if sys.platform == "win32": self._passthrough(want); return
        if bool(self.windowFlags() & Qt.WindowTransparentForInput) != want:           # ngoài Windows: dùng flag Qt
            vis = self.isVisible(); self.setWindowFlag(Qt.WindowTransparentForInput, want)
            if vis: self.show()

    def set_paused(self, p): self.btns["pause"].setText("▶▶" if p else "⏸"); self.status.setText("Tạm dừng" if p else "")

    # ---- kéo thả / hover toolbar
    def showEvent(self, e): super().showEvent(e); exclude_from_capture(self, self.cfg["hide_from_capture"]); self._apply_input()

    def set_locked(self, on):
        self.grip.setVisible(not on)
        if on: self._set_bar(False)
        self.btns["lock"].setText("🔓" if on else "🔒"); self._apply_input()
        if on and self.cfg["alt_unlock"] and sys.platform == "win32": self.alt_t.start()
        else: self.alt_t.stop(); self._alt = False

    def _poll_alt(self):
        down = bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)            # VK_MENU
        if down == self._alt: return
        self._alt = down; self._apply_input()
        if not down: self._set_bar(False)

    def _passthrough(self, on):
        """Chuột xuyên qua bằng WS_EX_TRANSPARENT (+LAYERED). Không dùng flag Qt: Qt tự bỏ sự kiện chuột của cửa sổ
        mang flag đó nên giữ Alt cũng không bấm được, và đổi flag còn tạo lại cửa sổ (nháy)."""
        u32 = ctypes.windll.user32; hwnd = int(self.winId()); ex = u32.GetWindowLongW(hwnd, -20)
        u32.SetWindowLongW(hwnd, -20, (ex | 0x80020) if on else (ex & ~0x20))

    def _apply_display(self):
        """2 ngôn ngữ / chỉ bản dịch / chỉ 1 thứ, rê chuột vào overlay hiện thêm thứ còn lại."""
        c, h = self.cfg, self.bar.isVisible(); d, tr = c["display"], c["translate"]
        src = (not tr) or d in ("both", "src_hover") or (d == "vi_hover" and h)
        vi = tr and (d in ("both", "vi", "vi_hover") or (d == "src_hover" and h))
        if self.src_lbl.isVisibleTo(self) != src or self.vi.isVisibleTo(self) != vi:
            self.src_lbl.setVisible(src); self.vi.setVisible(vi); self._fit()

    def _set_bar(self, on):
        self.bar.setVisible(on); self._tag_vis(); self._apply_display(); self.update()

    def enterEvent(self, e):
        if self.cfg["locked"] and not self._alt: return     # khóa: rê chuột không hiện gì (giữ Alt thì được)
        self.hide_bar.stop(); self._set_bar(True)
    def leaveEvent(self, e): self.hide_bar.start()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and (not self.cfg["locked"] or self._alt): self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton: self.move(e.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, e): self._drag = None; self._save_geom()
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._auto: self.base_h = self.height(); self._save_geom(); self._fit()    # người dùng tự đổi cỡ
    def _save_geom(self):
        g = self.geometry(); self.cfg["overlay_geom"] = [g.x(), g.bottom() + 1 - self.base_h, g.width(), self.base_h]


class WordPopup(QFrame):
    act = Signal(str, str)                     # action, word
    lang_changed = Signal(str)                 # mã ngôn ngữ đích

    def __init__(self, cfg):
        super().__init__(None, FLAGS); self.cfg = cfg; self.word = ""; self.pinned = False
        self.setAttribute(Qt.WA_ShowWithoutActivating); self.setAttribute(Qt.WA_AlwaysShowToolTips); self.setObjectName("pop"); self.meta = self.raw = ""
        v = QVBoxLayout(self); v.setContentsMargins(10, 8, 10, 8)
        self.title = QLabel(); self.title.setTextFormat(Qt.RichText); self.anchor = QPoint()   # AutoText đoán sai -> hiện nguyên &#x27;
        self.lang = QComboBox(); self.lang.setToolTip("Ngôn ngữ dịch")
        for code, name in LANGS.items(): self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg["target_lang"])))
        self.lang.activated.connect(lambda _: self.lang_changed.emit(self.lang.currentData()))
        self.close_btn = QToolButton(); self.close_btn.setText("✕"); self.close_btn.setToolTip("Đóng"); self.close_btn.setAutoRaise(True)
        self.close_btn.clicked.connect(self.close_pop)
        th = QHBoxLayout(); th.addWidget(self.title, 1); th.addWidget(self.lang); th.addWidget(self.close_btn)
        self.body = QLabel(); self.body.setWordWrap(True); self.body.setTextFormat(Qt.RichText); self.body.setMaximumWidth(420); self.body.setMinimumWidth(260)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addLayout(th); v.addWidget(self.body)
        hb = QHBoxLayout(); hb.setSpacing(4)
        for k, t in [("vocab", "＋ Sổ từ"), ("keep", "Giữ nguyên"), ("translate", "Dịch là…"), ("explain", "AI ngữ cảnh")]:
            b = QPushButton(t); b.clicked.connect(lambda _=0, k=k: self.act.emit(k, self.word)); hb.addWidget(b)
        v.addLayout(hb)
        self.source = QLabel(); self.source.setAlignment(Qt.AlignRight); v.addWidget(self.source)   # nguồn tra: Google / offline / AI
        self.hide_t = QTimer(self, singleShot=True, interval=450, timeout=self._auto_hide); self.apply_style()

    def apply_style(self):
        c = self.cfg
        self.setStyleSheet(f"""QFrame#pop {{ background:{c['bg']}; border:1px solid {c['accent']}; border-radius:8px; }}
            QLabel {{ color:{c['fg']}; }} QPushButton {{ color:{c['fg']}; background:rgba(255,255,255,0.08); border:none;
            padding:3px 8px; border-radius:4px; font-size:11px; }} QPushButton:hover {{ background:{c['accent']}; color:#111; }}
            QComboBox {{ color:{c['fg']}; background:rgba(255,255,255,0.08); border:none; padding:2px 6px; font-size:11px; }}""")
        self.title.setStyleSheet(f"color:{c['accent']}; font-weight:600; font-size:14px")
        self.source.setStyleSheet(f"color:{c['src_fg']}; font-size:10px")
        self.close_btn.setStyleSheet(f"QToolButton {{ color:{c['src_fg']}; border:none; padding:0 4px; font-size:13px; }} QToolButton:hover {{ color:{c['accent']}; }}")

    def _set(self, meta, body):
        if meta is not None: self.meta = meta
        self.raw = body; self.body.setText(self.meta + f"<div>{body}</div>"); self.adjustSize()

    def show_for(self, word, head, meta, body_html, pos, pinned=False, source=""):
        self.word = word; self.pinned = pinned; self.anchor = pos; self.source.setText(source)
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.cfg["target_lang"])))
        self.title.setText(esc(word if len(word) <= 48 else word[:46] + "…") + (f" <span style='opacity:.6;font-weight:400'>→ {esc(head)}</span>" if head and head.lower() != word.lower() else ""))
        self._set(meta, body_html)
        scr = QApplication.screenAt(pos) or QApplication.primaryScreen(); a = scr.availableGeometry()
        x = min(max(a.x(), pos.x() - self.width() // 2), a.right() - self.width())
        y = pos.y() - self.height() - 14
        if y < a.y(): y = pos.y() + 20
        self.move(x, y); self.show(); self.raise_(); self.hide_t.stop()

    def set_body(self, word, body_html, meta=None):
        if word == self.word and self.isVisible(): self._set(meta, body_html)

    def request_hide(self):
        if not self.pinned: self.hide_t.start()
    def _auto_hide(self):
        if not self.underMouse() and not self.pinned and not self.lang.view().isVisible(): self.hide()
    def enterEvent(self, e): self.hide_t.stop()
    def leaveEvent(self, e):
        if not self.pinned: self.hide_t.start()
    def close_pop(self): self.pinned = False; self.hide()
    def showEvent(self, e): super().showEvent(e); exclude_from_capture(self, self.cfg["hide_from_capture"])
    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton: self.close_pop()
