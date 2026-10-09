import random, html, time, threading
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QKeySequence
from PySide6.QtWidgets import (QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QSpinBox,
    QDoubleSpinBox, QCheckBox, QComboBox, QPlainTextEdit, QDialogButtonBox, QPushButton, QListWidget, QFileDialog, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QAbstractItemView, QProgressDialog, QSlider, QColorDialog, QGroupBox,
    QListWidgetItem, QScrollArea, QFrame, QTableView, QApplication)
from .icons import icon as mdi
from . import importer, engines, hotkeys, __version__
from .dictionary import LANGS
from .ui_overlay import outline_offsets, TOOLBAR, TIPS
from .i18n import tr, N_, LANGS as UI_LANGS

DIALOG_ENGINES = {"google": N_("settings.translate.dialog_engine.google"), "gemini_google": N_("settings.translate.dialog_engine.gemini_google"),
                  "gemini": N_("settings.translate.dialog_engine.gemini")}
SCAN_ENGINES = {"ocr_google": N_("settings.translate.scan_engine.ocr_google"), "ocr_gemini": N_("settings.translate.scan_engine.ocr_gemini"),
                "gemini_image": N_("settings.translate.scan_engine.gemini_image")}

OCR_TIPS = {
    "ocr_engine": N_("settings.ocr.tip.ocr_engine"),
    "ocr_lang": N_("settings.ocr.tip.ocr_lang"),
    "ocr_scale": N_("settings.ocr.tip.ocr_scale"),
    "interval_ms": N_("settings.ocr.tip.interval_ms"),
    "stable_ms": N_("settings.ocr.tip.stable_ms"),
    "diff_threshold": N_("settings.ocr.tip.diff_threshold"),
    "dedupe_ratio": N_("settings.ocr.tip.dedupe_ratio"),
    "target_app": N_("settings.ocr.tip.target_app"),
    "clear_on_empty": N_("settings.ocr.tip.clear_on_empty"),
    "fix_spacing": N_("settings.ocr.tip.fix_spacing"),
}
SNAP_TIP = N_("settings.ocr.snap_tip")

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None, on_preview=None, subs=None):
        super().__init__(parent); self.cfg = cfg; self.on_preview = on_preview; self.w = {}; self._snap = {k: cfg[k] for k in self.LIVE}; self.setWindowTitle(tr("settings.title")); self.resize(760, 680)
        tabs = QTabWidget(); v = QVBoxLayout(self); v.addWidget(tabs)
        # --- OCR
        f = self._tab(tabs, "settings.tab.ocr")
        self._combo(f, "ocr_engine", "settings.ocr.ocr_engine", {"windows": "settings.ocr.ocr_engine.windows", "rapidocr": "settings.ocr.ocr_engine.rapidocr", "tesseract": "settings.ocr.ocr_engine.tesseract"})
        self._line(f, "ocr_lang", "settings.ocr.ocr_lang", "settings.ocr.ocr_lang.placeholder")
        self._dspin(f, "ocr_scale", "settings.ocr.ocr_scale", 0.5, 4, 0.25)
        self._spin(f, "interval_ms", "settings.ocr.interval_ms", 50, 2000)
        self._spin(f, "stable_ms", "settings.ocr.stable_ms", 0, 3000)
        self._dspin(f, "diff_threshold", "settings.ocr.diff_threshold", 0.2, 50, 0.5)
        self._spin(f, "dedupe_ratio", "settings.ocr.dedupe_ratio", 50, 100)
        self.app_combo = QComboBox(); self.app_combo.setEditable(True); self.app_combo.setMinimumWidth(260)
        ref = QPushButton(tr("settings.ocr.refresh")); ref.clicked.connect(self._load_apps); self._load_apps()
        hb = QHBoxLayout(); hb.addWidget(self.app_combo, 1); hb.addWidget(ref); f.addRow(tr("settings.ocr.only_translate_while_this_app"), hb)
        self.w["target_app"] = (self.app_combo, self._app_value)
        self._check(f, "clear_on_empty", "settings.ocr.clear_on_empty")
        self._check(f, "fix_spacing", "settings.ocr.fix_spacing")
        f.addRow(QLabel("<i>" + tr("settings.ocr.pick_dialogue_speaker_name_areas") + "</i>"))
        self.btn_snap = QPushButton(tr("settings.ocr.save_current_region_image_for")); self.btn_show = QPushButton(tr("settings.ocr.show_selected_areas"))
        self.btn_show.setToolTip("<p>" + tr("settings.ocr.outline_dialogue_and_speaker_name") + "</p>")
        hb2 = QHBoxLayout(); hb2.addWidget(self.btn_show); hb2.addWidget(self.btn_snap, 1); f.addRow(hb2)
        for k, t in OCR_TIPS.items(): self._tip(f, hb if k == "target_app" else self.w[k][0], t)
        self.btn_snap.setToolTip(f"<p>{tr(SNAP_TIP)}</p>")
        # quản lý OCR engine tải thêm: trạng thái + dung lượng, Tải / Xóa
        self.installed = False; self.eng_rows = {}
        g = self._group(f, "settings.ocr.group.downloadable_ocr_engines")
        for key, name, dl in [("rapidocr", "RapidOCR", "~80 MB"), ("tesseract", "Tesseract", "~50 MB")]:
            st = QLabel(); bi = QPushButton(); bd = QPushButton(tr("settings.ocr.remove"))
            bi.clicked.connect(lambda _=0, k=key: self._install(k)); bd.clicked.connect(lambda _=0, k=key: self._remove(k))
            hb = QHBoxLayout(); hb.addWidget(st, 1); hb.addWidget(bi); hb.addWidget(bd); g.addRow(name, hb); self.eng_rows[key] = (st, bi, bd, dl)
        self.eng_status = QLabel(); self.eng_status.setWordWrap(True); g.addRow(self.eng_status)
        self._eng_refresh()
        # --- Dịch
        tab = self._tab(tabs, "settings.tab.translate")
        f = self._group(tab, "settings.translate.group.dialogue_translation_overlay")
        self._check(f, "translate", "settings.translate.translate")
        self._combo(f, "dialog_engine", "settings.translate.dialog_engine", DIALOG_ENGINES)
        f = self._group(tab, "settings.translate.group.captured_area_translation")
        self._combo(f, "scan_engine", "settings.translate.scan_engine", SCAN_ENGINES)
        f = self._group(tab, "settings.translate.group.gemini_ai_only")
        self.gem_warn = QLabel(); self.gem_warn.setWordWrap(True); self.gem_warn.setStyleSheet("color:#e8a33a"); f.addRow(self.gem_warn)
        self._line(f, "gemini_key", "settings.translate.gemini_key", password=True)
        self.model = QComboBox(); self.model.setEditable(True); self.model.addItem(cfg["gemini_model"]); self.model.setToolTip(tr("settings.translate.press_check_key_list_models"))
        f.addRow(tr("settings.translate.gemini_model"), self.model); self.w["gemini_model"] = (self.model, lambda: self.model.currentText().strip())
        bt = QPushButton(tr("settings.translate.check_key")); self.key_status = QLabel(); self.key_status.setWordWrap(True); bt.clicked.connect(self._test_key)
        hb = QHBoxLayout(); hb.addWidget(bt); hb.addWidget(self.key_status, 1); f.addRow(hb)
        for k in ("dialog_engine", "scan_engine"): self.w[k][0].currentIndexChanged.connect(self._gem_warn)
        self.w["gemini_key"][0].textChanged.connect(self._gem_warn); self._gem_warn()
        self._spin(f, "context_lines", "settings.translate.context_lines", 0, 20); self._check(f, "keep_terms", "settings.translate.keep_terms")
        self._check(f, "stream", "settings.translate.stream")
        self._spin(f, "gemini_thinking_budget", "settings.translate.gemini_thinking_budget", -1, 8192)
        self._spin(f, "timeout_s", "settings.translate.timeout_s", 3, 120); self._spin(f, "cooldown_s", "settings.translate.cooldown_s", 0, 3600)
        self._src_lang = self._line(f, "src_lang", "settings.translate.src_lang")
        # --- Bộ sub Việt hóa
        f = self._tab(tabs, "settings.tab.subs")
        self._check(f, "use_subs", "settings.translate.use_subs")
        sl = QSlider(Qt.Horizontal); sl.setRange(50, 100); sl.setValue(int(cfg["fuzzy_threshold"]))
        pct = QLabel(); pct.setMinimumWidth(110)
        def th_text(t): pct.setText(f"{t}%" + (" — " + tr("settings.subs.exact_only") if t == 100 else ""))
        sl.valueChanged.connect(th_text); th_text(sl.value())
        hb = QHBoxLayout(); hb.addWidget(sl, 1); hb.addWidget(pct); f.addRow(tr("settings.translate.fuzzy_threshold"), hb)
        self.w["fuzzy_threshold"] = (sl, sl.value); self._tip(f, hb, "settings.subs.tip.fuzzy_threshold")
        if subs:
            self.subs_panel = SubsPanel(*subs, threshold=sl.value); f.addRow(self.subs_panel)
            sl.valueChanged.connect(lambda _: self.subs_panel.test.text() and self.subs_panel._test())
        # --- Prompt
        t = QWidget(); tv = QVBoxLayout(t); tabs.addTab(t, tr("settings.tab.prompt"))
        tv.addWidget(QLabel(tr("settings.prompt.variables") + " {src_lang} {player} {gender} {keep_rule} {glossary}"))
        self.prompt = QPlainTextEdit(cfg["prompt"]); tv.addWidget(self.prompt)
        tv.addWidget(QLabel(tr("settings.prompt.word_explanation_prompt_variables") + " {word} {sentence}")); self.explain = QPlainTextEdit(cfg["explain_prompt"]); tv.addWidget(self.explain)
        # --- Nhân vật
        f = self._tab(tabs, "settings.tab.character")
        self._line(f, "player_name", "settings.character.player_name"); self._combo(f, "gender", "settings.character.gender", {"male": N_("settings.character.gender.male"), "female": "settings.character.gender.female"})
        self.tokens = QLineEdit(", ".join(cfg["name_tokens"])); f.addRow(tr("settings.character.name_placeholders_in_subtitle_files"), self.tokens)
        f.addRow(QLabel("<i>" + tr("settings.character.gender_macros_like_male_he", _=0) + "</i>"))
        # --- Từ điển
        f = self._tab(tabs, "settings.tab.dictionary")
        self._combo(f, "dict_mode", "settings.dictionary.dict_mode", {"auto": "settings.dictionary.dict_mode.auto", "google": "settings.dictionary.dict_mode.google", "offline": "settings.dictionary.dict_mode.offline", "online": "settings.dictionary.dict_mode.online", "llm": "settings.dictionary.dict_mode.llm"})
        self._combo(f, "target_lang", "settings.dictionary.target_lang", LANGS)
        self._combo(f, "popup_trigger", "settings.dictionary.popup_trigger", {"click": "settings.dictionary.popup_trigger.click", "hover": "settings.dictionary.popup_trigger.hover"})
        self._spin(f, "hover_delay_ms", "settings.dictionary.hover_delay_ms", 0, 2000)
        self.dicts = QListWidget(); self.dicts.addItems(cfg["dict_files"]); f.addRow(tr("settings.dictionary.dictionary_files"), self.dicts)
        hb = QHBoxLayout(); a = QPushButton(tr("settings.dictionary.add")); d = QPushButton(tr("settings.dictionary.remove")); hb.addWidget(a); hb.addWidget(d); hb.addStretch(1); f.addRow(hb)
        a.clicked.connect(self._add_dict); d.clicked.connect(lambda: [self.dicts.takeItem(self.dicts.row(i)) for i in self.dicts.selectedItems()])
        f.addRow(QLabel("<i>" + tr("settings.dictionary.supports_stardict_ifo_idx_dict", _=0) + "</i>"))
        # --- Giao diện
        tab = self._tab(tabs, "settings.tab.appearance")
        lc = QComboBox(); lc.addItem("Tự động (theo Windows) / Auto", "")   # no-i18n: song ngữ
        for code, name in UI_LANGS.items(): lc.addItem(name, code)
        lc.setCurrentIndex(max(0, lc.findData(cfg["ui_lang"]))); tab.addRow("Ngôn ngữ / Language", lc); self.w["ui_lang"] = (lc, lc.currentData)   # no-i18n: song ngữ, chọn nhầm vẫn tìm lại được
        # khung / màu / độ trong suốt / viền chữ: đổi là overlay + ô xem trước cập nhật ngay; Cancel thì trả lại
        self.prev = _Preview(cfg); tab.addRow(self.prev)
        f = self._group(tab, "settings.appearance.group.text")
        self._spin(f, "font_size", "settings.appearance.font_size", 8, 48); self._spin(f, "src_font_size", "settings.appearance.src_font_size", 8, 40)
        self._combo(f, "display", "settings.appearance.display", {"both": "settings.appearance.display.both", "vi": "settings.appearance.display.vi",
                                                "vi_hover": "settings.appearance.display.vi_hover", "src_hover": "settings.appearance.display.src_hover"})
        self._combo(f, "text_valign", "settings.appearance.text_valign", {"top": "settings.appearance.text_valign.top", "center": "settings.appearance.text_valign.center", "bottom": "settings.appearance.text_valign.bottom"})
        cb = self.w["text_valign"][0]; cb.currentIndexChanged.connect(lambda _: self._live("text_valign", cb.currentData()))
        self._tip(f, cb, "settings.appearance.tip.when_frame_is_taller")
        s = self._spin(f, "line_gap", "settings.appearance.line_gap", 0, 40); s.valueChanged.connect(lambda v: self._live("line_gap", v))
        self._tip(f, s, "settings.appearance.tip.extra_space_between_source")
        s = self._spin(f, "text_outline", "settings.appearance.text_outline", 0, 4); s.valueChanged.connect(lambda v: self._live("text_outline", v))
        self._check(f, "show_speaker", "settings.appearance.show_speaker")
        f = self._group(tab, "settings.appearance.group.frame_colors")
        c = self._check(f, "show_frame", "settings.appearance.show_frame"); c.toggled.connect(lambda on: self._live("show_frame", on))
        sl = QSlider(Qt.Horizontal); sl.setRange(0, 95); sl.setValue(round((1 - float(cfg["opacity"])) * 100))
        pct = QLabel(f"{sl.value()}%"); pct.setMinimumWidth(44)
        sl.valueChanged.connect(lambda t: (pct.setText(f"{t}%"), self._live("opacity", round(1 - t / 100, 2))))
        hb = QHBoxLayout(); hb.addWidget(sl, 1); hb.addWidget(pct); f.addRow(tr("settings.appearance.frame_transparency"), hb)
        self.w["opacity"] = (sl, lambda: round(1 - sl.value() / 100, 2))
        cols = QHBoxLayout(); cf = [QFormLayout(), QFormLayout()]; cols.addLayout(cf[0]); cols.addSpacing(16); cols.addLayout(cf[1]); f.addRow(cols)
        for i, (k, n) in enumerate([("bg", N_("settings.appearance.bg")), ("fg", N_("settings.appearance.fg")), ("src_fg", N_("settings.appearance.src_fg")), ("accent", N_("settings.appearance.accent"))]): self._color(cf[i % 2], k, n)
        self._tip(cf[1], self.w["accent"][0], "settings.appearance.tip.speaker_name_lookup_popup")
        g = QGroupBox(tr("settings.appearance.toolbar_buttons_tick_show_drag")); gl = QHBoxLayout(g)
        lst = QListWidget(); lst.setDragDropMode(QAbstractItemView.InternalMove); lst.setDefaultDropAction(Qt.MoveAction)
        col, icons = lst.palette().text().color(), dict(TOOLBAR)
        for k in list(cfg["toolbar"]) + [k for k, _ in TOOLBAR if k not in cfg["toolbar"]]:     # nút đang hiện theo thứ tự đã xếp, nút ẩn xuống cuối
            if k not in icons: continue
            it = QListWidgetItem(mdi(icons[k], color=col), tr(TIPS[k]).split(" (")[0]); it.setData(Qt.UserRole, k)
            it.setFlags((it.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsDropEnabled)      # không thả đè lên item (mất item)
            it.setCheckState(Qt.Checked if k in cfg["toolbar"] else Qt.Unchecked); lst.addItem(it)
        lst.setFixedHeight(lst.sizeHintForRow(0) * lst.count() + 2 * lst.frameWidth() + 2)
        def move(d):
            r = lst.currentRow(); n = r + d
            if r < 0 or not 0 <= n < lst.count(): return
            lst.insertItem(n, lst.takeItem(r)); lst.setCurrentRow(n)
        bv = QVBoxLayout()
        for ic, d, tip in (("mdi6.arrow-up", -1, N_("settings.appearance.up_further_left_on_toolbar")), ("mdi6.arrow-down", 1, N_("settings.appearance.down_further_right_on_toolbar"))):
            b = QPushButton(mdi(ic, color=col), ""); b.setToolTip(tr(tip)); b.clicked.connect(lambda _=0, d=d: move(d)); bv.addWidget(b)
        bv.addStretch(1)
        gl.addWidget(lst, 1); gl.addLayout(bv)
        tab.addRow(g); self.w["toolbar"] = (lst, lambda: [lst.item(i).data(Qt.UserRole) for i in range(lst.count()) if lst.item(i).checkState() == Qt.Checked])
        f = self._group(tab, "settings.appearance.group.behavior")
        self._dspin(f, "auto_hide_s", "settings.appearance.auto_hide_s", 0, 60, 0.5)
        self._check(f, "animations", "settings.appearance.animations")
        uk = KeyCapture(cfg["unlock_key"]); f.addRow(tr("settings.appearance.hold_key_interact_while_locked"), uk); self.w["unlock_key"] = (uk, uk.text)
        self._tip(f, uk, "settings.appearance.tip.while_overlay_is_locked")
        c = self._check(f, "hide_from_capture", "settings.appearance.hide_from_capture")
        self._tip(f, c, "settings.appearance.tip.overlay_stays_visible_on")
        self._check(f, "check_updates", "settings.appearance.check_updates")
        # --- Hotkey
        f = self._tab(tabs, "settings.tab.hotkeys"); self.hk = {}
        for k, n in [("toggle", N_("settings.hotkeys.toggle")), ("region", N_("settings.hotkeys.region")), ("pause", N_("settings.hotkeys.pause")), ("rescan", N_("settings.hotkeys.rescan")), ("clickthrough", "Click-through"),
                     ("clear", N_("settings.hotkeys.clear")), ("translate", N_("settings.hotkeys.translate")), ("scan", N_("settings.hotkeys.scan")), ("lock", N_("settings.hotkeys.lock"))]:
            e = KeyCapture(cfg["hotkeys"].get(k, ""), hotkey=True); f.addRow(tr(n).replace("&", "&&"), e); self.hk[k] = e
        self._check(f, "run_as_admin", "settings.hotkeys.run_as_admin")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        ver = QLabel(f"Game Sub v{__version__}"); ver.setStyleSheet("color:gray")          # phiên bản bản build, góc trái dưới
        self.btn_update = QPushButton(tr("updater.check_button"))                         # app.check_update nối vào
        self.reset = False; btn_reset = QPushButton(tr("settings.reset.button")); btn_reset.clicked.connect(self._reset)
        foot = QHBoxLayout(); foot.addWidget(ver); foot.addWidget(self.btn_update); foot.addWidget(btn_reset); foot.addStretch(1); foot.addWidget(bb); v.addLayout(foot)

    def _reset(self):
        """Khôi phục cài đặt gốc -> đóng hộp thoại; app mở lại để áp dụng hết (app.open_settings xem self.reset)."""
        box = QMessageBox(QMessageBox.Question, tr("settings.reset.button"), tr("settings.reset.confirm"), QMessageBox.Yes | QMessageBox.No, self)
        keep = QCheckBox(tr("settings.reset.keep")); keep.setChecked(True); box.setCheckBox(keep)
        if box.exec() != QMessageBox.Yes: return
        self.cfg.reset(keep.isChecked()); self.reset = True; QDialog.reject(self)     # không qua self.reject: nó trả lại màu/khung cũ

    LIVE = ("opacity", "bg", "fg", "src_fg", "accent", "show_frame", "text_outline", "text_valign", "line_gap")

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
            col = QColorDialog.getColor(QColor(b.text()), self, tr(label))
            if col.isValid(): show(col.name()); self._live(k, col.name())
        show(self.cfg[k]); b.clicked.connect(pick); f.addRow(tr(label), b); self.w[k] = (b, b.text)

    def _tip(self, f, field, text):
        """Icon ⓘ ngay sau nhãn của dòng (hoặc sau ô tick), rê chuột vào hiện giải thích (rich text để tự xuống dòng)."""
        info = QLabel(); info.setPixmap(mdi("mdi6.information-outline", color=self.palette().placeholderText().color()).pixmap(15, 15))
        info.setToolTip(f"<p>{html.escape(tr(text))}</p>"); info.setCursor(Qt.WhatsThisCursor)
        row, role = (f.getWidgetPosition if isinstance(field, QWidget) else f.getLayoutPosition)(field)
        old = f.labelForField(field) if role == QFormLayout.FieldRole else field      # dòng có nhãn -> gắn sau nhãn; ô tick (cả dòng) -> sau ô tick
        box = QWidget(); hb = QHBoxLayout(box); hb.setContentsMargins(0, 0, 0, 0); hb.setSpacing(5)
        f.removeWidget(old); hb.addWidget(old); hb.addWidget(info); hb.addStretch(1)
        f.setWidget(row, QFormLayout.LabelRole if role == QFormLayout.FieldRole else role, box)

    def _tab(self, tabs, name):
        """Tab cuộn được: màn hình thấp (laptop 768p) vẫn thấy hết."""
        w = QWidget(); f = QFormLayout(w); sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(w); tabs.addTab(sa, tr(name)); return f
    def _group(self, f, title):
        g = QGroupBox(tr(title)); gf = QFormLayout(g); f.addRow(g); return gf
    def _line(self, f, k, label, ph="", password=False):
        e = QLineEdit(str(self.cfg[k] or "")); e.setPlaceholderText(tr(ph) if ph else "")
        if password: e.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        f.addRow(tr(label), e); self.w[k] = (e, lambda e=e: e.text().strip()); return e
    def _spin(self, f, k, label, lo, hi):
        s = QSpinBox(); s.setRange(lo, hi); s.setValue(int(self.cfg[k])); f.addRow(tr(label), s); self.w[k] = (s, s.value); return s
    def _dspin(self, f, k, label, lo, hi, step):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step); s.setValue(float(self.cfg[k])); f.addRow(tr(label), s); self.w[k] = (s, s.value); return s
    def _check(self, f, k, label):
        c = QCheckBox(tr(label)); c.setChecked(bool(self.cfg[k])); f.addRow(c); self.w[k] = (c, c.isChecked); return c
    def _combo(self, f, k, label, opts):
        c = QComboBox()
        for key, txt in opts.items(): c.addItem(tr(txt), key)
        c.setCurrentIndex(max(0, c.findData(self.cfg[k]))); f.addRow(tr(label), c); self.w[k] = (c, c.currentData)

    def _eng_refresh(self):
        ok = {"rapidocr": engines.has_rapidocr(), "tesseract": bool(engines.tesseract_exe())}
        pend = engines.pending()
        for k, (st, bi, bd, dl) in self.eng_rows.items():
            if {"rapidocr": "py", "tesseract": "tesseract"}[k] in pend:
                st.setText(tr("settings.ocr.will_be_removed_when_app")); bi.setEnabled(False); bd.setEnabled(False); continue
            st.setText(tr("settings.ocr.installed_mb_mb_on_disk", mb=f"{engines.size_mb(k):.0f}") if ok[k] else tr("settings.ocr.not_installed"))
            bi.setText(tr("settings.ocr.re_download") if ok[k] else tr("settings.ocr.download_size", size=dl)); bd.setEnabled(ok[k])
        self.eng_status.setText("<i>" + tr("settings.ocr.located_in_path", path=html.escape(str(engines.ENG_DIR))) + "</i>")

    def _load_apps(self):
        """App đang có cửa sổ mở + giá trị đang lưu."""
        from . import winapp
        cur = self._app_value() if self.app_combo.count() else self.cfg["target_app"]
        c = self.app_combo; c.clear(); c.addItem(tr("settings.ocr.any_window_no_filter"), "")
        apps = dict(winapp.windows())
        if cur and cur not in apps: apps[cur] = tr("settings.ocr.not_open")
        for exe, title in sorted(apps.items()): c.addItem(f"{exe} — {title[:40]}", exe)
        c.setCurrentIndex(max(0, c.findData(cur)))

    def _app_value(self):
        c = self.app_combo; t = c.currentText().strip()
        if c.currentIndex() >= 0 and t == c.itemText(c.currentIndex()): return c.currentData() or ""
        return t.split(" — ")[0].strip().lower()                              # gõ tay tên exe

    def _gem_warn(self):
        uses = [tr(n) for k, n in (("dialog_engine", N_("settings.translate.uses.dialog_engine")), ("scan_engine", N_("settings.translate.uses.scan_engine"))) if "gemini" in (self.w[k][1]() or "")]
        no_key = not self.w["gemini_key"][1]()
        self.gem_warn.setText(tr("settings.translate.gemini_is_selected_for_what", what=tr("settings.translate.and").join(uses)) if uses and no_key else "")
        self.gem_warn.setVisible(bool(uses and no_key))

    def _test_key(self):
        key, model = self.w["gemini_key"][1](), self.w["gemini_model"][1]()
        if not key: self.key_status.setText(tr("settings.translate.no_key_entered")); return
        from .translator import Translator
        c = dict(self.cfg); c.update(gemini_key=key, gemini_model=model, stream=False, timeout_s=20)
        res = {}; self.key_status.setText(tr("settings.translate.testing"))
        def work(_):     # 1) lấy danh sách model (cũng là kiểm tra key)  2) model đang chọn không có -> tự chọn  3) gọi thử
            t = Translator(c, None); res["models"] = t.list_models(key)
            if res["models"] and model not in res["models"]: c["gemini_model"] = res["picked"] = Translator.pick_model(res["models"])
            t0 = time.time(); t.gemini("", "Reply with exactly one word: OK", None); res["t"] = time.time() - t0
        job = _Job(work)
        def done(err):
            if res.get("models"):
                cur = res.get("picked") or model; self.model.clear(); self.model.addItems(res["models"]); self.model.setCurrentText(cur)
            note = tr("settings.translate.model_replaced", old=html.escape(model), new=html.escape(res["picked"])) if res.get("picked") else ""
            if err: self.key_status.setText(f"<span style='color:#e86a6a'>{note}✗ {html.escape(err.split(': ', 1)[-1])}</span>")
            else: self.key_status.setText(f"<span style='color:#7bd88f'>{note}" + tr("settings.translate.key_works", model=html.escape(c["gemini_model"]), sec=f"{res['t']:.1f}") + "</span>")
        job.done.connect(done); self._key_job = job; job.start()

    def _remove(self, key):
        name = {"rapidocr": "RapidOCR", "tesseract": "Tesseract"}[key]
        if QMessageBox.question(self, tr("settings.ocr.remove_ocr_engine"), tr("settings.ocr.remove_name_mb_mb", name=name, mb=f"{engines.size_mb(key):.0f}")) != QMessageBox.Yes: return
        now = engines.remove(key); combo = self.w["ocr_engine"][0]
        if combo.currentData() == key: combo.setCurrentIndex(combo.findData("windows"))     # đang chọn engine bị xóa -> về Windows OCR
        self.installed = True; self._eng_refresh()
        if not now: QMessageBox.information(self, tr("settings.ocr.remove_ocr_engine"), tr("settings.ocr.name_is_in_use_it", name=name))

    def _install(self, key):
        dlg = QProgressDialog(tr("settings.ocr.downloading"), tr("settings.ocr.cancel"), 0, 100, self); dlg.setWindowTitle(tr("settings.ocr.download_ocr_engine")); dlg.setMinimumWidth(420)
        dlg.setWindowModality(Qt.WindowModal); dlg.setAutoClose(False); dlg.setAutoReset(False); dlg.show()
        job = _Job(engines.install_rapidocr if key == "rapidocr" else engines.install_tesseract)
        job.progress.connect(lambda t, p: (dlg.setLabelText(t), dlg.setValue(p)))
        dlg.canceled.connect(lambda: setattr(job, "cancel", True))
        def done(err):
            dlg.close(); self._eng_refresh()
            if err == "cancel": return
            if err: QMessageBox.warning(self, tr("settings.ocr.download_ocr_engine"), tr("settings.ocr.error_e", e=err)); return
            self.installed = True; i = self.w["ocr_engine"][0].findData(key)
            if i >= 0: self.w["ocr_engine"][0].setCurrentIndex(i)
            QMessageBox.information(self, tr("settings.ocr.download_ocr_engine"), tr("settings.ocr.installed_press_ok"))
        job.done.connect(done); self._job = job; job.start()

    def _add_dict(self):
        fs, _ = QFileDialog.getOpenFileNames(self, tr("settings.dictionary.choose_dictionaries"), "", tr("settings.dictionary.dictionary") + " (*.ifo *.tsv *.txt *.csv *.json)")
        for x in fs: self.dicts.addItem(x)

    def apply(self):
        c = self.cfg
        for k, (_, get) in self.w.items(): c[k] = get()
        c["prompt"], c["explain_prompt"] = self.prompt.toPlainText(), self.explain.toPlainText()
        c["name_tokens"] = [x.strip() for x in self.tokens.text().split(",") if x.strip()]
        c["dict_files"] = [self.dicts.item(i).text() for i in range(self.dicts.count())]
        c["hotkeys"] = {k: e.text().strip() for k, e in self.hk.items()}
        c.save()


class KeyCapture(QLineEdit):
    """Bấm vào ô rồi nhấn phím / tổ hợp / nút chuột giữa-bên để gán; Backspace hoặc Delete = tắt.
    hotkey=True: hotkey toàn cục (RegisterHotKey) -> phải có 1 phím thường (vd Ctrl+Alt+R), không nhận chuột / chỉ phím bổ trợ."""
    NAMES = {Qt.Key_Control: "Ctrl", Qt.Key_Alt: "Alt", Qt.Key_Shift: "Shift", Qt.Key_Meta: "Win"}
    MOUSE = {Qt.MiddleButton: "Mouse3", Qt.BackButton: "Mouse4", Qt.ForwardButton: "Mouse5"}
    def __init__(self, seq, hotkey=False):
        super().__init__(seq); self.hotkey = hotkey; self.setReadOnly(True); self.setPlaceholderText(tr("keycap.off"))
        self.setToolTip(tr("keycap.press_combo_for_hotkey") if hotkey else tr("keycap.click_field_then_press_key"))
    def focusInEvent(self, e): super().focusInEvent(e); self.setPlaceholderText(tr("keycap.press_combo") if self.hotkey else tr("keycap.press_key_mouse_button_backspace"))
    def focusOutEvent(self, e): super().focusOutEvent(e); self.setPlaceholderText(tr("keycap.off"))
    def _set(self, key, mods):
        names = [n for m, n in ((Qt.ControlModifier, "Ctrl"), (Qt.AltModifier, "Alt"), (Qt.ShiftModifier, "Shift"), (Qt.MetaModifier, "Win")) if mods & m and n != key]
        seq = "+".join(names + [key])
        ok = key not in self.NAMES.values() and hotkeys.parse(seq)[1] is not None if self.hotkey else hotkeys.held_vks(seq)
        if ok: self.setText(seq)
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Backspace, Qt.Key_Delete): self.clear()
        elif e.key() == Qt.Key_Escape: self.clearFocus()
        else: self._set(self.NAMES.get(e.key()) or QKeySequence(e.key()).toString(), e.modifiers())
    def mousePressEvent(self, e):
        if e.button() in self.MOUSE and not self.hotkey: self.setFocus(); self._set(self.MOUSE[e.button()], e.modifiers())
        else: super().mousePressEvent(e)


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
        self._text(p, box.adjusted(12, 0, -12, -8), Qt.AlignBottom | Qt.AlignLeft, "Rover, cuối cùng anh cũng tỉnh rồi.", self.cfg["fg"])   # no-i18n: câu mẫu bản dịch


class _Job(QThread):
    progress = Signal(str, int); done = Signal(str)        # done("") = OK, "cancel", hoặc thông báo lỗi
    def __init__(self, fn): super().__init__(); self.fn = fn; self.cancel = False
    def run(self):
        try: self.result = self.fn(lambda t, p: (self.progress.emit(t, p), not self.cancel)[1]); self.done.emit("")
        except engines.Cancelled: self.done.emit("cancel")
        except Exception as e: self.done.emit(f"{type(e).__name__}: {e}")


def _table(headers):
    t = QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive); t.horizontalHeader().setStretchLastSection(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows); t.verticalHeader().setVisible(False); return t


class GlossaryDialog(QDialog):
    def __init__(self, db, cfg, parent=None):
        super().__init__(parent); self.db, self.cfg = db, cfg; self.setWindowTitle(tr("glossary.glossary_names_terms")); self.resize(720, 520)
        v = QVBoxLayout(self)
        self.keep = QCheckBox(tr("glossary.dont_translate_names_terms_every")); self.keep.setChecked(cfg["keep_terms"]); v.addWidget(self.keep)
        self.flt = QLineEdit(); self.flt.setPlaceholderText(tr("glossary.filter")); self.flt.textChanged.connect(self._filter); v.addWidget(self.flt)
        self.t = _table([tr("glossary.term_source"), tr("glossary.translate_as"), tr("glossary.mode"), tr("glossary.note")]); v.addWidget(self.t)
        hb = QHBoxLayout()
        for txt, fn in [(tr("glossary.add"), self._add), (tr("glossary.remove"), self._del), (tr("glossary.import_csv"), self._imp), (tr("glossary.export_csv"), self._exp)]:
            b = QPushButton(txt); b.clicked.connect(fn); hb.addWidget(b)
        hb.addStretch(1); v.addLayout(hb)
        v.addWidget(QLabel("<i>" + tr("glossary.only_applies_machine_translation_gemini") + "</i>"))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); bb.accepted.connect(self._save); bb.rejected.connect(self.reject); v.addWidget(bb)
        self._load()

    def _row(self, term="", vi="", mode="keep", note=""):
        r = self.t.rowCount(); self.t.insertRow(r)
        for i, x in enumerate((term, vi)): self.t.setItem(r, i, QTableWidgetItem(x))
        c = QComboBox(); c.addItem(tr("glossary.keep_as_is"), "keep"); c.addItem(tr("glossary.use_translate_as_column"), "translate"); c.setCurrentIndex(0 if mode == "keep" else 1)
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
        p, _ = QFileDialog.getOpenFileName(self, tr("glossary.import_title"), "", "CSV (*.csv)")
        if p: n = self.db.import_glossary_csv(p); self._load(); QMessageBox.information(self, tr("glossary.imported_title"), tr("glossary.imported_n_entries_columns_term", n=n))
    def _exp(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("glossary.export_title"), "glossary.csv", "CSV (*.csv)")
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
        super().__init__(parent); self.db = db; self.setWindowTitle(tr("vocab.vocabulary")); self.resize(820, 520)
        v = QVBoxLayout(self)
        self.flt = QLineEdit(); self.flt.setPlaceholderText(tr("vocab.filter")); self.flt.textChanged.connect(self._load); v.addWidget(self.flt)
        self.t = _table([tr("vocab.word"), tr("vocab.meaning"), tr("vocab.source_line"), tr("vocab.translated_line"), tr("vocab.saved_on"), tr("vocab.reviews")]); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t.setWordWrap(True); v.addWidget(self.t)
        hb = QHBoxLayout()
        for txt, fn in [(tr("vocab.review"), self._review), (tr("vocab.remove"), self._del), (tr("vocab.export_anki"), self._exp)]:
            b = QPushButton(txt); b.clicked.connect(fn); hb.addWidget(b)
        hb.addStretch(1); self.count = QLabel(); hb.addWidget(self.count); v.addLayout(hb); self._load()

    def _load(self):
        s = self.flt.text().lower(); rows = [r for r in self.db.vocab() if not s or any(s in str(x).lower() for x in r[:4])]
        self.t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, x in enumerate(r):
                self.t.setItem(i, j, QTableWidgetItem(_plain(str(x)) if j == 1 else str(x)))
        self.t.setColumnWidth(0, 140); self.t.setColumnWidth(1, 220); self.t.setColumnWidth(2, 220); self.t.setColumnWidth(3, 160)
        self.count.setText(tr("vocab.n_words", n=len(rows)))
    def _del(self):
        for r in sorted({i.row() for i in self.t.selectedIndexes()}, reverse=True): self.db.del_vocab(self.t.item(r, 0).text())
        self._load()
    def _exp(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("vocab.export_vocabulary"), "vocab.csv", "CSV (*.csv)")
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
        super().__init__(parent); self.db = db; self.setWindowTitle(tr("review.review")); self.resize(520, 360)
        rows = sorted(rows, key=lambda r: (r[5], random.random())); self.rows, self.i = rows, 0
        v = QVBoxLayout(self)
        self.word = QLabel(); self.word.setAlignment(Qt.AlignCenter); self.word.setStyleSheet("font-size:28px;font-weight:600")
        self.ctx = QLabel(); self.ctx.setWordWrap(True); self.ctx.setAlignment(Qt.AlignCenter); self.ctx.setStyleSheet("color:gray")
        self.ans = QLabel(); self.ans.setWordWrap(True); self.ans.setTextFormat(Qt.RichText)
        for w in (self.word, self.ctx, self.ans): v.addWidget(w)
        v.addStretch(1); hb = QHBoxLayout()
        self.show_b = QPushButton(tr("review.show_meaning_space")); self.next_b = QPushButton(tr("review.next"))
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


class SubsPanel(QWidget):
    """Quản lý bộ sub: nhập / xóa file + thử khớp. Dùng trong SubsDialog và tab Bộ sub của Cài đặt."""
    def __init__(self, db, index, cfg, on_changed, threshold=None, parent=None):
        super().__init__(parent); self.db, self.index, self.cfg, self.on_changed = db, index, cfg, on_changed
        self.threshold = threshold or (lambda: self.cfg["fuzzy_threshold"])        # Cài đặt truyền giá trị đang chỉnh (chưa lưu)
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0)
        self.count_lbl = QLabel(); v.addWidget(self.count_lbl)
        v.addWidget(QLabel(tr("subs.imported_files_later_imports_win")))
        self.files = QListWidget(); self.files.setMaximumHeight(120); v.addWidget(self.files)
        hb = QHBoxLayout(); b1 = QPushButton(tr("subs.choose_subtitle_file")); b2 = QPushButton(tr("subs.remove_imported_file")); b3 = QPushButton(tr("subs.browse_data"))
        hb.addWidget(b1); hb.addWidget(b2); hb.addWidget(b3); hb.addStretch(1)
        b1.clicked.connect(self._open); b2.clicked.connect(self._del); b3.clicked.connect(lambda: self._browse())
        self.files.itemDoubleClicked.connect(lambda it: self._browse(it.data(Qt.UserRole))); self.files.setToolTip(tr("subs.double_click_to_browse")); v.addLayout(hb)
        # preview
        self.prev_lbl = QLabel(""); v.addWidget(self.prev_lbl)
        cb = QHBoxLayout(); self.src_c = QComboBox(); self.vi_c = QComboBox()
        cb.addWidget(QLabel(tr("subs.source_column_en"))); cb.addWidget(self.src_c, 1); cb.addWidget(QLabel(tr("subs.translation_column"))); cb.addWidget(self.vi_c, 1)
        self.imp_b = QPushButton(tr("subs.import")); self.imp_b.setEnabled(False); self.imp_b.clicked.connect(self._import); cb.addWidget(self.imp_b); v.addLayout(cb)
        self.t = _table([]); self.t.setEditTriggers(QAbstractItemView.NoEditTriggers); self.t.setMinimumHeight(140); v.addWidget(self.t, 1)
        # test
        tb = QHBoxLayout(); self.test = QLineEdit(); self.test.setPlaceholderText(tr("subs.test_matching_paste_english_line"))
        self.test.returnPressed.connect(self._test); tb.addWidget(self.test); v.addLayout(tb)
        self.test_out = QLabel(); self.test_out.setWordWrap(True); self.test_out.setTextInteractionFlags(Qt.TextSelectableByMouse); v.addWidget(self.test_out)
        self.path = None; self._files()

    def _files(self):
        self.files.clear()
        for f, n in self.db.sub_files():
            it = QListWidgetItem(tr("subs.file_n_lines", file=f, n=f"{n:,}")); it.setData(Qt.UserRole, f); self.files.addItem(it)
        self.count_lbl.setText(tr("subs.subtitle_pack_n_lines_indexed", n=f"{len(self.index):,}"))

    def _open(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("subs.choose_subtitle_pack"), "", "Sub (*.csv *.tsv *.txt *.xlsx *.json);;" + tr("subs.all_files") + " (*)")
        if not p: return
        try: self.hdr, self.rows = importer.read_table(p)
        except Exception as e: QMessageBox.warning(self, tr("subs.couldnt_read_file"), str(e)); return
        if len(self.hdr) < 2: QMessageBox.warning(self, tr("subs.error"), tr("subs.file_needs_at_least_2")); return
        self.path = p; s, vi = importer.guess_cols(self.hdr, self.rows)
        for c in (self.src_c, self.vi_c): c.clear(); c.addItems(self.hdr)
        self.src_c.setCurrentIndex(s); self.vi_c.setCurrentIndex(vi)
        self.t.setColumnCount(len(self.hdr)); self.t.setHorizontalHeaderLabels(self.hdr); show = self.rows[:200]; self.t.setRowCount(len(show))
        for i, r in enumerate(show):
            for j, x in enumerate(r): self.t.setItem(i, j, QTableWidgetItem(x[:300]))
        self.prev_lbl.setText(tr("subs.file_rows_rows_cols_columns", file=html.escape(Path(p).name), rows=f"{len(self.rows):,}", cols=len(self.hdr)))
        self.imp_b.setEnabled(True)

    def _import(self):
        s, v = self.src_c.currentIndex(), self.vi_c.currentIndex()
        if s == v: QMessageBox.warning(self, tr("subs.error"), tr("subs.source_and_translation_columns_must")); return
        pairs = importer.extract_pairs(self.rows, s, v)
        self.db.add_subs(Path(self.path).name, pairs); self.on_changed(); self._files(); self.imp_b.setEnabled(False); self._browser_reload()
        QMessageBox.information(self, tr("subs.imported"), tr("subs.imported_n_line_pairs_from", n=f"{len(pairs):,}", file=Path(self.path).name))

    def _del(self):
        for it in self.files.selectedItems(): self.db.del_sub_file(it.data(Qt.UserRole))
        self.on_changed(); self._files(); self._browser_reload()

    def _browse(self, file=None):
        b = getattr(self, "browser", None)
        if b is None or not b.isVisible(): self.browser = b = SubsBrowser(self.db, on_pick=self._pick, parent=self)
        b.set_file(file); b.show(); b.raise_(); b.activateWindow()

    def _browser_reload(self):
        b = getattr(self, "browser", None)
        if b is not None and b.isVisible(): b.reload_files()

    def _pick(self, src): self.test.setText(src); self._test()

    def _test(self):
        """Hiện câu gần nhất kể cả khi dưới ngưỡng -> biết nên hạ ngưỡng bao nhiêu."""
        th = self.threshold(); m = self.index.match(self.test.text(), 0) if self.test.text().strip() else None
        if not m: self.test_out.setText("<i>" + tr("subs.no_line_matches_above_threshold") + "</i>"); return
        ok = m.score >= th
        head = f"<b style='color:{'#3fb950' if ok else '#e8a33a'}'>{m.score:.1f}%</b> " + (tr("subs.test_used") if ok else tr("subs.test_below_threshold", th=th))
        self.test_out.setText(f"{head} — {html.escape(m.src)}<br>→ {html.escape(m.vi)}")


class SubsDialog(QDialog):
    def __init__(self, db, index, cfg, on_changed, parent=None):
        super().__init__(parent); self.setWindowTitle(tr("subs.subtitle_pack")); self.resize(860, 600)
        self.panel = SubsPanel(db, index, cfg, on_changed); v = QVBoxLayout(self); v.addWidget(self.panel)


class _SubsQuery(QObject):
    """Đọc bảng subs ở luồng nền bằng kết nối chỉ đọc riêng: sqlite nhả GIL khi quét, không giữ khóa DB
    -> khớp câu OCR (luồng UI, dùng chỉ mục SubIndex trong RAM) không bị chậm khi đang tìm."""
    page = Signal(int, list, bool)                 # gen, rows, hết dữ liệu
    count = Signal(int, int)                       # gen, tổng số câu khớp bộ lọc

    def __init__(self, db):
        super().__init__(); self.db, self.gen, self.where, self.args = db, 0, "", ()

    def set_filter(self, text, file):
        self.gen += 1; w, a = [], []
        if file: w.append("file=?"); a.append(file)
        for t in text.split():                     # mọi từ đều phải có (ở cột gốc hoặc cột dịch)
            t = "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            w.append("(src LIKE ? ESCAPE '\\' OR vi LIKE ? ESCAPE '\\')"); a += [t, t]
        self.where, self.args = " AND ".join(w), tuple(a)
        self._bg(self._count, self.gen, self.where, self.args)

    def fetch(self, after_id, n=300): self._bg(self._page, self.gen, self.where, self.args, after_id, n)

    @staticmethod
    def _bg(fn, *a): threading.Thread(target=fn, args=a, daemon=True).start()

    def _run(self, sql, args):
        c = self.db.reader()
        try: return c.execute(sql, args).fetchall()
        finally: c.close()

    def _page(self, gen, where, args, after_id, n):
        try: rows = self._run(f"SELECT id, src, vi, file FROM subs WHERE id>? {'AND ' + where if where else ''} ORDER BY id LIMIT ?", (after_id, *args, n))
        except Exception: rows = []
        self.page.emit(gen, rows, len(rows) < n)

    def _count(self, gen, where, args):
        try: n = self._run(f"SELECT COUNT(*) FROM subs {'WHERE ' + where if where else ''}", args)[0][0]
        except Exception: n = 0
        self.count.emit(gen, n)


class SubsModel(QAbstractTableModel):
    """Bảng ảo: cuộn tới cuối mới nạp thêm 300 dòng (keyset theo id), không đọc cả bộ sub vào RAM."""
    def __init__(self, query, parent=None):
        super().__init__(parent); self.qr, self.rows, self.done, self.busy = query, [], True, False
        self.hdr = [tr("subs.col_source"), tr("subs.col_translation"), tr("subs.col_file")]
        query.page.connect(self._got)

    def reset(self):
        self.beginResetModel(); self.rows, self.done, self.busy = [], False, False; self.endResetModel(); self.fetchMore()

    def rowCount(self, p=QModelIndex()): return 0 if p.isValid() else len(self.rows)
    def columnCount(self, p=QModelIndex()): return 0 if p.isValid() else 3
    def headerData(self, s, o, role=Qt.DisplayRole):
        if role == Qt.DisplayRole: return self.hdr[s] if o == Qt.Horizontal else str(s + 1)
    def data(self, i, role=Qt.DisplayRole):
        if role in (Qt.DisplayRole, Qt.ToolTipRole): return self.rows[i.row()][i.column() + 1]
    def canFetchMore(self, p=QModelIndex()): return not p.isValid() and not self.done and not self.busy
    def fetchMore(self, p=QModelIndex()):
        if self.canFetchMore(p): self.busy = True; self.qr.fetch(self.rows[-1][0] if self.rows else 0)

    def _got(self, gen, rows, done):
        if gen != self.qr.gen: return                                   # kết quả của bộ lọc cũ
        if rows:
            self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(rows) - 1); self.rows += rows; self.endInsertRows()
        self.done, self.busy = done, False


class SubsBrowser(QDialog):
    """Xem dữ liệu bộ sub đã nhập: tìm theo từ (cột gốc hoặc dịch), lọc theo file. Nhấp đúp 1 dòng -> thử khớp câu đó."""
    def __init__(self, db, on_pick=None, parent=None):
        super().__init__(parent); self.db, self.on_pick = db, on_pick
        self.setWindowTitle(tr("subs.browse_title")); self.resize(980, 620); self.setAttribute(Qt.WA_DeleteOnClose)
        v = QVBoxLayout(self); hb = QHBoxLayout()
        self.q = QLineEdit(); self.q.setPlaceholderText(tr("subs.search_placeholder")); self.q.setClearButtonEnabled(True)
        self.file_c = QComboBox(); hb.addWidget(self.q, 1); hb.addWidget(self.file_c); v.addLayout(hb)
        self.qr = _SubsQuery(db); self.model = SubsModel(self.qr, self)
        self.view = QTableView(); self.view.setModel(self.model); self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers); self.view.setWordWrap(False); self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().setDefaultSectionSize(self.view.fontMetrics().height() + 8)
        hh = self.view.horizontalHeader(); hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.resizeSection(0, 400); hh.resizeSection(1, 400); hh.setStretchLastSection(True)
        self.view.doubleClicked.connect(self._pick); v.addWidget(self.view, 1)
        self.status = QLabel(); self.status.setStyleSheet("color:gray"); v.addWidget(self.status)
        self.timer = QTimer(self, singleShot=True, interval=250); self.timer.timeout.connect(self._apply)   # gõ xong mới tìm
        self.q.textChanged.connect(lambda _: self.timer.start()); self.qr.count.connect(self._count)
        self.reload_files(); self.file_c.currentIndexChanged.connect(lambda _: self._apply())

    def reload_files(self):
        cur = self.file_c.currentData(); self.file_c.blockSignals(True); self.file_c.clear(); self.file_c.addItem(tr("subs.all_files"), None)
        for f, n in self.db.sub_files(): self.file_c.addItem(f"{f} ({n:,})", f)
        self.file_c.setCurrentIndex(max(0, self.file_c.findData(cur))); self.file_c.blockSignals(False); self._apply()

    def set_file(self, file):
        i = self.file_c.findData(file) if file else 0
        if i >= 0 and i != self.file_c.currentIndex(): self.file_c.setCurrentIndex(i)

    def _apply(self):
        self.timer.stop(); self.qr.set_filter(self.q.text(), self.file_c.currentData())
        self.status.setText(tr("subs.searching")); self.model.reset()

    def _count(self, gen, n):
        if gen == self.qr.gen: self.status.setText(tr("subs.n_lines_found", n=f"{n:,}") + ("  ·  " + tr("subs.double_click_to_test") if self.on_pick else ""))

    def _pick(self, i):
        if self.on_pick: self.on_pick(self.model.rows[i.row()][1])

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Copy):                                    # Ctrl+C: "gốc<TAB>dịch" mỗi dòng chọn
            rows = sorted({i.row() for i in self.view.selectionModel().selectedRows()})
            QApplication.clipboard().setText("\n".join(f"{self.model.rows[r][1]}\t{self.model.rows[r][2]}" for r in rows)); return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter): self._apply(); return  # Enter = tìm ngay, không đóng hộp thoại
        super().keyPressEvent(e)
