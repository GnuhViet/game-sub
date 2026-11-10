"""Smoke test UI offscreen: QT_QPA_PLATFORM=offscreen python tests/test_ui_smoke.py"""
import os, sys, tempfile, time, pathlib
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32": os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))   # offscreen không có font hệ thống
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gamesub.config as C
C.DATA_DIR = Path(tempfile.mkdtemp()); C.CFG_PATH = C.DATA_DIR / "settings.json"
import gamesub.app as A
A.DATA_DIR = C.DATA_DIR
from PySide6.QtCore import QPoint, QRect, QThreadPool, Qt
from PySide6.QtWidgets import QApplication
from gamesub.ui_dialogs import SettingsDialog, GlossaryDialog, VocabDialog, SubsDialog, ReviewDialog
from gamesub.ui_region import RegionSelector, to_physical

class FakeWorker(A.CaptureWorker):
    def run(self):
        while self.running: time.sleep(0.05)
A.CaptureWorker = FakeWorker
INFO = {"tag": "v99.0", "name": "v99.0", "notes": "", "url": "", "size": 1, "digest": "", "page": ""}
A.updater.check = lambda: INFO                    # không gọi GitHub thật

q = QApplication(sys.argv)
def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end: q.processEvents(); time.sleep(0.01)
    QThreadPool.globalInstance().waitForDone(2000); q.processEvents()

a = A.App(q)
msgs = []; a.tray.showMessage = lambda *x: msgs.append(x)
a.check_update(); pump(); assert a.update_info is INFO and "v99.0" in msgs[0][1]     # tự kiểm tra: chỉ báo ở khay
assert C.DEFAULTS["check_updates"] is False                                           # mặc định không tự kiểm tra
a.ov.hide(); a.on_show_requested(); assert a.ov.isVisible() and msgs[-1][1] == A.tr("app.already_running")   # mở bản thứ 2 -> hiện overlay
g0 = a.ov.geometry(); a.ov._set_bar(True); a.ov.resize(820, 170); pump(0.1); assert not a.ov.flow.hidden and a.ov.grip.isVisible()
a.ov.resize(330, 170); pump(0.1); assert a.ov.btns["lock"] in a.ov.flow.hidden and a.ov.more.x() > 0     # hẹp -> dồn vào ☰
a.ov._set_bar(False); assert not a.ov.grip.isVisible(); a.ov.setGeometry(g0)                             # không rê chuột -> ẩn nút đổi cỡ
a.ov._hover_bar(True); assert a.ov.anim.state() == a.ov.anim.State.Running; a.ov._set_bar(False)          # có animation
a.cfg["animations"] = False; a.ov._hover_bar(True); assert a.ov.bar.isVisible() and a.ov._exp == 1          # tắt -> hiện ngay
a.ov._hover_bar(False); assert not a.ov.bar.isVisible() and a.ov._exp == 0; a.cfg["animations"] = True
from PySide6.QtGui import QKeyEvent; from PySide6.QtCore import QEvent
from gamesub.ui_dialogs import KeyCapture
kc = KeyCapture("", hotkey=True)
kc.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_R, Qt.ControlModifier | Qt.AltModifier)); assert kc.text() == "Ctrl+Alt+R", kc.text()
kc.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Control, Qt.ControlModifier)); assert kc.text() == "Ctrl+Alt+R"     # chỉ phím bổ trợ -> bỏ qua
kc.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)); assert kc.text() == ""
(C.DATA_DIR / "d.tsv").write_text("finally\tcuối cùng\nwake\tthức dậy\n", "utf-8")
a.cfg["dict_files"] = [str(C.DATA_DIR / "d.tsv")]; a.dicts.load(a.cfg["dict_files"])
a.db.add_subs("vh.csv", [("Rover, you finally woke up.", "Rover, cuối cùng anh cũng tỉnh rồi.")]); a.rebuild_index()

# 1) sub match
a.on_text("Yangyang", "Rover, you finaIly woke up."); pump()
assert a.ov.vi.text() == "Rover, cuối cùng anh cũng tỉnh rồi." and a.ov._tag.startswith("Bộ sub"), (a.ov.vi.text(), a.ov._tag)
assert a.ov.speaker.text() == "Yangyang" and 'href="w:' in a.ov.src_lbl.text()
# dedupe
n = len(a.history); a.on_text("", "Rover, you finally woke up"); assert len(a.history) == n

# 2) machine translation fallback (mock) + streaming partial
calls = []
def fake_tr(src, spk, ctx, partial, engine=None):
    calls.append(ctx)
    if engine is None: assert a.ov._tag == "" and a.ov.vi.text() == ""     # thoại: không hiện "Đang dịch…", không hiện tạm câu gốc
    partial("Đang…"); return "Câu dịch máy.", "gemini"
a.tr.translate = fake_tr
a.on_text("", "Something brand new happens here."); pump()
assert a.ov.vi.text() == "Câu dịch máy." and a.ov._tag == "Gemini · gemini-2.5-flash-lite", a.ov._tag
assert calls[0] and calls[0][-1][2] == "Rover, cuối cùng anh cũng tỉnh rồi."    # context truyền vào
# lỗi dịch
def bad(*_): raise RuntimeError("429 hết quota")
a.tr.translate = bad; a.on_text("", "Another line that fails."); pump()
assert "Lỗi dịch" in a.ov._tag and a.ov._alert and "Lỗi dịch" in a.ov.tag.text()      # lỗi: hiện cả khi không rê chuột

# 3) history nav
a.goto(a.pos - 1); assert "[2/3]" in a.ov._tag; a.goto(len(a.history) - 1); assert "[" not in a.ov._tag
rows = []; a.ov.pick_from = lambda r: rows.extend(r); a.on_action("history")       # menu lịch sử: mới nhất trên cùng, đang xem có dấu
assert [r[0] for r in rows] == [2, 1, 0] and rows[0][3] and rows[2][1] == "Rover, cuối cùng anh cũng tỉnh rồi." and "woke up" in rows[2][2], rows
a.goto(0); rows.clear(); a.on_action("history"); assert rows[0][:2] == (2, "Về câu mới nhất") and rows[1][0] is None and rows[4][3]
a.ov.pick_from = lambda r: 2; a.on_action("history"); assert a.pos == 2 and "[" not in a.ov._tag
del a.ov.pick_from
from PySide6.QtCore import QTimer as _QT
_QT.singleShot(150, lambda: QApplication.activePopupWidget() and QApplication.activePopupWidget().close())
assert a.ov.pick_from([(0, "x" * 500, "tip", True), (None, "", "", False), ("", "mờ", "", False)]) is None     # menu thật mở/đóng không lỗi

# 3b) mặc định: rê chuột không hiện popup, bấm vào từ mới hiện
assert a.cfg["popup_trigger"] == "click"; a.pop.hide(); a.on_hover("finally", QPoint(500, 500)); pump(0.5); assert not a.pop.isVisible()
a.on_click("finally", QPoint(500, 500)); pump(); assert a.pop.isVisible() and a.pop.word == "finally"; a.pop.close_pop()
a.cfg["popup_trigger"] = "hover"

# 4) hover lookup offline
a.goto(a.pos - 2)
a.on_hover("finally", QPoint(500, 500)); pump(0.5)
assert a.pop.isVisible() and "cuối cùng" in a.pop.body.text(), a.pop.body.text()
a.cfg["dict_mode"] = "offline"; a.on_hover("", QPoint()); pump(0.7)
a.on_hover("woke", QPoint(520, 500)); pump(0.5); assert a.pop.word == "woke" and "Không có" in a.pop.raw, a.pop.raw

# 5) popup actions: lưu sổ từ, glossary, AI ngữ cảnh
a.on_click("finally", QPoint(500, 500)); pump(0.2); assert a.pop.pinned
a.on_pop_action("vocab", "finally"); v = a.db.vocab()[0]
assert v[0] == "finally" and "cuối cùng" in v[1] and v[2].startswith("Rover") and "📖" in a.pop.body.text(), v
a.on_phrase("keep", "Rover"); assert a.db.terms_in("hi Rover")[0]["mode"] == "keep"
a.tr.explain = lambda w, s: f"/ˈfaɪnəli/ (adv) cuối cùng — {w}"
a.on_pop_action("explain", "finally"); pump(); assert "ˈfaɪnəli" in a.pop.raw
assert any(k[0].startswith("ai:finally|") for k in a.db.q("SELECT k FROM cache"))
a.cfg["dict_mode"] = "llm"; a.pop.hide(); a.pop.pinned = False; a.on_hover("woke", QPoint(1, 1)); pump(1.0); assert "cuối cùng — woke" in a.pop.raw

# 5b) Google dịch tự động trong popup + đổi ngôn ngữ đích
langs = []
A.google_lookup = lambda w, tl, t=6: (langs.append(tl), (f"{w}-{tl}", f"<b>{w}-{tl}</b>"))[1]
a.cfg["dict_mode"] = "auto"; a.pop.hide(); a.pop.pinned = False
a.on_click("woke", QPoint(300, 300)); pump(); assert "woke-vi" in a.pop.raw and langs == ["vi"] and a.pop.source.text() == "Google Translate", a.pop.raw
a.pop.close_btn.click(); assert not a.pop.isVisible() and not a.pop.pinned
a.on_click("woke", QPoint(300, 300)); pump()
a.on_lang("ja"); pump(); assert a.cfg["target_lang"] == "ja" and "woke-ja" in a.pop.raw and a.pop.pinned
a.on_click("woke", QPoint(300, 300)); pump(); assert langs == ["vi", "ja"]            # lần 2 lấy từ cache
a.cfg["dict_mode"] = "offline"; a.on_lang("vi"); pump(); assert a.cfg["dict_mode"] == "google"
a.cfg["dict_mode"] = "llm"

# 5c) rê ra/vào khi đang chờ kết quả -> chỉ gọi mạng 1 lần
import threading; gate = threading.Event(); hits = []
A.google_lookup = lambda w, tl, t=6: (hits.append(w), gate.wait(2), (f"{w}-{tl}", f"<b>{w}-{tl}</b>"))[2]
a.cfg["dict_mode"] = "google"; a.pop.hide(); a.pop.pinned = False
for _ in range(4): a.lookup("dawnlight", QPoint(300, 300))
gate.set(); pump(); assert hits == ["dawnlight"] and "dawnlight-" in a.pop.raw and not a.inflight, hits
A.google_lookup = lambda w, tl, t=6: (langs.append(tl), (f"{w}-{tl}", f"<b>{w}-{tl}</b>"))[1]; a.cfg["dict_mode"] = "llm"

# 6) dialogs khởi tạo được
for d in (SettingsDialog(a.cfg), GlossaryDialog(a.db, a.cfg), VocabDialog(a.db), SubsDialog(a.db, a.index, a.cfg, a.rebuild_index)):
    d.show(); pump(0.05); d.close()
seen = []; sd = SettingsDialog(a.cfg, on_preview=lambda: seen.append(1)); sd.show(); pump(0.05)
sl = sd.w["opacity"][0]; sl.setValue(40); assert seen and a.cfg["opacity"] == 0.6     # xem trước trực tiếp
sd.w["show_frame"][0].setChecked(False); sd.w["text_outline"][0].setValue(2); assert not a.cfg["show_frame"] and a.cfg["text_outline"] == 2
sd.reject(); assert a.cfg["opacity"] == 0.82 and a.cfg["show_frame"] and not a.cfg["text_outline"]     # Cancel trả lại
sd = SettingsDialog(a.cfg); sd.w["text_outline"][0].setValue(1); sd.apply(); a.ov.apply_style(); assert a.ov.vi.graphicsEffect().w == 1
assert isinstance(a.ov.vi.graphicsEffect(), __import__("gamesub.ui_overlay", fromlist=["x"]).OutlineEffect); a.ov.grab()
a.cfg["show_frame"] = False; a.ov.update(); a.ov.grab(); a.cfg["show_frame"] = True; a.cfg["text_outline"] = 0; a.ov.apply_style()
a.render(); a.on_action("clear"); assert a.ov.vi.text() == "" and a.ov.src == ""
# tắt dịch: chỉ câu gốc, không gọi máy dịch; bật lại thì dịch câu hiện tại
n_calls = len(calls); a.on_action("translate"); a.on_text("", "Brand new untranslated line here.")
assert a.ov.vi.text() == "" and a.ov.src == "Brand new untranslated line here." and a.ov.src_lbl.isVisibleTo(a.ov) and "Không dịch" in a.ov._tag
a.tr.translate = fake_tr; a.on_action("translate"); pump(); assert a.ov.vi.text() == "Câu dịch máy." and len(calls) == n_calls + 1
sd = SettingsDialog(a.cfg); cb = sd.w["dialog_engine"][0]; cb.setCurrentIndex(cb.findData("gemini_google")); sd.apply(); assert a.cfg["dialog_engine"] == "gemini_google"
assert "openai_key" not in a.cfg and sd.w["scan_engine"][0].count() == 3
assert not sd.gem_warn.isHidden() and "chưa có API key" in sd.gem_warn.text()          # chọn Gemini mà không có key -> cảnh báo
sd.w["gemini_key"][0].setText("k"); assert sd.gem_warn.isHidden()
import gamesub.translator as T; T.Translator.gemini = lambda self, *a, **k: (_ for _ in ()).throw(T.ProviderError("API key sai"))
sd._test_key(); sd._key_job.wait(3000); pump(); assert "API key sai" in sd.key_status.text(), sd.key_status.text()
T.Translator.gemini = lambda self, *a, **k: "OK"; T.Translator.list_models = lambda self, key: ["gemini-3.1-flash-lite", "gemini-3-flash", "gemini-2.5-pro"]
sd._test_key(); sd._key_job.wait(3000); pump(); assert "dùng được" in sd.key_status.text() and sd.model.count() == 3
assert sd.w["gemini_model"][1]() == "gemini-3.1-flash-lite" and "không còn" in sd.key_status.text()      # model cũ không có -> tự chọn
sd.apply(); assert a.cfg["gemini_model"] == "gemini-3.1-flash-lite"; a.cfg["gemini_model"] = "gemini-2.5-flash-lite"
# toolbar: bỏ ghim nút -> ẩn; ⚙ — ✕ luôn hiện và nằm bên phải
sd = SettingsDialog(a.cfg); sd.w["toolbar"][0].item(0).setCheckState(Qt.Unchecked); sd.apply()
assert "history" not in a.cfg["toolbar"]; a.ov.apply_style(); a.ov._set_bar(True); a.ov.show(); pump(0.05)
assert a.ov.btns["history"].isHidden() and not a.ov.btns["pause"].isHidden() and not a.ov.btns["settings"].isHidden()
assert a.ov.btns["quit"].mapTo(a.ov, QPoint(0, 0)).x() > a.ov.width() - 80                       # ✕ ở mép phải
a.cfg["toolbar"].insert(0, "history"); a.ov.apply_style(); a.ov._set_bar(False)
# sắp xếp toolbar: nút ↑ trong Cài đặt đổi thứ tự -> overlay xếp theo
sd = SettingsDialog(a.cfg); lst = sd.w["toolbar"][0]; k1 = lst.item(1).data(Qt.UserRole); lst.setCurrentRow(1)
next(b for b in sd.findChildren(__import__("PySide6.QtWidgets", fromlist=["x"]).QPushButton) if b.toolTip().startswith("Lên")).click(); sd.apply()
assert a.cfg["toolbar"][0] == k1 and a.cfg["toolbar"][1] == "history", a.cfg["toolbar"]
a.ov.apply_style(); a.ov._set_bar(True); pump(0.05); assert a.ov.btns[k1].x() < a.ov.btns["history"].x()
a.cfg["toolbar"].remove(k1); a.cfg["toolbar"].insert(1, k1); a.ov.apply_style(); a.ov._set_bar(False)
from gamesub import __version__
assert any(l.text() == f"Game Sub v{__version__}" for l in SettingsDialog(a.cfg).findChildren(__import__("PySide6.QtWidgets", fromlist=["x"]).QLabel))
# game chạy quyền admin, GameSub không -> cảnh báo 1 lần
W = A.winapp; _orig = (W.self_elevated, W.foreground, W.elevated)
W.self_elevated = lambda: False; W.foreground = lambda: (4242, "client-win64-shipping.exe"); W.elevated = lambda pid: True
shown = []; a.tray.showMessage = lambda *x: shown.append(x)
a._check_elevation(); a._check_elevation(); assert len(shown) == 1 and "quyền admin" in a.ov.status.text() and "client-win64-shipping.exe" in shown[0][1]
W.self_elevated, W.foreground, W.elevated = _orig
# lý do Gemini lỗi chỉ báo 1 lần
assert a._note("Gemini lỗi: API key sai") == " · Gemini lỗi: API key sai" and a._note("Gemini lỗi: API key sai") == "" and a._note("") == ""
assert (C.DATA_DIR / "settings.json").exists()
subd = SubsDialog(a.db, a.index, a.cfg, a.rebuild_index); sub = subd.panel; sub.test.setText("Rover you finally woke up"); sub._test(); assert "100" in sub.test_out.text() or "%" in sub.test_out.text()
# tab Bộ sub trong Cài đặt: thanh trượt ngưỡng + ô thử khớp dùng ngưỡng đang chỉnh (chưa lưu)
sd = SettingsDialog(a.cfg, subs=(a.db, a.index, a.cfg, a.rebuild_index)); sp = sd.subs_panel; sl = sd.w["fuzzy_threshold"][0]
sp.test.setText("Rover you finaly woke up"); sl.setValue(100); assert "#e8a33a" in sp.test_out.text()      # sai 1 chữ: dưới 100% -> không dùng
sl.setValue(80); assert "#3fb950" in sp.test_out.text(); sd.apply(); assert a.cfg["fuzzy_threshold"] == 80
# xem dữ liệu bộ sub: tìm ở luồng nền (kết nối chỉ đọc riêng), nạp dần theo trang, nhấp đúp -> thử khớp
a.db.add_subs("big.csv", [(f"Line {i} 50%_off", f"Câu {i}") for i in range(700)])
def wait_br(b, cond):
    end = time.time() + 3
    while not cond() and time.time() < end: q.processEvents(); time.sleep(0.01)
    assert cond()
sub._browse(); br = sub.browser; wait_br(br, lambda: br.model.rowCount() == 300 and "701" in br.status.text())   # 1 + 700, trang đầu 300
br.model.fetchMore(); wait_br(br, lambda: br.model.rowCount() == 600)
br.q.setText("rover WOKE"); br._apply(); wait_br(br, lambda: br.model.rowCount() == 1 and br.model.done)          # nhiều từ, không phân biệt hoa thường
br.q.setText("50%_"); br._apply(); wait_br(br, lambda: br.model.rowCount() == 300 and "700" in br.status.text())  # % _ là ký tự thường
br.q.setText("0%_"); br.set_file("vh.csv"); wait_br(br, lambda: br.model.done and br.model.rowCount() == 0)
br.q.setText(""); br._apply(); wait_br(br, lambda: br.model.rowCount() == 1)
br._pick(br.model.index(0, 0)); assert sub.test.text() == "Rover, you finally woke up." and "100" in sub.test_out.text()
br.close(); a.db.del_sub_file("big.csv")
gd = GlossaryDialog(a.db, a.cfg); gd._row("Resonator", "Cộng Minh Giả", "translate"); gd._save(); assert any(g["term"] == "Resonator" for g in a.db.glossary())
ReviewDialog(a.db, a.db.vocab()).show(); pump(0.05)

# 7) region selector + quy đổi DPI
rs = RegionSelector(); rs.show(); pump(0.05); rs.close()
class S:
    def geometry(self): return QRect(1920, 0, 1280, 720)
    def devicePixelRatio(self): return 1.5
assert to_physical(S(), QRect(100, 200, 300, 40)) == {"x": 2070, "y": 300, "w": 450, "h": 60}

a.on_action("pause"); assert a.worker.paused; a.on_action("pause")
# 10) chụp & dịch 1 vùng (thư): OCR 1 lần -> cửa sổ riêng, hover tra từ dùng ngữ cảnh của thư
class _Sct:
    def __enter__(self): return self
    def __exit__(self, *a): pass
class _Eng:
    def recognize(self, img): return ["Dear Rover, thank you for", "yourhelp in Jinzhou."]
A.open_sct = _Sct; A.grab = lambda sct, r: None; A.ocr.create = lambda n, l: _Eng(); a.tr.translate = fake_tr
a.scan_capture({"x": 0, "y": 0, "w": 10, "h": 10}); pump()
assert a.scan_win.isVisible() and a.scan_win.src == "Dear Rover, thank you for your help in Jinzhou." and a.scan_win.vi_view.toPlainText() == "Câu dịch máy.", a.scan_win.src
assert "w:" in a.scan_win.src_view.toHtml()
a.cfg["dict_mode"] = "auto"; a.pop.hide(); a.pop.pinned = False
a.scan_win.word_click.emit("help", QPoint(200, 200)); pump(); assert a.cur_line()["src"].startswith("Dear Rover") and a.pop.word == "help"
a.ov.word_hover.emit("woke", QPoint(1, 1)); pump(0.5); assert a.lookup_ctx is None
a.on_action("scan_retranslate"); pump(); assert a.scan_win.tag.text().startswith("Gemini")
# 10b) Gemini đọc ảnh vùng chụp; lỗi thì quay về OCR
a.cfg.update(scan_engine="gemini_image", gemini_key="k")
a.tr.read_image = lambda png, p=None: (p and p("Thư"), (png[:4] == b"\x89PNG" and "Dear Rover, the letter.", "Rover thân mến, lá thư."))[1]
A.grab = lambda sct, r: __import__("numpy").zeros((20, 40, 3), "uint8")
a.scan_capture({"x": 0, "y": 0, "w": 40, "h": 20}); pump()
assert a.scan_win.src == "Dear Rover, the letter." and a.scan_win.vi_view.toPlainText() == "Rover thân mến, lá thư." and a.scan_win.tag.text().startswith("Gemini đọc ảnh")
def gem_fail(png, p=None): raise RuntimeError("429")
a.tr.read_image = gem_fail; a.scan_capture({"x": 0, "y": 0, "w": 40, "h": 20}); pump()
assert a.scan_win.src.startswith("Dear Rover, thank you") and "Gemini đọc ảnh lỗi: 429" in a.scan_win.tag.text(), a.scan_win.tag.text()
a.cfg.update(scan_engine="ocr_google", gemini_key="")
# 10c) vùng chụp khớp bộ sub từng câu: câu khớp lấy bản sub, phần còn lại dịch máy (câu khớp làm ngữ cảnh)
_Eng.recognize = lambda self, img: ["Rover, you finally woke up. Thank you for your help."]
seen = []; a.tr.translate = lambda src, spk, ctx, p=None, engine=None: (seen.append((src, ctx)), ("Cảm ơn đã giúp.", "google"))[1]
a.scan_capture({"x": 0, "y": 0, "w": 10, "h": 10}); pump()
assert a.scan_win.vi_view.toPlainText() == "Rover, cuối cùng anh cũng tỉnh rồi. Cảm ơn đã giúp.", a.scan_win.vi_view.toPlainText()
assert seen[0][0] == "Thank you for your help." and seen[0][1][0][2].startswith("Rover, cuối") and a.scan_win.tag.text().startswith("Bộ sub 1/2")
a.cfg["scan_use_subs"] = False; seen.clear(); a.scan_capture({"x": 0, "y": 0, "w": 10, "h": 10}); pump()
assert seen[0][0] == "Rover, you finally woke up. Thank you for your help." and a.scan_win.vi_view.toPlainText() == "Cảm ơn đã giúp."
a.cfg["scan_use_subs"] = True; a.tr.translate = fake_tr
# 11) nguồn dịch chỉ hiện khi rê chuột; khóa overlay; khung tự giãn; tooltip có hotkey; 1/2 ngôn ngữ
a.ov.show_line("", "Hi.", "Xin chào.", "Google Translate"); assert a.ov.tag.text() == ""
a.ov._set_bar(True); assert a.ov.tag.text() == "Google Translate"; a.ov._set_bar(False)
a.ov.show_line("", "Hi.", "", "Lỗi dịch: x", alert=True); assert a.ov.tag.text() == "Lỗi dịch: x"      # báo lỗi: luôn hiện
a.on_error("Lỗi capture/OCR: x"); assert a.ov.tag.text() == "Lỗi capture/OCR: x"
a.on_action("lock"); assert a.cfg["locked"] and not a.ov.grip.isVisible() and a.lock_action.isChecked() and a.ov.passthrough_wanted()
a.ov.enterEvent(None); assert not a.ov.bar.isVisible(); a.on_action("lock"); assert not a.cfg["locked"]
h0 = a.ov.height(); bottom = a.ov.geometry().bottom()
a.ov.show_line("", "word " * 80, "chữ " * 120, "Gemini"); assert a.ov.height() > h0 and abs(a.ov.geometry().bottom() - bottom) <= 1, (h0, a.ov.height())
a.ov.show_line("", "Hi.", "Xin chào.", ""); assert a.ov.height() == h0 and a.cfg["overlay_geom"][3] == h0
assert "[Ctrl+Alt+P]" in a.ov.btns["pause"].toolTip() and "[Ctrl+Alt+T]" in a.ov.btns["hide"].toolTip() and a.ov.btns["lock"].toolTip()
sd = SettingsDialog(a.cfg); cb = sd.w["display"][0]; cb.setCurrentIndex(cb.findData("vi")); sd.apply(); assert a.cfg["display"] == "vi"
a.ov.apply_style(); assert not a.ov.src_lbl.isVisibleTo(a.ov) and a.ov.vi.isVisibleTo(a.ov)
# chỉ câu gốc, rê chuột hiện bản dịch / chỉ bản dịch, rê chuột hiện câu gốc
a.cfg["display"] = "src_hover"; a.ov.apply_style(); assert a.ov.src_lbl.isVisibleTo(a.ov) and not a.ov.vi.isVisibleTo(a.ov)
a.ov._set_bar(True); assert a.ov.vi.isVisibleTo(a.ov); a.ov._set_bar(False); assert not a.ov.vi.isVisibleTo(a.ov)
a.cfg["display"] = "vi_hover"; a.ov.apply_style(); assert not a.ov.src_lbl.isVisibleTo(a.ov); a.ov._set_bar(True); assert a.ov.src_lbl.isVisibleTo(a.ov); a.ov._set_bar(False)
a.cfg["display"] = "both"; a.ov.apply_style(); assert a.ov.src_lbl.isVisibleTo(a.ov) and a.ov.vi.isVisibleTo(a.ov)
# cài đặt cũ show_source=False -> display "vi"
import json, tempfile as _t; _p = pathlib.Path(_t.mkdtemp()) / "s.json"; _p.write_text(json.dumps({"show_source": False}), "utf-8"); assert C.Config(_p)["display"] == "vi"

# 8) tự ẩn khi hết thoại, hiện lại khi có thoại mới; toggle tay không bị auto-show
a.cfg["auto_hide_s"] = 0.1; a.ov.show(); a.pop.hide(); a.on_text("", ""); pump(0.3)
assert not a.ov.isVisible() and a.auto_hidden
a.on_text("", "A completely new line appears."); assert a.ov.isVisible() and not a.auto_hidden
a.on_text("", "Some other line again."); a.on_action("toggle"); assert not a.ov.isVisible() and not a.auto_hidden
a.on_action("toggle"); a.cfg["auto_hide_s"] = 0

# 8b) hết thoại -> tự xóa chữ; bản dịch về muộn không hiện lại; ký tự rác coi như rỗng
a.on_text("", "Yet another fresh line."); pump(); assert a.ov.vi.text()
a.on_text("", " |- . "); assert a.ov.vi.text() == "" and a.ov.src == "" and a.cleared
a.render(a.history[a.pos]); assert a.ov.vi.text() == ""
a.on_text("", "Yet another fresh line."); pump(); assert a.ov.src == "Yet another fresh line." and not a.cleared
a.goto(a.pos - 1); assert a.ov.src and not a.cleared; a.goto(len(a.history) - 1)

# 8c) bôi đen câu gốc -> popup dịch đoạn bôi đen
a.ov.show_line("", "Rover's \"friend\" isn't here.", "", ""); a.ov.src_lbl.setSelection(0, 28); a.ov._selected(); pump()
assert a.pop.title.grab() and "&#" not in a.pop.title.text() and a.pop.title.textFormat() == Qt.RichText      # dấu nháy không thành &#x27;
a.pop.close_pop()
a.cfg["dict_mode"] = "auto"; a.pop.hide(); a.pop.pinned = False
a.ov.show_line("", "Rover, you finally woke up after all this time.", "", ""); a.ov.src_lbl.setSelection(7, 22)
a.ov._selected(); pump(); assert a.pop.word.startswith("you finally") and a.pop.pinned and a.pop.word + "-vi" in a.pop.raw, a.pop.word
a.pop.close_pop(); a.cfg["dict_mode"] = "llm"

# 9) click-through
from PySide6.QtCore import Qt
a.on_action("clickthrough"); assert a.cfg["click_through"] and a.ov.passthrough_wanted() and a.ov.isVisible() and a.ct_action.isChecked()
a.on_action("clickthrough"); assert not a.ov.passthrough_wanted() and not a.ct_action.isChecked()

# 10) xem vùng đang chọn: bật / bấm lại tắt / tự tắt
a.cfg["regions"] = []; a.cfg["speaker_region"] = None; a.on_action("show_region"); assert not a.flash
a.cfg["regions"] = [{"x": 10, "y": 40, "w": 300, "h": 60}]; a.cfg["speaker_region"] = {"x": 10, "y": 10, "w": 100, "h": 15}
a.on_action("show_region"); assert len(a.flash) == 2 and all(w.isVisible() for w in a.flash)
a.on_action("show_region"); assert not a.flash
a.on_action("show_region"); a.flash_t.start(50); pump(0.2); assert not a.flash
# khôi phục cài đặt gốc: giữ vùng thoại (tick mặc định), các thứ khác về mặc định, hộp thoại đóng với cờ reset
from PySide6.QtWidgets import QMessageBox as _MB
a.cfg["font_size"] = 33; reg = list(a.cfg["regions"]); sd = SettingsDialog(a.cfg)
_exec = _MB.exec; _MB.exec = lambda self: _MB.Yes
try: sd._reset()
finally: _MB.exec = _exec
assert sd.reset and a.cfg["font_size"] == 17 and a.cfg["regions"] == reg

# 11) nhiều vùng: vùng trên đang hiện -> câu vùng dưới chỉ vào lịch sử (chưa dịch); vùng trên hết chữ -> hiện + dịch câu vùng dưới
a.cfg["translate"] = True; a.cfg["regions"] = [{"x": 0, "y": 0, "w": 10, "h": 10, "name": "Thoại"}, {"x": 0, "y": 20, "w": 10, "h": 10, "name": "Dẫn"}]; a.reset_regions()
tcalls = []; a.tr.translate = lambda src, spk, ctx, partial, engine=None: (tcalls.append(src), ("VI " + src, "google"))[1]
a.on_text("", "Upper region speaks first.", 0); pump()
assert a.ov.src == "Upper region speaks first." and a.ov._tag.startswith("Thoại · "), a.ov._tag
a.on_text("", "Lower narration appears now.", 1); pump()
assert a.ov.src == "Upper region speaks first." and a.history[-2]["src"] == "Lower narration appears now." and a.history[-2].get("pending")
assert tcalls == ["Upper region speaks first."] and a.pos == len(a.history) - 1
a.on_text("", "", 0); pump()
assert a.ov.src == "Lower narration appears now." and a.ov.vi.text() == "VI Lower narration appears now." and a.history[-1]["reg"] == 1 and not a.cleared
a.on_text("", "Upper region again.", 0); pump(); assert a.ov.src == "Upper region again."
a.on_text("", "", 1); assert a.ov.src == "Upper region again." and not a.cleared       # vùng dưới hết chữ: không đụng vùng trên
a.on_text("", "", 0); assert a.cleared

# 12) chế độ sửa vùng: kéo chỗ trống = thêm, phím số = ưu tiên, nút ✕ = xóa, vùng tên, giới hạn số vùng, OCR thử
from PySide6.QtTest import QTest
from gamesub.ui_region import RegionEditor
ed = RegionEditor([C.region({"x": 10, "y": 40, "w": 300, "h": 60, "name": "Hộp thoại"})], None, max_regions=3)
pv = []; ed.preview.connect(lambda seq, img: pv.append((seq, img.shape))); ed.start(); pump(0.1)
assert pv == [(1, (60, 300, 3))], pv
ed.set_preview(1, "Hello there"); assert ed.items[0].preview == "Hello there"
def drag(w, p0, p1): QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, p0); QTest.mouseMove(w, p1); QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, p1)
drag(ed, QPoint(400, 300), QPoint(600, 350)); assert len(ed.items) == 2 and ed.sel is ed.items[1] and ed.items[1].rect == QRect(400, 300, 201, 51) and len(pv) == 2
ed.set_preview(1, "late"); assert ed.items[0].preview == "Hello there"            # kết quả cũ về muộn: bỏ qua
QTest.keyClick(ed, Qt.Key_1); assert ed.items[0].rect.x() == 400 and ed.items[1].meta["name"] == "Hộp thoại"
drag(ed, QPoint(410, 310), QPoint(430, 320)); assert ed.items[0].rect.topLeft() == QPoint(420, 310)    # kéo vùng = di chuyển
QTest.keyClick(ed, Qt.Key_Right, Qt.ShiftModifier); assert ed.items[0].rect.x() == 430
b = next(r for k, _, r in ed._label_box(ed.items[1])[1] if k == "yield"); QTest.mouseClick(ed, Qt.LeftButton, Qt.NoModifier, b.center()); assert ed.items[1].meta["yield"] is False
assert ed._tip(ed.items[1], "yield").startswith("▶ Đang LUÔN ĐỌC") and ed._tip(ed.items[0], "yield").startswith("⏸ Đang NHƯỜNG") and ed.msg.startswith("▶")
ed.grab()                                                                       # vẽ cả dòng chú thích icon không lỗi
assert dict((k, n) for k, n, _ in ed._label_box(ed.items[1])[1])["yield"] == "mdi6.play-circle-outline" and dict((k, n) for k, n, _ in ed._label_box(ed.items[0])[1])["yield"] == "mdi6.pause-circle-outline"
ed.btn_spk.setChecked(True); drag(ed, QPoint(10, 10), QPoint(110, 25)); assert ed.spk and ed.spk.rect.width() == 101 and not ed.draw_spk
drag(ed, QPoint(50, 200), QPoint(150, 250)); drag(ed, QPoint(50, 500), QPoint(150, 550)); assert len(ed.items) == 3 and ed.msg       # tối đa 3
b = next(r for k, _, r in ed._label_box(ed.items[2])[1] if k == "close"); QTest.mouseClick(ed, Qt.LeftButton, Qt.NoModifier, b.center()); assert len(ed.items) == 2
regs, spk = ed.result()
assert [r["x"] for r in regs] == [430, 10] and regs[1]["name"] == "Hộp thoại" and regs[1]["yield"] is False and spk == {"x": 10, "y": 10, "w": 101, "h": 16}, (regs, spk)
QTest.keyClick(ed, Qt.Key_Escape); assert not ed.isVisible()
# qua app: Ctrl+Alt+R mở chế độ sửa, OCR thử chạy nền, Lưu -> cfg + worker chạy lại
a._preview_ocr = lambda img: f"ocr {img.shape[1]}"
a.on_action("region"); pump(0.5); ed = a.sel
assert isinstance(ed, RegionEditor) and a.worker.paused and not a.ov.isVisible() and ed.items[0].preview == "ocr 10", ed.items[0].preview
ed.remove(ed.items[1]); ed.add(QRect(100, 100, 50, 20)); QTest.keyClick(ed, Qt.Key_Return)
assert [r["w"] for r in a.cfg["regions"]] == [10, 50] and not a.worker.paused and a.ov.isVisible()
a.on_action("region"); pump(0.3); a.sel.btn_spk.setChecked(True); QTest.keyClick(a.sel, Qt.Key_Escape); assert a.sel.isVisible() and not a.sel.draw_spk; QTest.keyClick(a.sel, Qt.Key_Escape)
assert not a.sel.isVisible() and [r["w"] for r in a.cfg["regions"]] == [10, 50] and not a.worker.paused

# 13) gợi ý vùng: khối chữ nằm gọn trong vùng có sẵn bị bỏ; bấm khối gợi ý = thêm vùng; kéo vùng gần mép khối chữ thì bám vào
ed = RegionEditor([C.region({"x": 100, "y": 100, "w": 300, "h": 80})], None); asked = []; ed.suggest_req.connect(lambda img: asked.append(img.shape)); ed.start()
ed.ask_suggest(); assert ed.busy and asked and asked[0][2] == 3 and not ed.btn_suggest.isEnabled()
ed.set_suggestions([(110, 110, 200, 30, "inside existing"), (400, 400, 300, 40, "Narration text here")])          # màn offscreen 800px
assert len(ed.sugg) == 1 and ed.sugg[0][0] == QRect(390, 390, 320, 60) and not ed.busy, ed.sugg
QTest.mouseClick(ed, Qt.LeftButton, Qt.NoModifier, QPoint(500, 410)); assert len(ed.items) == 2 and ed.items[1].rect == QRect(390, 390, 320, 60) and not ed.sugg
ed.remove(ed.items[1]); ed.set_suggestions([(500, 300, 100, 20, "snap me")]); assert ed.sugg[0][0].left() == 495
drag(ed, QPoint(200, 140), QPoint(200 + 391, 140)); assert ed.items[0].rect.left() == 495, ed.items[0].rect      # lệch 4px -> bám mép khối chữ
QTest.keyClick(ed, Qt.Key_Escape); assert not ed.sugg and ed.isVisible(); QTest.keyClick(ed, Qt.Key_Escape); assert not ed.isVisible()
a._suggest_ocr = lambda img: [(10, 10, 100, 20, "auto suggested")]
a.cfg["regions"] = []; a.on_action("region"); pump(0.5); assert a.sel.sugg and a.sel.sugg[0][1] == "auto suggested"       # chưa có vùng: tự gợi ý
QTest.keyClick(a.sel, Qt.Key_Escape); QTest.keyClick(a.sel, Qt.Key_Escape)

# 14) Cài đặt -> OCR -> bảng vùng: đổi tên, tắt, xếp lại, xóa vùng tên; Hủy không đổi gì
a.cfg["regions"] = [C.region({"x": 1, "y": 2, "w": 30, "h": 40, "name": "A"}), C.region({"x": 5, "y": 6, "w": 70, "h": 80})]; a.cfg["speaker_region"] = {"x": 0, "y": 0, "w": 9, "h": 9}
sd = SettingsDialog(a.cfg); t = sd.reg_tbl
assert t.rowCount() == 2 and t.item(0, 0).text() == "A" and t.item(1, 3).text() == "5,6  70×80" and sd.spk_del.isEnabled()
t.item(1, 0).setText("Lời dẫn"); t.item(1, 2).setCheckState(Qt.Unchecked); t.setCurrentCell(1, 0); sd._reg_move(-1)
assert t.item(0, 0).text() == "Lời dẫn" and t.currentRow() == 0
t.item(1, 1).setCheckState(Qt.Unchecked); sd.spk_del.click(); assert sd.spk_lbl.text() and not sd.spk_del.isEnabled()
sd.apply(); r = a.cfg["regions"]
assert [x["name"] for x in r] == ["Lời dẫn", "A"] and r[0]["yield"] is False and r[1]["on"] is False and a.cfg["speaker_region"] is None, r
sd = SettingsDialog(a.cfg); sd.reg_tbl.setCurrentCell(0, 0); sd._reg_del(); assert sd.reg_tbl.rowCount() == 1; sd.reject(); assert len(a.cfg["regions"]) == 2
sd = SettingsDialog(a.cfg); sd._reg_edit(); assert sd.edit_regions and sd.result() == 1
a.quit(); print("UI SMOKE OK")
