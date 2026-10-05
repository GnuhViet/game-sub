import html, re, sys, traceback
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QTimer, QPoint
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QCursor, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QInputDialog, QMessageBox
from rapidfuzz import fuzz
from .config import Config, DATA_DIR
from .db import DB
from .matcher import SubIndex
from .translator import Translator
from .dictionary import Dictionaries, online_lookup, google_lookup
from .textnorm import norm, WORD_RE
from .spacing import Spacer
from .capture import CaptureWorker
from .hotkeys import Hotkeys
from .ui_overlay import Overlay, WordPopup
from .ui_region import RegionSelector
from .ui_scan import ScanWindow
from .capture import open_sct, grab
from . import ocr
from .textnorm import join_lines
from .ui_dialogs import SettingsDialog, GlossaryDialog, VocabDialog, SubsDialog

class _Sig(QObject):
    partial = Signal(str); done = Signal(object); error = Signal(str)

class Task(QRunnable):
    """Chạy fn(partial_cb) ở thread pool; callback về main thread qua signal."""
    live = set()
    def __init__(self, fn, done=None, error=None, partial=None):
        super().__init__(); self.setAutoDelete(False); self.fn = fn; self.s = _Sig(); Task.live.add(self)
        if done: self.s.done.connect(done)
        if error: self.s.error.connect(error)
        if partial: self.s.partial.connect(partial)
        for sig in (self.s.done, self.s.error): sig.connect(lambda *_: Task.live.discard(self))   # giải phóng sau khi callback chạy ở main thread
    def run(self):
        try: self.s.done.emit(self.fn(self.s.partial.emit))
        except Exception as e: traceback.print_exc(); self.s.error.emit(str(e) or type(e).__name__)

def run(fn, done=None, error=None, partial=None): QThreadPool.globalInstance().start(Task(fn, done, error, partial))

def on_top(dlg):
    dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True); return dlg

class App:
    def __init__(self, qapp):
        self.q = qapp; DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg = Config(); self.db = DB(DATA_DIR / "wuwasub.db")
        self.index = SubIndex(); self.spacer = Spacer(); self.rebuild_index()
        self.dicts = Dictionaries().load(cfg["dict_files"])
        self.tr = Translator(cfg, self.db)
        self.history, self.pos, self.last, self.seq, self.cleared = [], -1, "", 0, False
        self.ov = Overlay(cfg); self.pop = WordPopup(cfg)
        self.lookup_ctx = None                    # câu ngữ cảnh khi tra từ trong cửa sổ Dịch vùng
        self.ov.action.connect(self.on_action); self.ov.word_hover.connect(lambda w, p: self._hover_from(None, w, p)); self.ov.word_click.connect(lambda w, p: self._click_from(None, w, p))
        self.scan_win = ScanWindow(cfg); self.scan = {"src": "", "vi": ""}
        self.scan_win.word_hover.connect(lambda w, p: self._hover_from(self.scan, w, p)); self.scan_win.word_click.connect(lambda w, p: self._click_from(self.scan, w, p))
        self.scan_win.action.connect(self.on_action)
        self.ov.phrase_action.connect(self.on_phrase); self.pop.act.connect(self.on_pop_action)
        self.pop.lang_changed.connect(self.on_lang)
        self.hover_t = QTimer(singleShot=True, timeout=lambda: self.lookup(*self._pending)); self._pending = ("", QPoint())
        self.idle_t = QTimer(singleShot=True, timeout=self._auto_hide); self.auto_hidden = False
        self.ov.set_click_through(cfg["click_through"])
        self.worker = CaptureWorker(cfg)
        self.worker.text_ready.connect(self.on_text); self.worker.error.connect(self.on_error); self.worker.status.connect(self.ov.status.setText)
        self.worker.start()
        self.hk = Hotkeys(qapp); self.hk.triggered.connect(self.on_action); self._register_hotkeys()
        self._tray()
        self.ov.show()
        hint = [] if cfg["region"] else ["Bấm ⬚ (hoặc " + cfg["hotkeys"]["region"] + ") để chọn vùng thoại."]
        if not len(self.index): hint.append("Bấm 📂 để nhập bộ sub.")
        if self.dicts.errors: hint.append("Lỗi từ điển: " + "; ".join(self.dicts.errors))
        self.ov.show_line("", "", " ".join(hint) or "Sẵn sàng.", f"{len(self.index):,} câu sub")

    # ---------------- setup
    def rebuild_index(self):
        c = self.cfg; n = self.index.build(self.db.all_subs(), c["gender"], c["name_tokens"], c["player_name"]); self._known_words(); return n

    def _known_words(self):
        """Tên riêng/từ trong bộ sub + glossary: không tách khi sửa chữ OCR dính."""
        src = " ".join(s for s, _ in self.db.all_subs()) + " " + " ".join(g["term"] for g in self.db.glossary()) + " " + self.cfg["player_name"]
        self.spacer.set_known(WORD_RE.findall(src))

    def _register_hotkeys(self):
        errs = self.hk.register(self.cfg["hotkeys"])
        if errs: self.ov.status.setText("Hotkey bị trùng: " + ", ".join(errs))

    def _tray(self):
        pm = QPixmap(64, 64); pm.fill(Qt.transparent); p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(self.cfg["accent"])); p.setPen(Qt.NoPen); p.drawRoundedRect(4, 4, 56, 56, 14, 14)
        f = QFont(); f.setPointSize(26); f.setBold(True); p.setFont(f); p.setPen(QColor("#111")); p.drawText(pm.rect(), Qt.AlignCenter, "W"); p.end()
        self.icon = QIcon(pm); self.q.setWindowIcon(self.icon)
        self.tray = QSystemTrayIcon(self.icon); m = QMenu()
        for txt, k in [("Ẩn/hiện overlay", "toggle"), ("Chụp & dịch 1 vùng", "scan"), ("Chọn vùng", "region"), ("Tạm dừng", "pause"), ("Bộ sub", "subs"),
                       ("Glossary", "glossary"), ("Sổ từ", "vocab"), ("Cài đặt", "settings"), (None, None), ("Thoát", "quit")]:
            if txt is None: m.addSeparator(); continue
            a = QAction(txt, m); a.triggered.connect(lambda _=0, k=k: self.on_action(k)); m.addAction(a)
            if k == "pause":
                self.ct_action = a = QAction("Click-through (chuột xuyên qua)", m); a.setCheckable(True); a.setChecked(self.cfg["click_through"])
                a.triggered.connect(lambda _=0: self.on_action("clickthrough")); m.addAction(a)
                self.lock_action = a = QAction("Khóa overlay", m); a.setCheckable(True); a.setChecked(self.cfg["locked"])
                a.triggered.connect(lambda _=0: self.on_action("lock")); m.addAction(a)
        self.tray.setContextMenu(m); self.tray.setToolTip("WuWa Sub"); self.tray_menu = m
        self.tray.activated.connect(lambda r: self.on_action("toggle") if r == QSystemTrayIcon.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()

    # ---------------- pipeline
    def on_text(self, speaker, text):
        if not re.search(r"[A-Za-z]{2,}", text):              # rỗng / chỉ ký tự rác = hết thoại
            self.last = ""
            if self.cfg["clear_on_empty"] and not self.cleared: self.cleared = True; self.ov.show_line("", "", "", ""); self.pop.request_hide()
            if self.cfg["auto_hide_s"] > 0 and self.ov.isVisible(): self.idle_t.start(int(self.cfg["auto_hide_s"] * 1000))
            return
        self.idle_t.stop(); self.cleared = False
        if self.auto_hidden: self.auto_hidden = False; self.ov.show()
        if self.cfg["fix_spacing"]: text = self.spacer.fix(text)
        n = norm(text)
        if self.last and fuzz.ratio(n, self.last) >= self.cfg["dedupe_ratio"]: return
        self.last = n; self.seq += 1
        line = {"id": self.seq, "speaker": speaker.strip(), "src": text, "vi": "", "tag": ""}
        self.history.append(line); self.history = self.history[-300:]; self.pos = len(self.history) - 1
        self.resolve(line)

    def resolve(self, line, machine=False):
        c = self.cfg
        if not c["translate"] and not machine: line.update(vi="", tag="Không dịch — chỉ câu gốc"); self.render(line); return
        if c["use_subs"] and not machine:
            m = self.index.match(line["src"], c["fuzzy_threshold"])
            if m: line.update(vi=m.vi, tag=f"Bộ sub · khớp {m.score:.0f}%"); self.render(line); return
        line.update(tag="", busy=True); self.render(line)               # không hiện "Đang dịch…"
        i = next((k for k, l in enumerate(self.history) if l is line), len(self.history))
        ctx = [(l["speaker"], l["src"], l["vi"]) for l in self.history[max(0, i - c["context_lines"]):i]] if c["context_lines"] else []
        def partial(t): line["vi"] = t; self.render(line)
        def done(res): line.update(vi=res[0], tag=self.tr.label(res[1]), busy=False); self.render(line)
        def err(e): line.update(tag=f"Lỗi dịch: {e}", busy=False); self.render(line)
        run(lambda p: self.tr.translate(line["src"], line["speaker"], ctx, p), done, err, partial)

    def render(self, line=None):
        if not self.history: return
        cur = self.history[self.pos]
        if line is not None and (line is not cur or self.cleared): return     # đã xóa (hết thoại): bản dịch về muộn không hiện lại
        nav = f"  [{self.pos + 1}/{len(self.history)}]" if self.pos != len(self.history) - 1 else ""
        self.ov.show_line(cur["speaker"], cur["src"], cur["vi"] or ("" if cur.get("busy") or cur["tag"].startswith(("Lỗi", "Không")) else cur["src"]), cur["tag"] + nav)

    def _auto_hide(self):
        if self.ov.isVisible() and not self.ov.underMouse() and not self.pop.isVisible():
            self.ov.hide(); self.auto_hidden = True

    def on_error(self, msg): self.ov._tag = msg; self.ov._tag_vis()

    # ---------------- tra từ
    def cur_line(self):
        if self.lookup_ctx: return self.lookup_ctx
        return self.history[self.pos] if self.history else {"src": self.ov.src, "vi": ""}

    def _hover_from(self, ctx, word, pos):
        if word: self.lookup_ctx = ctx
        self.on_hover(word, pos)

    def _click_from(self, ctx, word, pos): self.lookup_ctx = ctx; self.on_click(word, pos)

    def on_hover(self, word, pos):
        if self.pop.pinned and self.pop.isVisible(): return
        if not word: self.hover_t.stop(); self.pop.request_hide(); return
        if self.pop.isVisible() and self.pop.word == word: self.pop.hide_t.stop(); return
        self._pending = (word, pos)
        d = self.cfg["hover_delay_ms"]; self.hover_t.start(max(d, 700) if self.cfg["dict_mode"] == "llm" else d)

    def on_click(self, word, pos): self.hover_t.stop(); self.lookup(word, pos, pinned=True)

    def _meta(self, word):
        out = []
        g = next((g for g in self.db.glossary() if g["term"].lower() == word.lower()), None)
        if g: out.append("🏷 " + ("giữ nguyên" if g["mode"] == "keep" or not g["vi"] else f"→ {html.escape(g['vi'])}") + (f" — {html.escape(g['note'])}" if g["note"] else ""))
        if self.db.has_vocab(word): out.append("📖 đã có trong sổ từ")
        return ("<div style='color:%s;font-size:11px'>%s</div>" % (self.cfg["accent"], " · ".join(out))) if out else ""

    def lookup(self, word, pos, pinned=False):
        if not word: return
        mode, meta, sent = self.cfg["dict_mode"], self._meta(word), self.cur_line()["src"]
        if mode in ("offline", "auto"):
            r = self.dicts.lookup(word)
            if r: self.pop.show_for(word, r[0], meta, r[1], pos, pinned, "Từ điển offline"); return
            if mode == "offline":
                self.pop.show_for(word, "", meta, "<i>Không có trong từ điển offline.</i>" + ("" if self.dicts.dicts else "<br><i>Chưa nạp file từ điển (Cài đặt → Từ điển).</i>"), pos, pinned, "Từ điển offline"); return
        if mode in ("google", "auto", "online"):
            tl = self.cfg["target_lang"]
            key, fn, wait, srcname = (("on:" + word.lower(), lambda _: online_lookup(word), "Đang tra online…", "dictionaryapi.dev (Anh-Anh)") if mode == "online" else
                             (f"gg:{tl}:{word.lower()}", lambda _: google_lookup(word, tl, self.cfg["timeout_s"]), "Đang dịch…", "Google Translate"))
            cached = self.db.cache_get(key); miss = "<i>Không tìm thấy. Bấm «AI ngữ cảnh».</i>"
            if cached is not None: self.pop.show_for(word, "", meta, cached or miss, pos, pinned, srcname); return
            self.pop.show_for(word, "", meta, f"<i>{wait}</i>", pos, pinned, srcname)
            def done(r): body = r[1] if r else ""; self.db.cache_set(key, body); self.pop.set_body(word, body or miss)
            run(fn, done, lambda e: self.pop.set_body(word, f"<i>Lỗi tra: {html.escape(e)}</i>")); return
        self.explain(word, sent, pos, pinned)

    def explain(self, word, sentence, pos=None, pinned=True):
        key = f"ai:{word.lower()}|{norm(sentence)}"; fmt = lambda t: html.escape(t).replace("\n", "<br>")
        wait = "<i>AI đang giải nghĩa…</i>"
        if pos is not None or not (self.pop.isVisible() and self.pop.word == word): self.pop.show_for(word, "", self._meta(word), wait, pos or QCursor.pos(), pinned, "AI ngữ cảnh")
        else: self.pop.pinned = True; self.pop.source.setText("AI ngữ cảnh"); self.pop.set_body(word, wait)
        cached = self.db.cache_get(key)
        if cached: self.pop.set_body(word, fmt(cached)); return
        def done(t): self.db.cache_set(key, t); self.pop.set_body(word, fmt(t))
        run(lambda _: self.tr.explain(word, sentence), done, lambda e: self.pop.set_body(word, f"<i>Lỗi: {html.escape(e)}</i>"))

    def on_pop_action(self, act, word): self.on_phrase(act, word)

    def on_lang(self, code):
        self.cfg["target_lang"] = code; self.cfg.save()
        if self.cfg["dict_mode"] in ("offline", "online", "llm"): self.cfg["dict_mode"] = "google"   # chọn ngôn ngữ = muốn Google dịch
        if self.pop.word: self.lookup(self.pop.word, self.pop.anchor, pinned=True)

    def on_phrase(self, act, phrase):
        line = self.cur_line()
        if act == "lookup": self.lookup(phrase, QCursor.pos(), pinned=True)
        elif act == "explain": self.explain(phrase, line["src"])
        elif act == "vocab":
            body = self.pop.raw if self.pop.word == phrase and self.pop.isVisible() and "Đang" not in self.pop.raw and "đang" not in self.pop.raw else ""
            self.db.add_vocab(phrase, body, line["src"], line.get("vi", "")); self._toast(f"Đã lưu «{phrase}» vào sổ từ")
        elif act == "keep": self.db.set_term(phrase, "", "keep"); self._toast(f"Glossary: giữ nguyên «{phrase}»")
        elif act == "translate":
            g = next((g for g in self.db.glossary() if g["term"].lower() == phrase.lower()), None)
            d = on_top(QInputDialog()); d.setWindowTitle("Glossary"); d.setLabelText(f"Dịch «{phrase}» là:"); d.setTextValue(g["vi"] if g else "")
            if d.exec() and d.textValue().strip(): self.db.set_term(phrase, d.textValue().strip(), "translate"); self._toast(f"Glossary: {phrase} → {d.textValue().strip()}")
        if act in ("vocab", "keep", "translate") and self.pop.isVisible() and self.pop.word == phrase:
            self.pop.set_body(phrase, self.pop.raw, self._meta(phrase))

    def _toast(self, msg):
        self.ov.status.setText(msg); QTimer.singleShot(2500, lambda: self.ov.status.text() == msg and self.ov.status.setText(""))

    # ---------------- actions
    def on_action(self, k):
        c = self.cfg
        if k == "prev" and self.pos > 0: self.pos -= 1; self.cleared = False; self.render()
        elif k == "next" and self.pos < len(self.history) - 1: self.pos += 1; self.cleared = False; self.render()
        elif k == "pause": self.worker.paused = not self.worker.paused; self.ov.set_paused(self.worker.paused)
        elif k == "rescan": self.last = ""; self.worker.force = True
        elif k == "translate":
            c["translate"] = not c["translate"]; c.save(); self.ov.apply_style(); self._toast("Dịch: " + ("BẬT" if c["translate"] else "TẮT — chỉ câu gốc"))
            if self.history: self.resolve(self.history[self.pos])
        elif k == "lock":
            c["locked"] = not c["locked"]; c.save(); self.ov.set_locked(c["locked"]); self.lock_action.setChecked(c["locked"])
            self._toast("Đã khóa overlay — " + c["hotkeys"].get("lock", "") + " để mở" if c["locked"] else "Đã mở khóa overlay")
        elif k == "clear": self.ov.show_line("", "", "", ""); self.pop.close_pop()
        elif k == "retranslate" and self.history: self.resolve(self.history[self.pos], machine=True)
        elif k in ("region", "speaker", "scan"): self.select_region(k)
        elif k == "scan_retranslate" and self.scan["src"]: self.scan_translate(machine=True)
        elif k == "toggle": self.auto_hidden = False; self.ov.setVisible(not self.ov.isVisible()); self.pop.hide()
        elif k == "clickthrough":
            c["click_through"] = not c["click_through"]; self.ov.set_click_through(c["click_through"]); self.ct_action.setChecked(c["click_through"])
            self._toast("Click-through: " + ("BẬT — " + c["hotkeys"].get("clickthrough", "") + " để tắt" if c["click_through"] else "TẮT"))
        elif k == "hide": self.auto_hidden = False; self.ov.hide(); self.pop.hide(); self._toast("")
        elif k == "subs": on_top(SubsDialog(self.db, self.index, c, self.rebuild_index)).exec(); self.render()
        elif k == "glossary": on_top(GlossaryDialog(self.db, c)).exec(); self._known_words()
        elif k == "vocab": on_top(VocabDialog(self.db)).exec()
        elif k == "settings": self.open_settings()
        elif k == "quit": self.quit()

    def select_region(self, kind):
        ov_vis, scan_vis = self.ov.isVisible() or kind != "scan", self.scan_win.isVisible()
        self.ov.hide(); self.pop.hide(); self.scan_win.hide(); self.worker.paused = True
        def go():
            title = {"region": "Kéo chọn vùng THOẠI cần dịch — Esc để hủy", "scan": "Kéo chọn vùng cần dịch 1 lần (thư, bảng…) — Esc để hủy"}.get(kind, "Kéo chọn vùng TÊN NHÂN VẬT — Esc để hủy / bỏ vùng tên")
            self.sel = RegionSelector(title)
            def ok(r):
                if kind == "scan": end(); self.scan_capture(r); return
                self.cfg["region" if kind == "region" else "speaker_region"] = r; self.cfg.save(); self.last = ""; self.worker.force = True; end()
            def cancel():
                if kind == "speaker" and self.cfg["speaker_region"]:
                    b = QMessageBox.question(None, "Vùng tên nhân vật", "Bỏ vùng tên nhân vật hiện tại?")
                    if b == QMessageBox.Yes: self.cfg["speaker_region"] = None; self.cfg.save()
                end()
            def end():
                self.worker.paused = False; self.ov.set_paused(False)
                if ov_vis: self.ov.show()
                if scan_vis: self.scan_win.show()
            self.sel.selected.connect(ok); self.sel.cancelled.connect(cancel); self.sel.start()
        QTimer.singleShot(180, go)

    # ---------------- chụp & dịch 1 vùng
    def scan_capture(self, r):
        c = self.cfg; use_gem = c["scan_engine"] == "gemini_image" and c["translate"]
        self.scan_win.show_result(self.scan["src"], "", "Gemini đang đọc ảnh…" if use_gem else "Đang OCR…")
        def work(partial):
            with open_sct() as sct: img = grab(sct, r)
            gem_err = ""
            if use_gem:                                          # Gemini đọc ảnh: chép nguyên văn + dịch 1 lần
                try:
                    import io; from PIL import Image; buf = io.BytesIO(); Image.fromarray(img).save(buf, "PNG")
                    return ("gemini",) + self.tr.read_image(buf.getvalue(), partial)
                except Exception as e: gem_err = str(e) or type(e).__name__        # lỗi/hết quota -> quay về OCR
            s = float(c["ocr_scale"] or 1)
            if abs(s - 1) > 0.01: img = ocr._resize(img, s)
            return "ocr", join_lines(ocr.create(c["ocr_engine"], c["ocr_lang"]).recognize(img)), gem_err
        def done(res):
            kind, text, extra = res
            if kind == "gemini":
                self.scan = {"src": text, "vi": extra}; self.scan_win.show_result(text, extra, f"Gemini đọc ảnh · {c['gemini_model']}"); return
            if extra: self._toast(f"Gemini đọc ảnh lỗi ({extra}) — dùng OCR")
            if c["fix_spacing"]: text = self.spacer.fix(text)
            self.scan = {"src": text, "vi": ""}
            if not text.strip(): self.scan_win.show_result("", "", "Không đọc được chữ trong vùng này"); return
            self.scan_translate()
        run(work, done, lambda e: self.scan_win.show_result(self.scan["src"], "", f"Lỗi OCR: {e}"),
            lambda t: self.scan_win.show_result("", t, "Gemini đang đọc ảnh…"))

    def scan_translate(self, machine=False):
        c, sc = self.cfg, self.scan; src = sc["src"]
        if not c["translate"] and not machine: self.scan_win.show_result(src, "", "Không dịch — chỉ câu gốc"); return
        m = self.index.match(src, c["fuzzy_threshold"]) if c["use_subs"] and not machine else None
        if m: sc["vi"] = m.vi; self.scan_win.show_result(src, m.vi, f"Bộ sub · khớp {m.score:.0f}%"); return
        self.scan_win.show_result(src, "", "Đang dịch…")
        def partial(t): self.scan_win.show_result(src, t, "Đang dịch…")
        def done(res): sc["vi"] = res[0]; self.scan_win.show_result(src, res[0], self.tr.label(res[1]))
        run(lambda p: self.tr.translate(src, "", [], p, engine=c["scan_engine"]), done, lambda e: self.scan_win.show_result(src, "", f"Lỗi dịch: {e}"), partial)

    def open_settings(self):
        c = self.cfg; old = {k: (list(c[k]) if isinstance(c[k], list) else c[k]) for k in ("ocr_engine", "ocr_lang", "dict_files", "gender", "player_name", "name_tokens", "translate")}
        d = on_top(SettingsDialog(c, on_preview=lambda: (self.ov.apply_style(), self.pop.apply_style())))   # đổi màu/khung -> overlay đổi ngay
        d.btn_snap.clicked.connect(lambda: setattr(self.worker, "snapshot_req", str(DATA_DIR / "region_snapshot.png")))
        if not d.exec(): return
        d.apply()
        if d.installed or (c["ocr_engine"], c["ocr_lang"]) != (old["ocr_engine"], old["ocr_lang"]): self.worker.reload_engine = True
        if c["dict_files"] != old["dict_files"]:
            self.dicts.load(c["dict_files"])
            if self.dicts.errors: QMessageBox.warning(None, "Từ điển", "\n".join(self.dicts.errors))
        if any(c[k] != old[k] for k in ("gender", "player_name", "name_tokens")): self.rebuild_index()
        self.ov.apply_style(); self.pop.apply_style(); self.scan_win.apply_style(); self._register_hotkeys(); self.render()
        if c["translate"] != old["translate"] and self.history: self.resolve(self.history[self.pos])

    def quit(self):
        self.cfg.save(); self.worker.stop(); self.tray.hide(); self.q.quit()

def main():
    qapp = QApplication(sys.argv); qapp.setQuitOnLastWindowClosed(False); qapp.setApplicationName("WuWa Sub")
    a = App(qapp); qapp.aboutToQuit.connect(lambda: a.cfg.save())
    sys.exit(qapp.exec())
