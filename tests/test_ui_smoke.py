"""Smoke test UI offscreen: QT_QPA_PLATFORM=offscreen python tests/test_ui_smoke.py"""
import os, sys, tempfile, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import wuwasub.config as C
C.DATA_DIR = Path(tempfile.mkdtemp()); C.CFG_PATH = C.DATA_DIR / "settings.json"
import wuwasub.app as A
A.DATA_DIR = C.DATA_DIR
from PySide6.QtCore import QPoint, QRect, QThreadPool
from PySide6.QtWidgets import QApplication
from wuwasub.ui_dialogs import SettingsDialog, GlossaryDialog, VocabDialog, SubsDialog, ReviewDialog
from wuwasub.ui_region import RegionSelector, to_physical

class FakeWorker(A.CaptureWorker):
    def run(self):
        while self.running: time.sleep(0.05)
A.CaptureWorker = FakeWorker

q = QApplication(sys.argv)
def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end: q.processEvents(); time.sleep(0.01)
    QThreadPool.globalInstance().waitForDone(2000); q.processEvents()

a = A.App(q)
(C.DATA_DIR / "d.tsv").write_text("finally\tcuối cùng\nwake\tthức dậy\n", "utf-8")
a.cfg["dict_files"] = [str(C.DATA_DIR / "d.tsv")]; a.dicts.load(a.cfg["dict_files"])
a.db.add_subs("vh.csv", [("Rover, you finally woke up.", "Rover, cuối cùng anh cũng tỉnh rồi.")]); a.rebuild_index()

# 1) sub match
a.on_text("Yangyang", "Rover, you finaIly woke up."); pump()
assert a.ov.vi.text() == "Rover, cuối cùng anh cũng tỉnh rồi." and a.ov.tag.text().startswith("Bộ sub"), (a.ov.vi.text(), a.ov.tag.text())
assert a.ov.speaker.text() == "Yangyang" and 'href="w:' in a.ov.src_lbl.text()
# dedupe
n = len(a.history); a.on_text("", "Rover, you finally woke up"); assert len(a.history) == n

# 2) machine translation fallback (mock) + streaming partial
calls = []
def fake_tr(src, spk, ctx, partial):
    calls.append(ctx); partial("Đang…"); return "Câu dịch máy.", "gemini"
a.tr.translate = fake_tr; a.cfg["chain"] = ["gemini"]
a.on_text("", "Something brand new happens here."); pump()
assert a.ov.vi.text() == "Câu dịch máy." and a.ov.tag.text() == "Gemini · gemini-2.5-flash-lite", a.ov.tag.text()
assert calls[0] and calls[0][-1][2] == "Rover, cuối cùng anh cũng tỉnh rồi."    # context truyền vào
# lỗi dịch
def bad(*_): raise RuntimeError("429 hết quota")
a.tr.translate = bad; a.on_text("", "Another line that fails."); pump()
assert "Lỗi dịch" in a.ov.tag.text()

# 3) history nav
a.on_action("prev"); assert "[2/3]" in a.ov.tag.text(); a.on_action("next"); assert "[" not in a.ov.tag.text()

# 4) hover lookup offline
a.on_action("prev"); a.on_action("prev")
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

# 6) dialogs khởi tạo được
for d in (SettingsDialog(a.cfg), GlossaryDialog(a.db, a.cfg), VocabDialog(a.db), SubsDialog(a.db, a.index, a.cfg, a.rebuild_index)):
    d.show(); pump(0.05); d.close()
seen = []; sd = SettingsDialog(a.cfg, on_preview=lambda: seen.append(1)); sd.show(); pump(0.05)
sl = sd.w["opacity"][0]; sl.setValue(40); assert seen and a.cfg["opacity"] == 0.6     # xem trước trực tiếp
sd.w["show_frame"][0].setChecked(False); sd.w["text_outline"][0].setChecked(True); assert not a.cfg["show_frame"] and a.cfg["text_outline"]
sd.reject(); assert a.cfg["opacity"] == 0.82 and a.cfg["show_frame"] and not a.cfg["text_outline"]     # Cancel trả lại
sd = SettingsDialog(a.cfg); sd.w["text_outline"][0].setChecked(True); sd.apply(); a.ov.apply_style()
assert isinstance(a.ov.vi.graphicsEffect(), __import__("wuwasub.ui_overlay", fromlist=["x"]).OutlineEffect); a.ov.grab()
a.cfg["show_frame"] = False; a.ov.update(); a.ov.grab(); a.cfg["show_frame"] = True; a.cfg["text_outline"] = False; a.ov.apply_style()
a.render(); a.on_action("clear"); assert a.ov.vi.text() == "" and a.ov.src == ""
# tắt dịch: chỉ câu gốc, không gọi máy dịch; bật lại thì dịch câu hiện tại
n_calls = len(calls); a.on_action("translate"); a.on_text("", "Brand new untranslated line here.")
assert a.ov.vi.text() == "" and a.ov.src == "Brand new untranslated line here." and a.ov.src_lbl.isVisibleTo(a.ov) and "Không dịch" in a.ov.tag.text()
a.tr.translate = fake_tr; a.on_action("translate"); pump(); assert a.ov.vi.text() == "Câu dịch máy." and len(calls) == n_calls + 1
sd = SettingsDialog(a.cfg);sd.chain.setText("google, bogus, gemini"); sd.apply(); assert a.cfg["chain"] == ["google", "gemini"]
assert (C.DATA_DIR / "settings.json").exists()
sub = SubsDialog(a.db, a.index, a.cfg, a.rebuild_index); sub.test.setText("Rover you finally woke up"); sub._test(); assert "100" in sub.test_out.text() or "%" in sub.test_out.text()
gd = GlossaryDialog(a.db, a.cfg); gd._row("Resonator", "Cộng Minh Giả", "translate"); gd._save(); assert any(g["term"] == "Resonator" for g in a.db.glossary())
ReviewDialog(a.db, a.db.vocab()).show(); pump(0.05)

# 7) region selector + quy đổi DPI
rs = RegionSelector(); rs.show(); pump(0.05); rs.close()
class S:
    def geometry(self): return QRect(1920, 0, 1280, 720)
    def devicePixelRatio(self): return 1.5
assert to_physical(S(), QRect(100, 200, 300, 40)) == {"x": 2070, "y": 300, "w": 450, "h": 60}

a.on_action("pause"); assert a.worker.paused; a.on_action("pause")

# 8) tự ẩn khi hết thoại, hiện lại khi có thoại mới; toggle tay không bị auto-show
a.cfg["auto_hide_s"] = 0.1; a.ov.show(); a.pop.hide(); a.on_text("", ""); pump(0.3)
assert not a.ov.isVisible() and a.auto_hidden
a.on_text("", "A completely new line appears."); assert a.ov.isVisible() and not a.auto_hidden
a.on_text("", "Some other line again."); a.on_action("toggle"); assert not a.ov.isVisible() and not a.auto_hidden
a.on_action("toggle"); a.cfg["auto_hide_s"] = 0

# 9) click-through
from PySide6.QtCore import Qt
a.on_action("clickthrough"); assert a.cfg["click_through"] and a.ov.windowFlags() & Qt.WindowTransparentForInput and a.ov.isVisible() and a.ct_action.isChecked()
a.on_action("clickthrough"); assert not a.ov.windowFlags() & Qt.WindowTransparentForInput and not a.ct_action.isChecked()
a.quit(); print("UI SMOKE OK")
