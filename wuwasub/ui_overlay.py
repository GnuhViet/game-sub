import html
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QRect
from PySide6.QtGui import QColor, QPainter, QCursor, QFont
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QToolButton, QSizeGrip, QFrame, QMenu,
                               QPushButton, QApplication)
from .textnorm import WORD_RE

FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool

def tokens_html(text, link_color):
    """Text -> HTML với mỗi từ là 1 link w:<start>:<end>."""
    out, i = [], 0
    for m in WORD_RE.finditer(text):
        out.append(html.escape(text[i:m.start()]))
        out.append(f'<a href="w:{m.start()}:{m.end()}" style="color:{link_color};text-decoration:none">{html.escape(m.group())}</a>')
        i = m.end()
    out.append(html.escape(text[i:]))
    return "".join(out)

class Overlay(QWidget):
    word_hover = Signal(str, QPoint)           # word ("" = rời), vị trí con trỏ
    word_click = Signal(str, QPoint)
    phrase_action = Signal(str, str)           # action, phrase
    action = Signal(str)                       # prev/next/pause/region/vocab/glossary/subs/settings/quit/rescan

    def __init__(self, cfg):
        super().__init__(None, FLAGS); self.cfg = cfg; self.src = ""
        self.setAttribute(Qt.WA_TranslucentBackground); self.setMouseTracking(True)
        self.setWindowTitle("WuWa Sub"); self.setMinimumSize(320, 90)
        v = QVBoxLayout(self); v.setContentsMargins(14, 6, 14, 8); v.setSpacing(3)
        # toolbar
        self.bar = QWidget(); hb = QHBoxLayout(self.bar); hb.setContentsMargins(0, 0, 0, 0); hb.setSpacing(2)
        self.btns = {}
        for key, txt, tip in [("prev", "◀", "Câu trước"), ("next", "▶", "Câu sau"), ("pause", "⏸", "Tạm dừng/Tiếp tục"),
                              ("rescan", "⟳", "Quét lại"), ("region", "⬚", "Chọn vùng dịch"), ("speaker", "👤", "Chọn vùng tên nhân vật"),
                              ("subs", "📂", "Bộ sub"), ("glossary", "🏷", "Glossary"), ("vocab", "📖", "Sổ từ"),
                              ("settings", "⚙", "Cài đặt"), ("hide", "—", "Ẩn (hotkey để hiện lại)"), ("quit", "✕", "Thoát")]:
            b = QToolButton(); b.setText(txt); b.setToolTip(tip); b.setAutoRaise(True); b.clicked.connect(lambda _=0, k=key: self.action.emit(k))
            hb.addWidget(b); self.btns[key] = b
            if key == "rescan": hb.addSpacing(8)
        hb.addStretch(1)
        self.status = QLabel(""); hb.addWidget(self.status)
        v.addWidget(self.bar)
        self.speaker = QLabel(); self.src_lbl = QLabel(); self.vi = QLabel(); self.tag = QLabel()
        for l in (self.speaker, self.src_lbl, self.vi): l.setWordWrap(True)
        self.src_lbl.setTextFormat(Qt.RichText)
        self.src_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.src_lbl.linkHovered.connect(self._hover); self.src_lbl.linkActivated.connect(self._click)
        self.src_lbl.setContextMenuPolicy(Qt.CustomContextMenu); self.src_lbl.customContextMenuRequested.connect(self._menu)
        self.vi.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.vi.setContextMenuPolicy(Qt.CustomContextMenu); self.vi.customContextMenuRequested.connect(self._menu_vi)
        v.addWidget(self.speaker); v.addWidget(self.src_lbl); v.addWidget(self.vi, 1)
        foot = QHBoxLayout(); foot.addWidget(self.tag); foot.addStretch(1); foot.addWidget(QSizeGrip(self), 0, Qt.AlignBottom | Qt.AlignRight)
        v.addLayout(foot)
        self.hide_bar = QTimer(self, singleShot=True, interval=1200, timeout=lambda: self.bar.setVisible(False))
        self._drag = None; self.apply_style()
        g = cfg.get("overlay_geom")
        if g: self.setGeometry(QRect(*g))
        else:
            sc = QApplication.primaryScreen().availableGeometry()
            self.setGeometry(sc.x() + sc.width() // 2 - 380, sc.y() + int(sc.height() * 0.70), 760, 150)
        self.bar.setVisible(False)

    def apply_style(self):
        c = self.cfg
        self.setStyleSheet(f"""
            QLabel {{ color:{c['fg']}; }} QToolButton {{ color:{c['src_fg']}; border:none; padding:2px 5px; font-size:13px; }}
            QToolButton:hover {{ color:{c['accent']}; background:rgba(255,255,255,0.08); border-radius:4px; }}""")
        f = QFont(); f.setPointSize(int(c["font_size"])); self.vi.setFont(f)
        fs = QFont(); fs.setPointSize(int(c["src_font_size"])); self.src_lbl.setFont(fs); self.speaker.setFont(fs)
        self.speaker.setStyleSheet(f"color:{c['accent']}; font-weight:600")
        self.tag.setStyleSheet(f"color:{c['src_fg']}; font-size:10px"); self.status.setStyleSheet(f"color:{c['src_fg']}; font-size:10px")
        self.src_lbl.setVisible(c["show_source"]); self.update(); self._render_src()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        col = QColor(self.cfg["bg"]); col.setAlphaF(max(0.05, min(1.0, float(self.cfg["opacity"]))))
        p.setBrush(col); p.setPen(Qt.NoPen); p.drawRoundedRect(self.rect(), 10, 10)

    # ---- nội dung
    def show_line(self, speaker, src, vi, tag):
        self.speaker.setText(speaker or ""); self.speaker.setVisible(bool(speaker) and self.cfg["show_speaker"])
        if src != self.src: self.src = src; self._render_src()
        self.vi.setText(vi or ""); self.tag.setText(tag or "")

    def _render_src(self): self.src_lbl.setText(tokens_html(self.src, self.cfg["src_fg"]))

    def _word(self, href):
        try: _, a, b = href.split(":"); return self.src[int(a):int(b)]
        except ValueError: return ""

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

    def set_click_through(self, on):
        vis = self.isVisible(); self.setWindowFlag(Qt.WindowTransparentForInput, on)   # đổi flag làm ẩn cửa sổ
        if on: self.bar.setVisible(False)
        if vis: self.show()

    def set_paused(self, p): self.btns["pause"].setText("▶▶" if p else "⏸"); self.status.setText("Tạm dừng" if p else "")

    # ---- kéo thả / hover toolbar
    def enterEvent(self, e): self.hide_bar.stop(); self.bar.setVisible(True)
    def leaveEvent(self, e): self.hide_bar.start()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton: self.move(e.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, e): self._drag = None; self._save_geom()
    def resizeEvent(self, e): super().resizeEvent(e); self._save_geom()
    def _save_geom(self): g = self.geometry(); self.cfg["overlay_geom"] = [g.x(), g.y(), g.width(), g.height()]


class WordPopup(QFrame):
    act = Signal(str, str)                     # action, word

    def __init__(self, cfg):
        super().__init__(None, FLAGS); self.cfg = cfg; self.word = ""; self.pinned = False
        self.setAttribute(Qt.WA_ShowWithoutActivating); self.setObjectName("pop"); self.meta = self.raw = ""
        v = QVBoxLayout(self); v.setContentsMargins(10, 8, 10, 8)
        self.title = QLabel()
        self.body = QLabel(); self.body.setWordWrap(True); self.body.setTextFormat(Qt.RichText); self.body.setMaximumWidth(420); self.body.setMinimumWidth(260)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.title); v.addWidget(self.body)
        hb = QHBoxLayout(); hb.setSpacing(4)
        for k, t in [("vocab", "＋ Sổ từ"), ("keep", "Giữ nguyên"), ("translate", "Dịch là…"), ("explain", "AI ngữ cảnh")]:
            b = QPushButton(t); b.clicked.connect(lambda _=0, k=k: self.act.emit(k, self.word)); hb.addWidget(b)
        v.addLayout(hb)
        self.hide_t = QTimer(self, singleShot=True, interval=450, timeout=self._auto_hide); self.apply_style()

    def apply_style(self):
        c = self.cfg
        self.setStyleSheet(f"""QFrame#pop {{ background:{c['bg']}; border:1px solid {c['accent']}; border-radius:8px; }}
            QLabel {{ color:{c['fg']}; }} QPushButton {{ color:{c['fg']}; background:rgba(255,255,255,0.08); border:none;
            padding:3px 8px; border-radius:4px; font-size:11px; }} QPushButton:hover {{ background:{c['accent']}; color:#111; }}""")
        self.title.setStyleSheet(f"color:{c['accent']}; font-weight:600; font-size:14px")

    def _set(self, meta, body):
        if meta is not None: self.meta = meta
        self.raw = body; self.body.setText(self.meta + f"<div>{body}</div>"); self.adjustSize()

    def show_for(self, word, head, meta, body_html, pos, pinned=False):
        self.word = word; self.pinned = pinned
        self.title.setText(html.escape(word) + (f" <span style='opacity:.6;font-weight:400'>→ {html.escape(head)}</span>" if head and head.lower() != word.lower() else ""))
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
        if not self.underMouse() and not self.pinned: self.hide()
    def enterEvent(self, e): self.hide_t.stop()
    def leaveEvent(self, e):
        if not self.pinned: self.hide_t.start()
    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton: self.pinned = False; self.hide()
