"""Cửa sổ "Chụp & dịch 1 vùng": OCR một lần vùng tùy ý (thư, bảng thông tin…), hiện câu gốc (hover tra từ) + bản dịch."""
from PySide6.QtCore import Qt, Signal, QPoint, QUrl, QEvent, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QSplitter, QPushButton, QLabel, QApplication
from .ui_overlay import tokens_html, exclude_from_capture
from .i18n import tr

class ScanWindow(QWidget):
    word_hover = Signal(str, QPoint)
    word_click = Signal(str, QPoint)
    action = Signal(str)                         # rescan / retranslate

    def __init__(self, cfg):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint); self.cfg = cfg; self.src = ""; self.setAttribute(Qt.WA_AlwaysShowToolTips)
        self.setWindowTitle(tr("Dịch vùng — hover từ để tra nghĩa")); self.resize(620, 560)
        v = QVBoxLayout(self); v.setContentsMargins(8, 8, 8, 8)
        self.src_view = QTextBrowser(); self.src_view.setOpenLinks(False)
        self.src_view.highlighted.connect(lambda u: self.word_hover.emit(self._word(u), QCursor.pos()))
        self.src_view.anchorClicked.connect(lambda u: self.word_click.emit(self._word(u), QCursor.pos()))
        self.src_view.viewport().installEventFilter(self)      # bôi đen xong -> dịch đoạn bôi đen
        self.vi_view = QTextBrowser()
        sp = QSplitter(Qt.Vertical); sp.addWidget(self.src_view); sp.addWidget(self.vi_view); v.addWidget(sp, 1)
        hb = QHBoxLayout(); self.tag = QLabel(); hb.addWidget(self.tag, 1)
        for k, t in [("scan", tr("📷 Chụp lại")), ("scan_retranslate", tr("Dịch lại")), ("copy", tr("Copy")), ("close", tr("Đóng"))]:
            b = QPushButton(t); b.clicked.connect(lambda _=0, k=k: self._btn(k)); hb.addWidget(b)
        v.addLayout(hb); self.apply_style()

    def eventFilter(self, obj, e):
        if obj is self.src_view.viewport() and e.type() == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton:
            QTimer.singleShot(0, self._selected)
        return super().eventFilter(obj, e)

    def _selected(self):
        sel = " ".join(self.src_view.textCursor().selectedText().split())     # split() bỏ cả U+2029 xuống đoạn
        if len(sel) >= 2: self.word_click.emit(sel, QCursor.pos())

    def showEvent(self, e): super().showEvent(e); exclude_from_capture(self, self.cfg["hide_from_capture"])

    def apply_style(self):
        c = self.cfg
        self.setStyleSheet(f"""QWidget {{ background:{c['bg']}; color:{c['fg']}; }}
            QTextBrowser {{ border:1px solid rgba(255,255,255,0.12); border-radius:6px; padding:6px; }}
            QPushButton {{ background:rgba(255,255,255,0.08); border:none; padding:4px 10px; border-radius:4px; }}
            QPushButton:hover {{ background:{c['accent']}; color:#111; }} QLabel {{ color:{c['src_fg']}; font-size:11px; }}""")
        self.src_view.setStyleSheet(f"font-size:{int(c['src_font_size']) + 2}pt;"); self.vi_view.setStyleSheet(f"font-size:{int(c['font_size'])}pt;")
        self._render_src()

    def _btn(self, k):
        if k == "copy": QApplication.clipboard().setText(self.src + "\n\n" + self.vi_view.toPlainText())
        elif k == "close": self.hide()
        else: self.action.emit(k)

    def _word(self, url: QUrl):
        try: _, a, b = url.toString().split(":"); return self.src[int(a):int(b)]
        except ValueError: return ""

    def _render_src(self):
        body = tokens_html(self.src, self.cfg['src_fg']).replace("\n", "<br><br>")        # giữ chia đoạn
        self.src_view.setHtml(f"<div style='color:{self.cfg['src_fg']}'>{body}</div>")

    def show_result(self, src, vi, tag):
        if src != self.src: self.src = src; self._render_src()
        self.vi_view.setPlainText(vi.replace("\n", "\n\n")); self.tag.setText(tag)
        if not self.isVisible(): self.show()
        self.raise_()
