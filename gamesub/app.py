import html, os, re, sys, traceback
from pathlib import Path
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QTimer, QPoint, QProcess, QUrl
from PySide6.QtGui import QIcon, QCursor, QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QInputDialog, QMessageBox, QProgressDialog
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
from .ui_region import RegionSelector, RegionFlash, to_logical
from .ui_scan import ScanWindow
from . import winapp, updater, __version__
from .capture import open_sct, grab
from . import ocr
from .textnorm import paragraphs
from .ui_dialogs import SettingsDialog, GlossaryDialog, VocabDialog, SubsDialog, _Job
from .i18n import tr, N_

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

ICON = Path(__file__).resolve().parent / "assets" / "icon.ico"
WAIT_ONLINE, WAIT_GOOGLE, WAIT_AI = N_("app.looking_up_online"), N_("app.translating"), N_("app.ai_is_explaining")     # chữ chờ trong popup tra từ (dịch lúc hiện)

class App:
    def __init__(self, qapp):
        self.q = qapp; DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg = Config(); self.db = DB(DATA_DIR / "gamesub.db")
        self.index = SubIndex(); self.spacer = Spacer(); self.rebuild_index()
        self.dicts = Dictionaries().load(cfg["dict_files"])
        self.tr = Translator(cfg, self.db)
        self.history, self.pos, self.last, self.seq, self.cleared, self.noted = [], -1, "", 0, False, set()
        self.ov = Overlay(cfg); self.pop = WordPopup(cfg); winapp.accept_show(int(self.ov.winId()))
        self.lookup_ctx = None                    # câu ngữ cảnh khi tra từ trong cửa sổ Dịch vùng
        self.inflight = set()                     # tra từ đang chờ kết quả -> không gửi trùng
        self.ov.action.connect(self.on_action); self.ov.word_hover.connect(lambda w, p: self._hover_from(None, w, p)); self.ov.word_click.connect(lambda w, p: self._click_from(None, w, p))
        self.scan_win = ScanWindow(cfg); self.scan = {"src": "", "vi": ""}
        self.flash = []; self.flash_t = QTimer(singleShot=True, interval=3000, timeout=self._flash_off)   # viền "Xem vùng đang chọn"
        self.scan_win.word_hover.connect(lambda w, p: self._hover_from(self.scan, w, p)); self.scan_win.word_click.connect(lambda w, p: self._click_from(self.scan, w, p))
        self.scan_win.action.connect(self.on_action)
        self.ov.phrase_action.connect(lambda act, ph: (setattr(self, "lookup_ctx", None), self.on_phrase(act, ph))); self.pop.act.connect(self.on_pop_action)
        self.pop.lang_changed.connect(self.on_lang)
        self.hover_t = QTimer(singleShot=True, timeout=lambda: self.lookup(*self._pending)); self._pending = ("", QPoint())
        self.idle_t = QTimer(singleShot=True, timeout=self._auto_hide); self.auto_hidden = False
        self.ov.set_click_through(cfg["click_through"])
        self.worker = CaptureWorker(cfg)
        self.worker.text_ready.connect(self.on_text); self.worker.error.connect(self.on_error); self.worker.status.connect(self.ov.status.setText)
        self.worker.start()
        self.hk = Hotkeys(qapp); self.hk.triggered.connect(self.on_action); self._register_hotkeys()
        self.hk.show_requested.connect(self.on_show_requested)
        self._tray()
        self.elev_warned = set(); self.elev_t = QTimer(interval=2000, timeout=self._check_elevation); self.elev_t.start()
        self.update_info = None
        if cfg["check_updates"]: QTimer.singleShot(5000, self.check_update)
        self.ov.show()
        hint = [] if cfg["region"] else [tr("app.press_select_region_button_or", hk=cfg["hotkeys"]["region"])]
        if not len(self.index): hint.append(tr("app.press_folder_button_subtitle_pack"))
        if self.dicts.errors: hint.append(tr("app.dictionary_error_e", e="; ".join(self.dicts.errors)))
        self.ov.show_line("", "", " ".join(hint) or tr("app.ready"), tr("app.n_subtitle_lines", n=f"{len(self.index):,}"))

    # ---------------- setup
    def rebuild_index(self):
        c = self.cfg; n = self.index.build(self.db.all_subs(), c["gender"], c["name_tokens"], c["player_name"]); self._known_words(); return n

    def _known_words(self):
        """Tên riêng/từ trong bộ sub + glossary: không tách khi sửa chữ OCR dính."""
        src = " ".join(s for s, _ in self.db.all_subs()) + " " + " ".join(g["term"] for g in self.db.glossary()) + " " + self.cfg["player_name"]
        self.spacer.set_known(WORD_RE.findall(src))

    def _register_hotkeys(self):
        errs = self.hk.register(self.cfg["hotkeys"])
        if errs: self.ov.status.setText(tr("app.hotkey_conflict_keys", keys=", ".join(errs)))

    def _tray(self):
        self.icon = QIcon(str(ICON)); self.q.setWindowIcon(self.icon)          # vẽ lại: python tools/make_icon.py
        self.tray = QSystemTrayIcon(self.icon); m = QMenu()
        for txt, k in [(N_("tray.toggle"), "toggle"), (N_("tray.scan"), "scan"), (N_("tray.region"), "region"), (N_("tray.pause"), "pause"), (N_("tray.subs"), "subs"),
                       (N_("tray.glossary"), "glossary"), (N_("tray.vocab"), "vocab"), (N_("tray.settings"), "settings"), (N_("tray.check_update"), "update"), (None, None)] + ([] if winapp.self_elevated() else [(N_("tray.relaunch_admin"), "relaunch_admin")]) + [(N_("tray.quit"), "quit")]:
            if txt is None: m.addSeparator(); continue
            a = QAction(tr(txt).replace("&", "&&"), m); a.triggered.connect(lambda _=0, k=k: self.on_action(k)); m.addAction(a)
            if k == "pause":
                self.ct_action = a = QAction(tr("app.click_through_mouse_passes_through"), m); a.setCheckable(True); a.setChecked(self.cfg["click_through"])
                a.triggered.connect(lambda _=0: self.on_action("clickthrough")); m.addAction(a)
                self.lock_action = a = QAction(tr("app.lock_overlay"), m); a.setCheckable(True); a.setChecked(self.cfg["locked"])
                a.triggered.connect(lambda _=0: self.on_action("lock")); m.addAction(a)
        self.tray.setContextMenu(m); self.tray.setToolTip("Game Sub"); self.tray_menu = m
        self.tray.activated.connect(lambda r: self.on_action("toggle") if r == QSystemTrayIcon.Trigger else None)
        self.tray.messageClicked.connect(lambda: self.update_info and self.ask_update(self.update_info))
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
        if not c["translate"] and not machine: line.update(vi="", tag=tr("app.not_translating_source_text_only"), notr=True, alert=False); self.render(line); return
        if c["use_subs"] and not machine:
            m = self.index.match(line["src"], c["fuzzy_threshold"])
            if m: line.update(vi=m.vi, tag=tr("app.subtitle_pack_p_match", p=f"{m.score:.0f}"), notr=False, alert=False); self.render(line); return
        line.update(tag="", busy=True, notr=False, alert=False); self.render(line)               # không hiện "Đang dịch…"
        i = next((k for k, l in enumerate(self.history) if l is line), len(self.history))
        ctx = [(l["speaker"], l["src"], l["vi"]) for l in self.history[max(0, i - c["context_lines"]):i]] if c["context_lines"] else []
        def partial(t): line["vi"] = t; self.render(line)
        def done(res): line.update(vi=res[0], tag=self.tr.label(res[1]) + self._note(res[2] if len(res) > 2 else ""), busy=False); self.render(line)
        def err(e): line.update(tag=tr("app.translation_error_e", e=e), busy=False, alert=True); self.render(line)
        run(lambda p: self.tr.translate(line["src"], line["speaker"], ctx, p), done, err, partial)

    def _note(self, note):
        """Lý do bỏ qua Gemini (lỗi key/quota…) chỉ báo 1 lần cho mỗi loại; đổi cài đặt thì báo lại."""
        if not note or note in self.noted: return ""
        self.noted.add(note); return f" · {note}"

    def render(self, line=None):
        if not self.history: return
        cur = self.history[self.pos]
        if line is not None and (line is not cur or self.cleared): return     # đã xóa (hết thoại): bản dịch về muộn không hiện lại
        nav = f"  [{self.pos + 1}/{len(self.history)}]" if self.pos != len(self.history) - 1 else ""
        hold = cur.get("busy") or cur.get("alert") or cur.get("notr")       # đang dịch / lỗi / tắt dịch: không lấy câu gốc làm bản dịch
        self.ov.show_line(cur["speaker"], cur["src"], cur["vi"] or ("" if hold else cur["src"]), cur["tag"] + nav, alert=bool(cur.get("alert")))

    def _check_elevation(self):
        """Game chạy quyền admin mà GameSub thì không -> Windows (UIPI) chặn hotkey/giữ phím mở khóa/focus: báo 1 lần."""
        if sys.platform != "win32" or winapp.self_elevated(): self.elev_t.stop(); return
        pid, exe = winapp.foreground(); tgt = self.cfg["target_app"]
        if not exe or exe in self.elev_warned or (tgt and exe != tgt) or not winapp.elevated(pid): return
        self.elev_warned.add(exe)
        msg = tr("app.exe_runs_as_administrator_so", exe=exe)
        self.update_info = None                  # bấm thông báo này không mở hộp cập nhật
        self.ov.status.setText(tr("app.game_runs_as_administrator_see")); self.tray.showMessage("Game Sub", msg, QSystemTrayIcon.Warning, 8000)

    def _auto_hide(self):
        if self.ov.isVisible() and not self.ov.underMouse() and not self.pop.isVisible():
            self.ov.hide(); self.auto_hidden = True

    def on_error(self, msg): self.ov._tag = msg; self.ov._alert = True; self.ov._tag_vis()

    # ---------------- tra từ
    def cur_line(self):
        if self.lookup_ctx: return self.lookup_ctx
        return self.history[self.pos] if self.history else {"src": self.ov.src, "vi": ""}

    def _hover_from(self, ctx, word, pos):
        if word: self.lookup_ctx = ctx
        self.on_hover(word, pos)

    def _click_from(self, ctx, word, pos): self.lookup_ctx = ctx; self.on_click(word, pos)

    def on_hover(self, word, pos):
        if self.cfg["popup_trigger"] != "hover": return          # mặc định: chỉ bấm vào từ mới hiện nghĩa
        if self.pop.pinned and self.pop.isVisible(): return
        if not word: self.hover_t.stop(); self.pop.request_hide(); return
        if self.pop.isVisible() and self.pop.word == word: self.pop.hide_t.stop(); return
        self._pending = (word, pos)
        d = self.cfg["hover_delay_ms"]; self.hover_t.start(max(d, 700) if self.cfg["dict_mode"] == "llm" else d)

    def on_click(self, word, pos): self.hover_t.stop(); self.lookup(word, pos, pinned=True)

    def _meta(self, word):
        out = []
        g = next((g for g in self.db.glossary() if g["term"].lower() == word.lower()), None)
        if g: out.append("🏷 " + (tr("app.keep_as_is") if g["mode"] == "keep" or not g["vi"] else f"→ {html.escape(g['vi'])}") + (f" — {html.escape(g['note'])}" if g["note"] else ""))
        if self.db.has_vocab(word): out.append("📖 " + tr("app.already_in_vocabulary"))
        return ("<div style='color:%s;font-size:11px'>%s</div>" % (self.cfg["accent"], " · ".join(out))) if out else ""

    def lookup(self, word, pos, pinned=False):
        if not word: return
        mode, meta, sent = self.cfg["dict_mode"], self._meta(word), self.cur_line()["src"]
        if mode in ("offline", "auto"):
            r = self.dicts.lookup(word)
            if r: self.pop.show_for(word, r[0], meta, r[1], pos, pinned, tr("app.offline_dictionary")); return
            if mode == "offline":
                self.pop.show_for(word, "", meta, "<i>" + tr("app.not_in_offline_dictionary") + "</i>" + ("" if self.dicts.dicts else "<br><i>" + tr("app.no_dictionary_file_loaded_settings") + "</i>"), pos, pinned, tr("app.offline_dictionary")); return
        if mode in ("google", "auto", "online"):
            tl = self.cfg["target_lang"]
            key, fn, wait, srcname = (("on:" + word.lower(), lambda _: online_lookup(word), WAIT_ONLINE, tr("app.dictionaryapi_dev_english_english")) if mode == "online" else
                             (f"gg:{tl}:{word.lower()}", lambda _: google_lookup(word, tl, self.cfg["timeout_s"]), WAIT_GOOGLE, "Google Translate"))
            cached = self.db.cache_get(key); miss = "<i>" + tr("app.not_found_press_ai_in") + "</i>"
            if cached is not None: self.pop.show_for(word, "", meta, cached or miss, pos, pinned, srcname); return
            self.pop.show_for(word, "", meta, f"<i>{tr(wait)}</i>", pos, pinned, srcname)
            self._fetch(key, fn, lambda r: self.pop.set_body(word, (r[1] if r else "") or miss), lambda r: (r[1] if r else ""),
                        lambda e: self.pop.set_body(word, "<i>" + tr("app.lookup_error_e", e=html.escape(e)) + "</i>")); return
        self.explain(word, sent, pos, pinned)

    def explain(self, word, sentence, pos=None, pinned=True):
        key = f"ai:{word.lower()}|{norm(sentence)}"; fmt = lambda t: html.escape(t).replace("\n", "<br>")
        wait = f"<i>{tr(WAIT_AI)}</i>"
        if pos is not None or not (self.pop.isVisible() and self.pop.word == word): self.pop.show_for(word, "", self._meta(word), wait, pos or QCursor.pos(), pinned, tr("app.ai_in_context"))
        else: self.pop.pinned = True; self.pop.source.setText(tr("app.ai_in_context")); self.pop.set_body(word, wait)
        cached = self.db.cache_get(key)
        if cached: self.pop.set_body(word, fmt(cached)); return
        self._fetch(key, lambda _: self.tr.explain(word, sentence), lambda t: self.pop.set_body(word, fmt(t)), lambda t: t,
                    lambda e: self.pop.set_body(word, "<i>" + tr("app.error_e", e=html.escape(e)) + "</i>"))

    def _fetch(self, key, fn, show, to_cache, error):
        """Gọi mạng 1 lần cho mỗi key: đang chờ thì không gửi trùng (popup tự cập nhật khi kết quả về)."""
        if key in self.inflight: return
        self.inflight.add(key)
        def done(r): self.inflight.discard(key); self.db.cache_set(key, to_cache(r)); show(r)
        def err(e): self.inflight.discard(key); error(e)
        run(fn, done, err)

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
            waiting = self.pop.raw in {f"<i>{tr(w)}</i>" for w in (WAIT_ONLINE, WAIT_GOOGLE, WAIT_AI)}     # nghĩa chưa về thì không lưu chữ "Đang…"
            body = self.pop.raw if self.pop.word == phrase and self.pop.isVisible() and not waiting else ""
            self.db.add_vocab(phrase, body, line["src"], line.get("vi", "")); self._toast(tr("app.saved_w_vocabulary", w=phrase))
        elif act == "keep": self.db.set_term(phrase, "", "keep"); self._toast(tr("app.glossary_keep_w_as_is", w=phrase))
        elif act == "translate":
            g = next((g for g in self.db.glossary() if g["term"].lower() == phrase.lower()), None)
            d = on_top(QInputDialog()); d.setWindowTitle(tr("app.glossary_title")); d.setLabelText(tr("app.translate_w_as", w=phrase)); d.setTextValue(g["vi"] if g else "")
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
            c["translate"] = not c["translate"]; c.save(); self.ov.apply_style(); self._toast(tr("app.translation_on") if c["translate"] else tr("app.translation_off_source_text_only"))
            if self.history: self.resolve(self.history[self.pos])
        elif k == "lock":
            c["locked"] = not c["locked"]; c.save(); self.ov.set_locked(c["locked"]); self.lock_action.setChecked(c["locked"])
            self._toast(tr("app.overlay_locked_mouse_passes_through", hk=c["hotkeys"].get("lock", "")) if c["locked"] else tr("app.overlay_unlocked"))
        elif k == "clear": self.ov.show_line("", "", "", ""); self.pop.close_pop()
        elif k == "retranslate" and self.history: self.resolve(self.history[self.pos], machine=True)
        elif k in ("region", "speaker", "scan"): self.select_region(k)
        elif k == "show_region": self.show_regions()
        elif k == "scan_retranslate" and self.scan["src"]: self.scan_translate(machine=True)
        elif k == "toggle": self.auto_hidden = False; self.ov.setVisible(not self.ov.isVisible()); self.pop.hide()
        elif k == "clickthrough":
            c["click_through"] = not c["click_through"]; self.ov.set_click_through(c["click_through"]); self.ct_action.setChecked(c["click_through"])
            self._toast(tr("app.click_through_on_hk_turn", hk=c["hotkeys"].get("clickthrough", "")) if c["click_through"] else tr("app.click_through_off"))
        elif k == "hide": self.auto_hidden = False; self.ov.hide(); self.pop.hide(); self._toast("")
        elif k == "subs": on_top(SubsDialog(self.db, self.index, c, self.rebuild_index)).exec(); self.render()
        elif k == "glossary": on_top(GlossaryDialog(self.db, c)).exec(); self._known_words()
        elif k == "vocab": on_top(VocabDialog(self.db)).exec()
        elif k == "settings": self.open_settings()
        elif k == "update": self.check_update(manual=True)
        elif k == "relaunch_admin":
            if winapp.relaunch_as_admin(): self.quit()
        elif k == "quit": self.quit()

    def on_show_requested(self):
        """Người dùng mở GameSub lần nữa trong lúc đang chạy -> hiện overlay + báo ở khay."""
        self.auto_hidden = False; self.ov.show(); self.ov.raise_()
        self.update_info = None; self.tray.showMessage("Game Sub", tr("app.already_running"), QSystemTrayIcon.Information, 4000)

    def show_regions(self):
        """Viền sáng quanh vùng thoại + vùng tên nhân vật trong 3 giây; bấm lần nữa thì tắt."""
        if self.flash: self._flash_off(); return
        c = self.cfg
        self.flash = [RegionFlash(to_logical(r), name, col) for r, name, col in
                      [(c["region"], tr("app.dialogue_area"), c["accent"]), (c["speaker_region"], tr("app.speaker_name_area"), "#6ab7e8")] if r]
        if not self.flash: self._toast(tr("app.no_dialogue_area_selected_press", hk=c["hotkeys"]["region"])); return
        for w in self.flash: w.show()
        self.flash_t.start()

    def _flash_off(self):
        self.flash_t.stop()
        for w in self.flash: w.close(); w.deleteLater()
        self.flash = []

    def select_region(self, kind):
        ov_vis, scan_vis = self.ov.isVisible() or kind != "scan", self.scan_win.isVisible()
        self.ov.hide(); self.pop.hide(); self.scan_win.hide(); self.worker.paused = True
        def go():
            title = {"region": N_("app.drag_select_dialogue_area_translate"), "scan": N_("app.drag_select_area_translate_once")}.get(kind, N_("app.drag_select_speaker_name_area"))
            self.sel = RegionSelector(tr(title))
            def ok(r):
                if kind == "scan": end(); self.scan_capture(r); return
                self.cfg["region" if kind == "region" else "speaker_region"] = r; self.cfg.save(); self.last = ""; self.worker.force = True; end()
            def cancel():
                if kind == "speaker" and self.cfg["speaker_region"]:
                    b = QMessageBox.question(None, tr("app.speaker_name_area"), tr("app.remove_current_speaker_name_area"))
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
        self.scan_win.show_result(self.scan["src"], "", tr("app.gemini_is_reading_image") if use_gem else tr("app.running_ocr"))
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
            return "ocr", paragraphs(ocr.create(c["ocr_engine"], c["ocr_lang"]).recognize(img)), gem_err     # giữ chia đoạn như trong ảnh
        def done(res):
            kind, text, extra = res
            if kind == "gemini":
                self.scan = {"src": text, "vi": extra}; self.scan_win.show_result(text, extra, tr("app.gemini_image_reading_model", model=c["gemini_model"])); return
            note = tr("app.gemini_image_reading_failed_e", e=extra) if extra else ""
            if c["fix_spacing"]: text = self.spacer.fix(text)
            self.scan = {"src": text, "vi": "", "note": note}
            if not text.strip(): self.scan_win.show_result("", "", tr("app.no_text_could_be_read") + self._note(note)); return
            self.scan_translate()
        run(work, done, lambda e: self.scan_win.show_result(self.scan["src"], "", tr("app.ocr_error_e", e=e)),
            lambda t: self.scan_win.show_result("", t, tr("app.gemini_is_reading_image")))

    def scan_translate(self, machine=False):
        c, sc = self.cfg, self.scan; src = sc["src"]
        if not c["translate"] and not machine: self.scan_win.show_result(src, "", tr("app.not_translating_source_text_only")); return
        m = self.index.match(src, c["fuzzy_threshold"]) if c["use_subs"] and not machine else None
        if m: sc["vi"] = m.vi; self.scan_win.show_result(src, m.vi, tr("app.subtitle_pack_p_match", p=f"{m.score:.0f}")); return
        self.scan_win.show_result(src, "", tr("app.translating"))
        def partial(t): self.scan_win.show_result(src, t, tr("app.translating"))
        def done(res):
            sc["vi"] = res[0]
            self.scan_win.show_result(src, res[0], self.tr.label(res[1]) + self._note(sc.get("note", "")) + self._note(res[2] if len(res) > 2 else ""))
        run(lambda p: self.tr.translate(src, "", [], p, engine=c["scan_engine"]), done, lambda e: self.scan_win.show_result(src, "", tr("app.translation_error_e", e=e)), partial)

    def open_settings(self):
        c = self.cfg; old = {k: (list(c[k]) if isinstance(c[k], list) else c[k]) for k in ("ocr_engine", "ocr_lang", "dict_files", "gender", "player_name", "name_tokens", "translate", "ui_lang")}
        d = on_top(SettingsDialog(c, on_preview=lambda: (self.ov.apply_style(), self.pop.apply_style())))   # đổi màu/khung -> overlay đổi ngay
        d.btn_snap.clicked.connect(lambda: setattr(self.worker, "snapshot_req", str(DATA_DIR / "region_snapshot.png")))
        d.btn_show.clicked.connect(lambda: (self._flash_off(), self.show_regions()))
        d.btn_update.clicked.connect(lambda: self.check_update(manual=True, parent=d))
        self.hk.register({})                      # nhả hotkey khi mở Cài đặt: bấm tổ hợp vào ô hotkey không kích hoạt hành động
        if not d.exec(): self._register_hotkeys(); return
        d.apply(); self.noted.clear()
        if d.installed or (c["ocr_engine"], c["ocr_lang"]) != (old["ocr_engine"], old["ocr_lang"]): self.worker.reload_engine = True
        if c["dict_files"] != old["dict_files"]:
            self.dicts.load(c["dict_files"])
            if self.dicts.errors: QMessageBox.warning(None, tr("app.dictionary"), "\n".join(self.dicts.errors))
        if any(c[k] != old[k] for k in ("gender", "player_name", "name_tokens")): self.rebuild_index()
        self.ov.apply_style(); self.pop.apply_style(); self.scan_win.apply_style(); self._register_hotkeys(); self.render()
        if c["translate"] != old["translate"] and self.history: self.resolve(self.history[self.pos])
        if c["ui_lang"] != old["ui_lang"] and QMessageBox.question(
                None, "Game Sub", "Đổi ngôn ngữ cần mở lại app. Mở lại ngay?\nChanging the language requires restarting the app. Restart now?"   # no-i18n: song ngữ
                ) == QMessageBox.Yes: self.restart()

    # ---------------- cập nhật (updater.py)
    def check_update(self, manual=False, parent=None):
        """Hỏi GitHub có bản mới không. manual = người dùng bấm: báo cả khi đã mới nhất / lỗi; tự động: chỉ hiện thông báo khay."""
        def done(info):
            if manual and not info: QMessageBox.information(parent, tr("updater.title"), tr("updater.up_to_date", ver=__version__))
            elif manual: self.ask_update(info, parent)
            elif info:
                self.update_info = info
                self.tray.showMessage("Game Sub", tr("updater.available_tray", tag=info["tag"]), QSystemTrayIcon.Information, 10000)
        def err(e):
            if manual: QMessageBox.warning(parent, tr("updater.title"), tr("updater.check_failed_e", e=e))
        run(lambda _: updater.check(), done, err)

    def ask_update(self, info, parent=None):
        self.update_info = None
        box = on_top(QMessageBox(QMessageBox.Question, tr("updater.title"), tr("updater.new_version", tag=info["tag"], ver=__version__), parent=parent))
        box.setInformativeText(tr("updater.will_restart", mb=f"{info['size'] / 1e6:.0f}") if updater.can_install() else tr("updater.from_source"))
        if info["notes"]: box.setDetailedText(info["notes"])
        go = box.addButton(tr("updater.update_now"), QMessageBox.AcceptRole) if updater.can_install() else None
        page = box.addButton(tr("updater.open_page"), QMessageBox.ActionRole); box.addButton(tr("updater.later"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is page: QDesktopServices.openUrl(QUrl(info["page"]))
        elif go and box.clickedButton() is go: self._install_update(info, parent)

    def _install_update(self, info, parent):
        dlg = on_top(QProgressDialog(tr("settings.ocr.downloading"), tr("settings.ocr.cancel"), 0, 100, parent)); dlg.setWindowTitle(tr("updater.title"))
        dlg.setMinimumWidth(420); dlg.setWindowModality(Qt.ApplicationModal); dlg.setAutoClose(False); dlg.setAutoReset(False); dlg.show()
        job = _Job(lambda p: updater.download(info, p))
        job.progress.connect(lambda t, p: (dlg.setLabelText(t), dlg.setValue(p))); dlg.canceled.connect(lambda: setattr(job, "cancel", True))
        def done(e):
            dlg.close()
            if e == "cancel": return
            try:
                if e: raise RuntimeError(e)
                updater.apply(job.result)
            except Exception as ex: QMessageBox.warning(parent, tr("updater.title"), tr("updater.failed_e", e=ex)); return
            self.hk.register({}); self.quit()                  # script đợi tiến trình này tắt rồi mới chép đè
        job.done.connect(done); self._upd_job = job; job.start()

    def restart(self):
        """Mở lại app (đổi ngôn ngữ). Nhả hotkey trước để bản mới đăng ký được."""
        self.hk.register({}); self.cfg.save()
        args = [a for a in sys.argv[1:] if a != "--wait"] + ["--wait"]          # bản mới đợi bản này thoát (single_instance)
        if not getattr(sys, "frozen", False): args = [os.path.abspath(sys.argv[0])] + args
        QProcess.startDetached(sys.executable, args); self.quit()

    def quit(self):
        self.cfg.save(); self.worker.stop(); self.tray.hide(); self.q.quit()

def main():
    if sys.platform == "win32" and Config()["run_as_admin"] and not winapp.self_elevated() and winapp.relaunch_as_admin(): return
    if sys.platform == "win32":                     # chạy từ source: taskbar hiện icon app thay vì icon python
        import ctypes; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GameSub")
    qapp = QApplication(sys.argv); qapp.setQuitOnLastWindowClosed(False); qapp.setApplicationName("Game Sub")
    if not winapp.single_instance("--wait" in sys.argv):          # đã có bản đang chạy -> hiện overlay của bản đó, thoát
        if not winapp.show_running(): QMessageBox.information(None, "Game Sub", tr("app.already_running"))
        return
    a = App(qapp); qapp.aboutToQuit.connect(lambda: a.cfg.save())
    sys.exit(qapp.exec())
