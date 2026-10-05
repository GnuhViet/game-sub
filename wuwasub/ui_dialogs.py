import random, html, time
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient
from PySide6.QtWidgets import (QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QComboBox, QPlainTextEdit, QDialogButtonBox, QPushButton, QListWidget, QFileDialog, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QAbstractItemView, QProgressDialog, QSlider, QColorDialog, QGroupBox, QGridLayout)
from . import importer, engines
from .dictionary import LANGS
from .ui_overlay import outline_offsets, TOOLBAR, TIPS

DIALOG_ENGINES = {"google": "Google Translate (nhanh, free)", "gemini_google": "Gemini AI (hiểu ngữ cảnh) — lỗi/hết quota thì Google",
                  "gemini": "Chỉ Gemini AI"}
SCAN_ENGINES = {"ocr_google": "OCR + Google Translate", "ocr_gemini": "OCR + Gemini AI (lỗi thì Google)",
                "gemini_image": "Gemini AI đọc thẳng ảnh (chính xác nhất; lỗi thì OCR + Google)"}

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None, on_preview=None):
        super().__init__(parent); self.cfg = cfg; self.on_preview = on_preview; self.w = {}; self._snap = {k: cfg[k] for k in self.LIVE}; self.setWindowTitle("Cài đặt"); self.resize(620, 560)
        tabs = QTabWidget(); v = QVBoxLayout(self); v.addWidget(tabs)
        # --- OCR
        f = self._tab(tabs, "OCR")
        self._combo(f, "ocr_engine", "Engine", {"windows": "Windows OCR (nhẹ, khuyên dùng)", "rapidocr": "RapidOCR (offline, chính xác hơn)", "tesseract": "Tesseract"})
        self._line(f, "ocr_lang", "Ngôn ngữ OCR", "en-US / ja / zh-Hans-CN / ko …")
        self._dspin(f, "ocr_scale", "Phóng to ảnh trước OCR", 0.5, 4, 0.25)
        self._spin(f, "interval_ms", "Chu kỳ chụp (ms)", 50, 2000)
        self._spin(f, "stable_ms", "Chờ chữ ổn định (ms)", 0, 3000)
        self._dspin(f, "diff_threshold", "Ngưỡng thay đổi ảnh", 0.2, 50, 0.5)
        self._spin(f, "dedupe_ratio", "Bỏ qua nếu giống câu trước ≥ (%)", 50, 100)
        self.app_combo = QComboBox(); self.app_combo.setEditable(True); self.app_combo.setMinimumWidth(260)
        ref = QPushButton("Làm mới"); ref.clicked.connect(self._load_apps); self._load_apps()
        hb = QHBoxLayout(); hb.addWidget(self.app_combo, 1); hb.addWidget(ref); f.addRow("Chỉ dịch khi đang mở app", hb)
        self.w["target_app"] = (self.app_combo, self._app_value)
        self._check(f, "clear_on_empty", "Tự xóa chữ khi vùng thoại không còn chữ")
        self._check(f, "fix_spacing", "Tự tách từ bị dính (youfinallywoke → you finally woke)")
        f.addRow(QLabel("<i>Vùng dịch / vùng tên nhân vật chọn bằng nút ⬚ / 👤 trên overlay.</i>"))
        self.btn_snap = QPushButton("Lưu ảnh vùng hiện tại để kiểm tra"); f.addRow(self.btn_snap)
        # quản lý OCR engine tải thêm: trạng thái + dung lượng, Tải / Xóa
        self.installed = False; self.eng_rows = {}
        g = self._group(f, "OCR engine tải thêm (Windows OCR có sẵn, không cần tải)")
        for key, name, dl in [("rapidocr", "RapidOCR", "~80 MB"), ("tesseract", "Tesseract", "~50 MB")]:
            st = QLabel(); bi = QPushButton(); bd = QPushButton("Xóa")
            bi.clicked.connect(lambda _=0, k=key: self._install(k)); bd.clicked.connect(lambda _=0, k=key: self._remove(k))
            hb = QHBoxLayout(); hb.addWidget(st, 1); hb.addWidget(bi); hb.addWidget(bd); g.addRow(name, hb); self.eng_rows[key] = (st, bi, bd, dl)
        self.eng_status = QLabel(); self.eng_status.setWordWrap(True); g.addRow(self.eng_status)
        self._eng_refresh()
        # --- Dịch
        tab = self._tab(tabs, "Dịch")
        f = self._group(tab, "Dịch thoại (overlay)")
        self._check(f, "translate", "Bật dịch (tắt = chỉ hiện câu gốc để tra từ)")
        self._check(f, "use_subs", "Ưu tiên bộ sub Việt hóa (khớp thì dùng luôn)"); self._spin(f, "fuzzy_threshold", "Ngưỡng khớp sub (%)", 50, 100)
        self._combo(f, "dialog_engine", "Không khớp sub thì dịch bằng", DIALOG_ENGINES)
        f = self._group(tab, "Dịch vùng chụp 📷 (thư, bảng…)")
        self._combo(f, "scan_engine", "Dịch bằng", SCAN_ENGINES)
        f = self._group(tab, "Gemini AI — chỉ dùng khi chọn Gemini ở trên")
        self.gem_warn = QLabel(); self.gem_warn.setWordWrap(True); self.gem_warn.setStyleSheet("color:#e8a33a"); f.addRow(self.gem_warn)
        self._line(f, "gemini_key", "API key (free: aistudio.google.com)", password=True)
        self.model = QComboBox(); self.model.setEditable(True); self.model.addItem(cfg["gemini_model"]); self.model.setToolTip("Bấm «Kiểm tra key» để lấy danh sách model key dùng được")
        f.addRow("Model", self.model); self.w["gemini_model"] = (self.model, lambda: self.model.currentText().strip())
        bt = QPushButton("Kiểm tra key"); self.key_status = QLabel(); self.key_status.setWordWrap(True); bt.clicked.connect(self._test_key)
        hb = QHBoxLayout(); hb.addWidget(bt); hb.addWidget(self.key_status, 1); f.addRow(hb)
        for k in ("dialog_engine", "scan_engine"): self.w[k][0].currentIndexChanged.connect(self._gem_warn)
        self.w["gemini_key"][0].textChanged.connect(self._gem_warn); self._gem_warn()
        self._spin(f, "context_lines", "Số câu thoại trước làm ngữ cảnh", 0, 20); self._check(f, "keep_terms", "Không dịch tên riêng / thuật ngữ")
        self._check(f, "stream", "Hiện chữ dần khi đang dịch (streaming)")
        self._spin(f, "gemini_thinking_budget", "Thinking budget (0 = nhanh nhất, -1 = mặc định)", -1, 8192)
        self._spin(f, "timeout_s", "Timeout (s)", 3, 120); self._spin(f, "cooldown_s", "Hết quota (429) thì nghỉ Gemini (s)", 0, 3600)
        self._src_lang = self._line(f, "src_lang", "Ngôn ngữ gốc (mô tả cho AI)")
        # --- Prompt
        t = QWidget(); tv = QVBoxLayout(t); tabs.addTab(t, "Prompt")
        tv.addWidget(QLabel("Biến: {src_lang} {player} {gender} {keep_rule} {glossary}"))
        self.prompt = QPlainTextEdit(cfg["prompt"]); tv.addWidget(self.prompt)
        tv.addWidget(QLabel("Prompt giải nghĩa từ — biến: {word} {sentence}")); self.explain = QPlainTextEdit(cfg["explain_prompt"]); tv.addWidget(self.explain)
        # --- Nhân vật
        f = self._tab(tabs, "Nhân vật")
        self._line(f, "player_name", "Tên Rover trong game"); self._combo(f, "gender", "Giới tính Rover", {"male": "Nam", "female": "Nữ"})
        self.tokens = QLineEdit(", ".join(cfg["name_tokens"])); f.addRow("Placeholder tên trong file sub", self.tokens)
        f.addRow(QLabel("<i>Macro giới tính dạng {Male=he;Female=she} được tự xử lý.</i>"))
        # --- Từ điển
        f = self._tab(tabs, "Từ điển")
        self._combo(f, "dict_mode", "Nguồn nghĩa khi hover", {"auto": "Offline → Google dịch tự động", "google": "Google dịch tự động", "offline": "Chỉ offline", "online": "Online (Anh-Anh, dictionaryapi.dev)", "llm": "AI theo ngữ cảnh (tốn quota)"})
        self._combo(f, "target_lang", "Ngôn ngữ dịch (Google)", LANGS)
        self._spin(f, "hover_delay_ms", "Độ trễ hover (ms)", 0, 2000)
        self.dicts = QListWidget(); self.dicts.addItems(cfg["dict_files"]); f.addRow("File từ điển", self.dicts)
        hb = QHBoxLayout(); a = QPushButton("Thêm…"); d = QPushButton("Xóa"); hb.addWidget(a); hb.addWidget(d); hb.addStretch(1); f.addRow(hb)
        a.clicked.connect(self._add_dict); d.clicked.connect(lambda: [self.dicts.takeItem(self.dicts.row(i)) for i in self.dicts.selectedItems()])
        f.addRow(QLabel("<i>Hỗ trợ StarDict (.ifo + .idx + .dict/.dict.dz), TSV/CSV (từ⇥nghĩa), JSON {từ: nghĩa}.</i>"))
        # --- Giao diện
        f = self._tab(tabs, "Giao diện")
        self._spin(f, "font_size", "Cỡ chữ bản dịch", 8, 48); self._spin(f, "src_font_size", "Cỡ chữ câu gốc", 8, 40)
        # khung / màu / độ trong suốt: đổi là overlay + ô xem trước cập nhật ngay; Cancel thì trả lại
        self.prev = _Preview(cfg); f.addRow(self.prev)
        c = self._check(f, "show_frame", "Hiện khung nền"); c.toggled.connect(lambda on: self._live("show_frame", on))
        s = self._spin(f, "text_outline", "Độ dày viền chữ (px, 0 = tắt)", 0, 4); s.valueChanged.connect(lambda v: self._live("text_outline", v))
        sl = QSlider(Qt.Horizontal); sl.setRange(0, 95); sl.setValue(round((1 - float(cfg["opacity"])) * 100))
        pct = QLabel(f"{sl.value()}%"); pct.setMinimumWidth(44)
        sl.valueChanged.connect(lambda t: (pct.setText(f"{t}%"), self._live("opacity", round(1 - t / 100, 2))))
        hb = QHBoxLayout(); hb.addWidget(sl, 1); hb.addWidget(pct); f.addRow("Độ trong suốt khung", hb)
        self.w["opacity"] = (sl, lambda: round(1 - sl.value() / 100, 2))
        for k, n in [("bg", "Màu khung"), ("fg", "Màu chữ dịch"), ("src_fg", "Màu câu gốc"), ("accent", "Màu nhấn (tên, viền popup)")]: self._color(f, k, n)
        g = QGroupBox("Nút trên toolbar (⚙ Cài đặt, — Ẩn, ✕ Thoát luôn ghim bên phải)"); gl = QGridLayout(g); tb = {}
        for i, (k, icon) in enumerate(TOOLBAR):
            cb = QCheckBox(f"{icon}  {TIPS[k].split(' (')[0]}".replace("&", "&&")); cb.setChecked(k in cfg["toolbar"]); gl.addWidget(cb, i // 2, i % 2); tb[k] = cb
        f.addRow(g); self.w["toolbar"] = (g, lambda: [k for k, _ in TOOLBAR if tb[k].isChecked()])
        self._check(f, "hide_from_capture", "Overlay vô hình với ảnh chụp: đặt đè lên vùng OCR được (quay/stream/chụp màn hình cũng không thấy overlay)")
        self._dspin(f, "auto_hide_s", "Tự ẩn khi hết thoại sau (s, 0 = tắt)", 0, 60, 0.5)
        self._combo(f, "show_source", "Hiển thị", {True: "2 ngôn ngữ (câu gốc + bản dịch)", False: "1 ngôn ngữ (chỉ bản dịch)"}); self._check(f, "show_speaker", "Hiện tên nhân vật")
        # --- Hotkey
        f = self._tab(tabs, "Hotkey"); self.hk = {}
        for k, n in [("toggle", "Ẩn/hiện overlay"), ("region", "Chọn vùng"), ("pause", "Tạm dừng"), ("rescan", "Quét lại"), ("clickthrough", "Click-through"), ("clear", "Xóa chữ"), ("translate", "Bật/tắt dịch"), ("scan", "Chụp & dịch 1 vùng"), ("lock", "Khóa/mở overlay")]:
            e = QLineEdit(cfg["hotkeys"].get(k, "")); f.addRow(n, e); self.hk[k] = e
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); v.addWidget(bb)

    LIVE = ("opacity", "bg", "fg", "src_fg", "accent", "show_frame", "text_outline")

    def _live(self, k, v):
        self.cfg[k] = v; self.prev.update()
        if self.on_preview: self.on_preview()

    def reject(self):
        self.cfg.update(self._snap)
        if self.on_preview: self.on_preview()
        super().reject()

    def _color(self, f, k, label):
        b = QPushButton(); b.setMinimumWidth(120)
        def show(hexc): b.setText(hexc); b.setStyleSheet(f"background:{hexc}; color:{'#111' if QColor(hexc).lightness() > 140 else '#f2f2f2'}; border:1px solid #555; padding:4px")
        def pick():
            col = QColorDialog.getColor(QColor(b.text()), self, label)
            if col.isValid(): show(col.name()); self._live(k, col.name())
        show(self.cfg[k]); b.clicked.connect(pick); f.addRow(label, b); self.w[k] = (b, b.text)

    def _tab(self, tabs, name):
        w = QWidget(); f = QFormLayout(w); tabs.addTab(w, name); return f
    def _group(self, f, title):
        g = QGroupBox(title); gf = QFormLayout(g); f.addRow(g); return gf
    def _line(self, f, k, label, ph="", password=False):
        e = QLineEdit(str(self.cfg[k] or "")); e.setPlaceholderText(ph)
        if password: e.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        f.addRow(label, e); self.w[k] = (e, lambda e=e: e.text().strip()); return e
    def _spin(self, f, k, label, lo, hi):
        s = QSpinBox(); s.setRange(lo, hi); s.setValue(int(self.cfg[k])); f.addRow(label, s); self.w[k] = (s, s.value); return s
    def _dspin(self, f, k, label, lo, hi, step):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step); s.setValue(float(self.cfg[k])); f.addRow(label, s); self.w[k] = (s, s.value)
    def _check(self, f, k, label):
        c = QCheckBox(label); c.setChecked(bool(self.cfg[k])); f.addRow(c); self.w[k] = (c, c.isChecked); return c
    def _combo(self, f, k, label, opts):
        c = QComboBox()
        for key, txt in opts.items(): c.addItem(txt, key)
        c.setCurrentIndex(max(0, c.findData(self.cfg[k]))); f.addRow(label, c); self.w[k] = (c, c.currentData)

    def _eng_refresh(self):
        ok = {"rapidocr": engines.has_rapidocr(), "tesseract": bool(engines.tesseract_exe())}
        pend = engines.pending()
        for k, (st, bi, bd, dl) in self.eng_rows.items():
            if {"rapidocr": "py", "tesseract": "tesseract"}[k] in pend:
                st.setText("sẽ xóa khi khởi động lại app"); bi.setEnabled(False); bd.setEnabled(False); continue
            st.setText(f"✓ đã cài — {engines.size_mb(k):.0f} MB trên đĩa" if ok[k] else "chưa cài")
            bi.setText("Tải lại" if ok[k] else f"Tải ({dl})"); bd.setEnabled(ok[k])
        self.eng_status.setText(f"<i>Nằm trong {html.escape(str(engines.ENG_DIR))}</i>")

    def _load_apps(self):
        """App đang có cửa sổ mở (WuWa: client-win64-shipping.exe) + giá trị đang lưu."""
        from . import winapp
        cur = self._app_value() if self.app_combo.count() else self.cfg["target_app"]
        c = self.app_combo; c.clear(); c.addItem("Mọi cửa sổ (không lọc)", "")
        apps = dict(winapp.windows())
        if cur and cur not in apps: apps[cur] = "(chưa mở)"
        for exe, title in sorted(apps.items()): c.addItem(f"{exe} — {title[:40]}", exe)
        c.setCurrentIndex(max(0, c.findData(cur)))

    def _app_value(self):
        c = self.app_combo; t = c.currentText().strip()
        if c.currentIndex() >= 0 and t == c.itemText(c.currentIndex()): return c.currentData() or ""
        return t.split(" — ")[0].strip().lower()                              # gõ tay tên exe

    def _gem_warn(self):
        uses = [n for k, n in (("dialog_engine", "dịch thoại"), ("scan_engine", "dịch vùng chụp")) if "gemini" in (self.w[k][1]() or "")]
        no_key = not self.w["gemini_key"][1]()
        self.gem_warn.setText(f"⚠ Đang chọn Gemini cho {' và '.join(uses)} nhưng chưa có API key → sẽ dùng Google." if uses and no_key else "")
        self.gem_warn.setVisible(bool(uses and no_key))

    def _test_key(self):
        key, model = self.w["gemini_key"][1](), self.w["gemini_model"][1]()
        if not key: self.key_status.setText("⚠ Chưa nhập key"); return
        from .translator import Translator
        c = dict(self.cfg); c.update(gemini_key=key, gemini_model=model, stream=False, timeout_s=20)
        res = {}; self.key_status.setText("Đang thử…")
        def work(_):     # 1) lấy danh sách model (cũng là kiểm tra key)  2) model đang chọn không có -> tự chọn  3) gọi thử
            t = Translator(c, None); res["models"] = t.list_models(key)
            if res["models"] and model not in res["models"]: c["gemini_model"] = res["picked"] = Translator.pick_model(res["models"])
            t0 = time.time(); t.gemini("", "Reply with exactly one word: OK", None); res["t"] = time.time() - t0
        job = _Job(work)
        def done(err):
            if res.get("models"):
                cur = res.get("picked") or model; self.model.clear(); self.model.addItems(res["models"]); self.model.setCurrentText(cur)
            note = f"«{html.escape(model)}» không còn → đã chọn «{html.escape(res['picked'])}». " if res.get("picked") else ""
            if err: self.key_status.setText(f"<span style='color:#e86a6a'>{note}✗ {html.escape(err.split(': ', 1)[-1])}</span>")
            else: self.key_status.setText(f"<span style='color:#7bd88f'>{note}✓ Key dùng được — {html.escape(c['gemini_model'])} trả lời sau {res['t']:.1f}s. Bấm OK để lưu.</span>")
        job.done.connect(done); self._key_job = job; job.start()

    def _remove(self, key):
        name = {"rapidocr": "RapidOCR", "tesseract": "Tesseract"}[key]
        if QMessageBox.question(self, "Xóa OCR engine", f"Xóa {name} ({engines.size_mb(key):.0f} MB)?") != QMessageBox.Yes: return
        now = engines.remove(key); combo = self.w["ocr_engine"][0]
        if combo.currentData() == key: combo.setCurrentIndex(combo.findData("windows"))     # đang chọn engine bị xóa -> về Windows OCR
        self.installed = True; self._eng_refresh()
        if not now: QMessageBox.information(self, "Xóa OCR engine", f"{name} đang được dùng — sẽ xóa hẳn khi khởi động lại app.")

    def _install(self, key):
        dlg = QProgressDialog("Đang tải…", "Hủy", 0, 100, self); dlg.setWindowTitle("Tải OCR engine"); dlg.setMinimumWidth(420)
        dlg.setWindowModality(Qt.WindowModal); dlg.setAutoClose(False); dlg.setAutoReset(False); dlg.show()
        job = _Job(engines.install_rapidocr if key == "rapidocr" else engines.install_tesseract)
        job.progress.connect(lambda t, p: (dlg.setLabelText(t), dlg.setValue(p)))
        dlg.canceled.connect(lambda: setattr(job, "cancel", True))
        def done(err):
            dlg.close(); self._eng_refresh()
            if err == "cancel": return
            if err: QMessageBox.warning(self, "Tải OCR engine", f"Lỗi: {err}"); return
            self.installed = True; i = self.w["ocr_engine"][0].findData(key)
            if i >= 0: self.w["ocr_engine"][0].setCurrentIndex(i)
            QMessageBox.information(self, "Tải OCR engine", "Đã cài xong. Bấm OK ở Cài đặt để dùng.")
        job.done.connect(done); self._job = job; job.start()

    def _add_dict(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Chọn từ điển", "", "Từ điển (*.ifo *.tsv *.txt *.csv *.json)")
        for x in fs: self.dicts.addItem(x)

    def apply(self):
        c = self.cfg
        for k, (_, get) in self.w.items(): c[k] = get()
        c["prompt"], c["explain_prompt"] = self.prompt.toPlainText(), self.explain.toPlainText()
        c["name_tokens"] = [x.strip() for x in self.tokens.text().split(",") if x.strip()]
        c["dict_files"] = [self.dicts.item(i).text() for i in range(self.dicts.count())]
        c["hotkeys"] = {k: e.text().strip() for k, e in self.hk.items()}
        c.save()


class _Preview(QWidget):
    """Nền giả lập cảnh game (sáng/tối/nhiều màu) + khung thoại mẫu theo cài đặt hiện tại (đọc thẳng từ cfg)."""
    def __init__(self, cfg):
        super().__init__(); self.cfg = cfg; self.setMinimumHeight(86)

    def _text(self, p, rect, flags, text, color):
        if int(self.cfg["text_outline"]):
            p.setPen(QColor(0, 0, 0, 230))
            for dx, dy in outline_offsets(int(self.cfg["text_outline"])): p.drawText(rect.translated(dx, dy), flags, text)
        p.setPen(QColor(color)); p.drawText(rect, flags, text)

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); r = self.rect()
        g = QLinearGradient(0, 0, r.width(), 0)
        for pos, col in [(0, "#f4f1e8"), (0.3, "#7fb7e6"), (0.55, "#3c7a3a"), (0.8, "#d9a441"), (1, "#141414")]: g.setColorAt(pos, QColor(col))
        p.fillRect(r, g)
        for x in range(0, r.width(), 40): p.fillRect(x, 0, 14, r.height(), QColor(255, 255, 255, 60))   # sọc chi tiết nền
        box = r.adjusted(18, 14, -18, -14)
        if self.cfg["show_frame"]:
            col = QColor(self.cfg["bg"]); col.setAlphaF(max(0.05, float(self.cfg["opacity"])))
            p.setBrush(col); p.setPen(Qt.NoPen); p.drawRoundedRect(box, 10, 10)
        f = QFont(); f.setPointSize(9); p.setFont(f)
        self._text(p, box.adjusted(12, 6, -12, 0), Qt.AlignTop | Qt.AlignLeft, "Rover, you finally woke up.", self.cfg["src_fg"])
        f.setPointSize(12); p.setFont(f)
        self._text(p, box.adjusted(12, 0, -12, -8), Qt.AlignBottom | Qt.AlignLeft, "Rover, cuối cùng anh cũng tỉnh rồi.", self.cfg["fg"])


class _Job(QThread):
    progress = Signal(str, int); done = Signal(str)        # done("") = OK, "cancel", hoặc thông báo lỗi
    def __init__(self, fn): super().__init__(); self.fn = fn; self.cancel = False
    def run(self):
        try: self.fn(lambda t, p: (self.progress.emit(t, p), not self.cancel)[1]); self.done.emit("")
        except engines.Cancelled: self.done.emit("cancel")
        except Exception as e: self.done.emit(f"{type(e).__name__}: {e}")


def _table(headers):
    t = QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive); t.horizontalHeader().setStretchLastSection(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows); t.verticalHeader().setVisible(False); return t


class GlossaryDialog(QDialog):
    def __init__(self, db, cfg, parent=None):
        super().__init__(parent); self.db, self.cfg = db, cfg; self.setWindowTitle("Glossary — tên riêng / thuật ngữ"); self.resize(720, 520)
        v = QVBoxLayout(self)
        self.keep = QCheckBox("Không dịch tên riêng / thuật ngữ (mọi mục đều giữ nguyên khi dịch máy)"); self.keep.setChecked(cfg["keep_terms"]); v.addWidget(self.keep)
        self.flt = QLineEdit(); self.flt.setPlaceholderText("Lọc…"); self.flt.textChanged.connect(self._filter); v.addWidget(self.flt)
        self.t = _table(["Thuật ngữ (gốc)", "Dịch là", "Chế độ", "Ghi chú"]); v.addWidget(self.t)
        hb = QHBoxLayout()
        for txt, fn in [("Thêm", self._add), ("Xóa", self._del), ("Import CSV", self._imp), ("Export CSV", self._exp)]:
            b = QPushButton(txt); b.clicked.connect(fn); hb.addWidget(b)
        hb.addStretch(1); v.addLayout(hb)
        v.addWidget(QLabel("<i>Chỉ áp dụng cho dịch máy (Gemini/OpenAI/Google). Câu lấy từ bộ sub giữ nguyên bản dịch của người dịch.</i>"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); bb.accepted.connect(self._save); bb.rejected.connect(self.reject); v.addWidget(bb)
        self._load()

    def _row(self, term="", vi="", mode="keep", note=""):
        r = self.t.rowCount(); self.t.insertRow(r)
        for i, x in enumerate((term, vi)): self.t.setItem(r, i, QTableWidgetItem(x))
        c = QComboBox(); c.addItem("Giữ nguyên", "keep"); c.addItem("Dịch theo cột 'Dịch là'", "translate"); c.setCurrentIndex(0 if mode == "keep" else 1)
        self.t.setCellWidget(r, 2, c); self.t.setItem(r, 3, QTableWidgetItem(note)); return r

    def _load(self):
        self.t.setRowCount(0)
        for g in sorted(self.db.glossary(), key=lambda g: g["term"].lower()): self._row(g["term"], g["vi"], g["mode"], g["note"])
        self.t.resizeColumnsToContents()
    def _filter(self, s):
        for r in range(self.t.rowCount()):
            self.t.setRowHidden(r, bool(s) and not any(s.lower() in (self.t.item(r, c).text().lower() if self.t.item(r, c) else "") for c in (0, 1, 3)))
    def _add(self): r = self._row(); self.t.scrollToBottom(); self.t.editItem(self.t.item(r, 0))
    def _del(self):
        for r in sorted({i.row() for i in self.t.selectedIndexes()}, reverse=True): self.t.removeRow(r)
    def _imp(self):
        p, _ = QFileDialog.getOpenFileName(self, "Import glossary", "", "CSV (*.csv)")
        if p: n = self.db.import_glossary_csv(p); self._load(); QMessageBox.information(self, "Import", f"Đã nhập {n} mục (cột: term, vi, mode, note).")
    def _exp(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export glossary", "glossary.csv", "CSV (*.csv)")
        if p: self._save(close=False); self.db.export_csv("glossary", p)
    def _save(self, close=True):
        for g in self.db.glossary(): self.db.del_term(g["term"])
        for r in range(self.t.rowCount()):
            term = (self.t.item(r, 0).text() if self.t.item(r, 0) else "").strip()
            if term: self.db.set_term(term, self.t.item(r, 1).text() if self.t.item(r, 1) else "", self.t.cellWidget(r, 2).currentData(),
                                      self.t.item(r, 3).text() if self.t.item(r, 3) else "")
        self.cfg["keep_terms"] = self.keep.isChecked(); self.cfg.save()
        if close: self.accept()


class VocabDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent); self.db = db; self.setWindowTitle("Sổ từ"); self.resize(820, 520)
        v = QVBoxLayout(self)
        self.flt = QLineEdit(); self.flt.setPlaceholderText("Lọc…"); self.flt.textChanged.connect(self._load); v.addWidget(self.flt)
        self.t = _table(["Từ", "Nghĩa", "Câu gốc", "Câu dịch", "Ngày lưu", "Ôn"]); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t.setWordWrap(True); v.addWidget(self.t)
        hb = QHBoxLayout()
        for txt, fn in [("Ôn tập", self._review), ("Xóa", self._del), ("Export CSV (Anki)", self._exp)]:
            b = QPushButton(txt); b.clicked.connect(fn); hb.addWidget(b)
        hb.addStretch(1); self.count = QLabel(); hb.addWidget(self.count); v.addLayout(hb); self._load()

    def _load(self):
        s = self.flt.text().lower(); rows = [r for r in self.db.vocab() if not s or any(s in str(x).lower() for x in r[:4])]
        self.t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, x in enumerate(r):
                self.t.setItem(i, j, QTableWidgetItem(_plain(str(x)) if j == 1 else str(x)))
        self.t.setColumnWidth(0, 140); self.t.setColumnWidth(1, 220); self.t.setColumnWidth(2, 220); self.t.setColumnWidth(3, 160)
        self.count.setText(f"{len(rows)} từ")
    def _del(self):
        for r in sorted({i.row() for i in self.t.selectedIndexes()}, reverse=True): self.db.del_vocab(self.t.item(r, 0).text())
        self._load()
    def _exp(self):
        p, _ = QFileDialog.getSaveFileName(self, "Export sổ từ", "vocab.csv", "CSV (*.csv)")
        if p: self.db.export_csv("vocab", p)
    def _review(self):
        rows = self.db.vocab()
        if rows: ReviewDialog(self.db, rows, self).exec(); self._load()


def _plain(h):
    import re
    return html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", h)))


class ReviewDialog(QDialog):
    """Flashcard: ưu tiên từ ít ôn."""
    def __init__(self, db, rows, parent=None):
        super().__init__(parent); self.db = db; self.setWindowTitle("Ôn tập"); self.resize(520, 360)
        rows = sorted(rows, key=lambda r: (r[5], random.random())); self.rows, self.i = rows, 0
        v = QVBoxLayout(self)
        self.word = QLabel(); self.word.setAlignment(Qt.AlignCenter); self.word.setStyleSheet("font-size:28px;font-weight:600")
        self.ctx = QLabel(); self.ctx.setWordWrap(True); self.ctx.setAlignment(Qt.AlignCenter); self.ctx.setStyleSheet("color:gray")
        self.ans = QLabel(); self.ans.setWordWrap(True); self.ans.setTextFormat(Qt.RichText)
        for w in (self.word, self.ctx, self.ans): v.addWidget(w)
        v.addStretch(1); hb = QHBoxLayout()
        self.show_b = QPushButton("Hiện nghĩa (Space)"); self.next_b = QPushButton("Tiếp →")
        self.show_b.clicked.connect(self._show); self.next_b.clicked.connect(self._next); hb.addWidget(self.show_b); hb.addWidget(self.next_b); v.addLayout(hb)
        self._render()
    def _render(self):
        r = self.rows[self.i]; self.word.setText(r[0]); self.ans.setText("")
        sent = r[2].replace(r[0], f"<b>{r[0]}</b>") if r[2] else ""; self.ctx.setText(sent)
    def _show(self):
        r = self.rows[self.i]; self.ans.setText(f"{r[1]}<br><br><span style='color:gray'>{html.escape(r[3] or '')}</span>"); self.db.reviewed(r[0])
    def _next(self): self.i = (self.i + 1) % len(self.rows); self._render()
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space: self._show()
        elif e.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter): self._next()
        else: super().keyPressEvent(e)


class SubsDialog(QDialog):
    def __init__(self, db, index, cfg, on_changed, parent=None):
        super().__init__(parent); self.db, self.index, self.cfg, self.on_changed = db, index, cfg, on_changed
        self.setWindowTitle("Bộ sub Việt hóa"); self.resize(860, 600); v = QVBoxLayout(self)
        v.addWidget(QLabel("<b>File đã nhập</b> (file nhập sau được ưu tiên khi trùng câu)"))
        self.files = QListWidget(); self.files.setMaximumHeight(120); v.addWidget(self.files)
        hb = QHBoxLayout(); b1 = QPushButton("Chọn file sub…"); b2 = QPushButton("Xóa file đã nhập"); hb.addWidget(b1); hb.addWidget(b2); hb.addStretch(1)
        b1.clicked.connect(self._open); b2.clicked.connect(self._del); v.addLayout(hb)
        # preview
        self.prev_lbl = QLabel(""); v.addWidget(self.prev_lbl)
        cb = QHBoxLayout(); self.src_c = QComboBox(); self.vi_c = QComboBox()
        cb.addWidget(QLabel("Cột gốc (EN):")); cb.addWidget(self.src_c, 1); cb.addWidget(QLabel("Cột tiếng Việt:")); cb.addWidget(self.vi_c, 1)
        self.imp_b = QPushButton("Nhập"); self.imp_b.setEnabled(False); self.imp_b.clicked.connect(self._import); cb.addWidget(self.imp_b); v.addLayout(cb)
        self.t = _table([]); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers); v.addWidget(self.t, 1)
        # test
        tb = QHBoxLayout(); self.test = QLineEdit(); self.test.setPlaceholderText("Thử khớp: dán 1 câu tiếng Anh (có thể sai vài ký tự như OCR)…")
        self.test.returnPressed.connect(self._test); tb.addWidget(self.test); v.addLayout(tb)
        self.test_out = QLabel(); self.test_out.setWordWrap(True); self.test_out.setTextInteractionFlags(Qt.TextSelectableByMouse); v.addWidget(self.test_out)
        self.path = None; self._files()

    def _files(self):
        self.files.clear()
        for f, n in self.db.sub_files(): self.files.addItem(f"{f}  —  {n:,} câu")
        self.setWindowTitle(f"Bộ sub Việt hóa — {len(self.index):,} câu trong chỉ mục")

    def _open(self):
        p, _ = QFileDialog.getOpenFileName(self, "Chọn bộ sub", "", "Sub (*.csv *.tsv *.txt *.xlsx *.json);;Tất cả (*)")
        if not p: return
        try: self.hdr, self.rows = importer.read_table(p)
        except Exception as e: QMessageBox.warning(self, "Lỗi đọc file", str(e)); return
        if len(self.hdr) < 2: QMessageBox.warning(self, "Lỗi", "File cần ít nhất 2 cột (gốc và tiếng Việt)."); return
        self.path = p; s, vi = importer.guess_cols(self.hdr, self.rows)
        for c in (self.src_c, self.vi_c): c.clear(); c.addItems(self.hdr)
        self.src_c.setCurrentIndex(s); self.vi_c.setCurrentIndex(vi)
        self.t.setColumnCount(len(self.hdr)); self.t.setHorizontalHeaderLabels(self.hdr); show = self.rows[:200]; self.t.setRowCount(len(show))
        for i, r in enumerate(show):
            for j, x in enumerate(r): self.t.setItem(i, j, QTableWidgetItem(x[:300]))
        self.prev_lbl.setText(f"<b>{Path(p).name}</b>: {len(self.rows):,} dòng, {len(self.hdr)} cột — xem trước 200 dòng. Kiểm tra lại cột rồi bấm Nhập.")
        self.imp_b.setEnabled(True)

    def _import(self):
        s, v = self.src_c.currentIndex(), self.vi_c.currentIndex()
        if s == v: QMessageBox.warning(self, "Lỗi", "Cột gốc và cột tiếng Việt phải khác nhau."); return
        pairs = importer.extract_pairs(self.rows, s, v)
        self.db.add_subs(Path(self.path).name, pairs); self.on_changed(); self._files(); self.imp_b.setEnabled(False)
        QMessageBox.information(self, "Đã nhập", f"Đã nhập {len(pairs):,} cặp câu từ {Path(self.path).name}.")

    def _del(self):
        for it in self.files.selectedItems(): self.db.del_sub_file(it.text().split("  —  ")[0])
        self.on_changed(); self._files()

    def _test(self):
        m = self.index.match(self.test.text(), self.cfg["fuzzy_threshold"])
        self.test_out.setText(f"<b>{m.score:.1f}%</b> — {html.escape(m.src)}<br>→ {html.escape(m.vi)}" if m else "<i>Không khớp câu nào trên ngưỡng.</i>")
