import random, html
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QComboBox, QPlainTextEdit, QDialogButtonBox, QPushButton, QListWidget, QFileDialog, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QAbstractItemView)
from . import importer

PROVIDERS = {"gemini": "Gemini", "openai": "OpenAI-compatible (DeepSeek/OpenRouter/Ollama)", "google": "Google Translate (free)"}

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent); self.cfg = cfg; self.w = {}; self.setWindowTitle("Cài đặt"); self.resize(620, 560)
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
        f.addRow(QLabel("<i>Vùng dịch / vùng tên nhân vật chọn bằng nút ⬚ / 👤 trên overlay.</i>"))
        self.btn_snap = QPushButton("Lưu ảnh vùng hiện tại để kiểm tra"); f.addRow(self.btn_snap)
        # --- Dịch
        f = self._tab(tabs, "Dịch")
        self._check(f, "use_subs", "Ưu tiên bộ sub Việt hóa")
        self._spin(f, "fuzzy_threshold", "Ngưỡng khớp sub (%)", 50, 100)
        self.chain = QLineEdit(", ".join(cfg["chain"])); self.chain.setToolTip("Thứ tự fallback, ví dụ: gemini, google  |  openai, gemini, google")
        f.addRow("Thứ tự dịch máy", self.chain); f.addRow("", QLabel("gemini, openai, google — để trống = chỉ dùng sub"))
        self._line(f, "gemini_key", "Gemini API key", password=True); self._line(f, "gemini_model", "Gemini model")
        self._spin(f, "gemini_thinking_budget", "Thinking budget (-1 = mặc định)", -1, 8192)
        self._line(f, "openai_base", "OpenAI base URL"); self._line(f, "openai_key", "OpenAI key", password=True); self._line(f, "openai_model", "OpenAI model")
        self._check(f, "stream", "Streaming (hiện chữ dần)"); self._spin(f, "context_lines", "Số câu ngữ cảnh", 0, 20)
        self._check(f, "keep_terms", "Không dịch tên riêng / thuật ngữ"); self._src_lang = self._line(f, "src_lang", "Ngôn ngữ gốc (mô tả cho AI)")
        self._spin(f, "timeout_s", "Timeout (s)", 3, 120); self._spin(f, "cooldown_s", "Nghỉ khi bị 429 (s)", 0, 3600)
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
        self._combo(f, "dict_mode", "Nguồn nghĩa khi hover", {"auto": "Offline → Online → nút AI", "offline": "Chỉ offline", "online": "Online (Anh-Anh, dictionaryapi.dev)", "llm": "AI theo ngữ cảnh (tốn quota)"})
        self._spin(f, "hover_delay_ms", "Độ trễ hover (ms)", 0, 2000)
        self.dicts = QListWidget(); self.dicts.addItems(cfg["dict_files"]); f.addRow("File từ điển", self.dicts)
        hb = QHBoxLayout(); a = QPushButton("Thêm…"); d = QPushButton("Xóa"); hb.addWidget(a); hb.addWidget(d); hb.addStretch(1); f.addRow(hb)
        a.clicked.connect(self._add_dict); d.clicked.connect(lambda: [self.dicts.takeItem(self.dicts.row(i)) for i in self.dicts.selectedItems()])
        f.addRow(QLabel("<i>Hỗ trợ StarDict (.ifo + .idx + .dict/.dict.dz), TSV/CSV (từ⇥nghĩa), JSON {từ: nghĩa}.</i>"))
        # --- Giao diện
        f = self._tab(tabs, "Giao diện")
        self._spin(f, "font_size", "Cỡ chữ bản dịch", 8, 48); self._spin(f, "src_font_size", "Cỡ chữ câu gốc", 8, 40)
        self._dspin(f, "opacity", "Độ đậm nền", 0.05, 1, 0.05)
        self._check(f, "show_source", "Hiện câu gốc (hover tra từ)"); self._check(f, "show_speaker", "Hiện tên nhân vật")
        for k, n in [("bg", "Màu nền"), ("fg", "Màu chữ"), ("src_fg", "Màu câu gốc"), ("accent", "Màu nhấn")]: self._line(f, k, n)
        # --- Hotkey
        f = self._tab(tabs, "Hotkey"); self.hk = {}
        for k, n in [("toggle", "Ẩn/hiện overlay"), ("region", "Chọn vùng"), ("pause", "Tạm dừng"), ("rescan", "Quét lại")]:
            e = QLineEdit(cfg["hotkeys"].get(k, "")); f.addRow(n, e); self.hk[k] = e
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); v.addWidget(bb)

    def _tab(self, tabs, name):
        w = QWidget(); f = QFormLayout(w); tabs.addTab(w, name); return f
    def _line(self, f, k, label, ph="", password=False):
        e = QLineEdit(str(self.cfg[k] or "")); e.setPlaceholderText(ph)
        if password: e.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        f.addRow(label, e); self.w[k] = (e, lambda e=e: e.text().strip()); return e
    def _spin(self, f, k, label, lo, hi):
        s = QSpinBox(); s.setRange(lo, hi); s.setValue(int(self.cfg[k])); f.addRow(label, s); self.w[k] = (s, s.value)
    def _dspin(self, f, k, label, lo, hi, step):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step); s.setValue(float(self.cfg[k])); f.addRow(label, s); self.w[k] = (s, s.value)
    def _check(self, f, k, label):
        c = QCheckBox(label); c.setChecked(bool(self.cfg[k])); f.addRow(c); self.w[k] = (c, c.isChecked)
    def _combo(self, f, k, label, opts):
        c = QComboBox()
        for key, txt in opts.items(): c.addItem(txt, key)
        c.setCurrentIndex(max(0, c.findData(self.cfg[k]))); f.addRow(label, c); self.w[k] = (c, c.currentData)

    def _add_dict(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Chọn từ điển", "", "Từ điển (*.ifo *.tsv *.txt *.csv *.json)")
        for x in fs: self.dicts.addItem(x)

    def apply(self):
        c = self.cfg
        for k, (_, get) in self.w.items(): c[k] = get()
        c["chain"] = [x.strip().lower() for x in self.chain.text().split(",") if x.strip().lower() in PROVIDERS]
        c["prompt"], c["explain_prompt"] = self.prompt.toPlainText(), self.explain.toPlainText()
        c["name_tokens"] = [x.strip() for x in self.tokens.text().split(",") if x.strip()]
        c["dict_files"] = [self.dicts.item(i).text() for i in range(self.dicts.count())]
        c["hotkeys"] = {k: e.text().strip() for k, e in self.hk.items()}
        c.save()


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
