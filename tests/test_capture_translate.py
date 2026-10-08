import os, sys, time, json, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32": os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))   # offscreen không có font hệ thống
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from PySide6.QtCore import QCoreApplication
import gamesub.capture as cap
from gamesub.config import Config
from gamesub.db import DB
from gamesub.translator import Translator

def test_capture_waits_for_stable_text():
    q = QCoreApplication.instance() or QCoreApplication(sys.argv)
    frames = {"i": 0}
    def fake_grab(sct, r):                       # 0-5: chữ đang chạy (đổi liên tục), sau đó đứng yên
        frames["i"] += 1; img = np.zeros((40, 200, 3), np.uint8); img[:, : min(200, frames["i"] * 30)] = 255; return img
    class Eng:
        name = "fake"; calls = 0
        def recognize(self, img): Eng.calls += 1; return ["Hello", f"width {int((img.mean(axis=2) > 0).sum(axis=1)[0])}"]
    cap.grab = fake_grab; cap.ocr.create = lambda n, l: Eng()
    class FakeMss:
        def close(self): pass
    cap.open_sct = lambda: FakeMss()
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); cfg.update(region={"x": 0, "y": 0, "w": 200, "h": 40}, interval_ms=20, stable_ms=150)
    w = cap.CaptureWorker(cfg); got = []; w.text_ready.connect(lambda s, t: got.append(t)); w.start()
    end = time.time() + 1.2
    while time.time() < end: q.processEvents(); time.sleep(0.01)
    w.stop(); q.processEvents()
    assert got == ["Hello width 200"], got        # chỉ OCR 1 lần khi khung đã đủ & ổn định
    assert Eng.calls == 1

def test_capture_waits_for_target_app():
    """App khác đang focus -> không OCR; về game -> OCR."""
    q = QCoreApplication.instance() or QCoreApplication(sys.argv)
    fg = {"exe": "chrome.exe"}
    cap.winapp.is_target = lambda t: not t or fg["exe"] == t
    A = np.zeros((40, 200, 3), np.uint8); A[:, :100] = 255
    cap.grab = lambda sct, r: A
    class Eng:
        name = "fake"; calls = 0
        def recognize(self, img): Eng.calls += 1; return ["hi"]
    cap.ocr.create = lambda n, l: Eng()
    class FakeMss:
        def close(self): pass
    cap.open_sct = lambda: FakeMss()
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); cfg.update(region={"x": 0, "y": 0, "w": 200, "h": 40}, interval_ms=20, stable_ms=50, target_app="game.exe")
    w = cap.CaptureWorker(cfg); st = []; w.status.connect(st.append); w.start()
    def run(sec):
        end = time.time() + sec
        while time.time() < end: q.processEvents(); time.sleep(0.01)
    run(0.5); assert Eng.calls == 0 and "Chờ game.exe…" in st
    fg["exe"] = "game.exe"; run(0.5); w.stop(); assert Eng.calls == 1, Eng.calls

def test_capture_skips_same_frame():
    """Nền nhấp nháy rồi trở lại y như cũ -> không OCR lại; đổi sang khung mới thật -> OCR."""
    q = QCoreApplication.instance() or QCoreApplication(sys.argv)
    seq = {"i": 0}
    A = np.zeros((40, 200, 3), np.uint8); A[:, :100] = 255
    B = np.zeros((40, 200, 3), np.uint8); B[:, 100:] = 255
    C = np.zeros((40, 200, 3), np.uint8); C[10:30] = 200
    def fake_grab(sct, r):                       # A ổn định -> B thoáng qua -> A ổn định lại -> C
        seq["i"] += 1; i = seq["i"]
        return A if i < 15 else B if i < 17 else A if i < 32 else C
    class Eng:
        name = "fake"; calls = 0
        def recognize(self, img): Eng.calls += 1; return [f"frame {Eng.calls}"]
    cap.grab = fake_grab; cap.ocr.create = lambda n, l: Eng()
    class FakeMss:
        def close(self): pass
    cap.open_sct = lambda: FakeMss()
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); cfg.update(region={"x": 0, "y": 0, "w": 200, "h": 40}, interval_ms=20, stable_ms=100)
    w = cap.CaptureWorker(cfg); w.start()
    end = time.time() + 1.6
    while time.time() < end: q.processEvents(); time.sleep(0.01)
    w.stop()
    assert Eng.calls == 2, Eng.calls             # A và C; lần A quay lại bị bỏ qua

def test_capture_rereads_slow_typing_tail():
    """Chữ chạy chậm: OCR lúc câu còn dở, phần cuối hiện sau chỉ lệch ít (trung bình < ngưỡng) -> vẫn phải OCR lại câu đủ."""
    q = QCoreApplication.instance() or QCoreApplication(sys.argv)
    seq = {"i": 0}
    def frame(n):                                # nền tối, n "ký tự" sáng 4x10px trên 1 dòng (vùng 940x100 như thoại thật)
        img = np.full((100, 940, 3), 40, np.uint8)
        for k in range(n): img[40:50, 20 + k * 10: 24 + k * 10] = 230
        return img
    def fake_grab(sct, r):                       # 60 ký tự hiện ngay, đứng yên 10 khung (đủ stable), rồi 20 ký tự cuối
        seq["i"] += 1; i = seq["i"]
        return frame(60 if i < 12 else 80)
    class Eng:
        name = "fake"; calls = 0
        def recognize(self, img): Eng.calls += 1; return [f"chars {int((img[45, :, 0] > 100).sum() // 4)}"]
    cap.grab = fake_grab; cap.ocr.create = lambda n, l: Eng()
    class FakeMss:
        def close(self): pass
    cap.open_sct = lambda: FakeMss()
    assert float(np.abs(cap.signature(frame(60)) - cap.signature(frame(80))).mean()) < 3.0     # đúng ca cũ bỏ sót
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); cfg.update(region={"x": 0, "y": 0, "w": 940, "h": 100}, interval_ms=20, stable_ms=100)
    w = cap.CaptureWorker(cfg); got = []; w.text_ready.connect(lambda s, t: got.append(t)); w.start()
    end = time.time() + 1.0
    while time.time() < end: q.processEvents(); time.sleep(0.01)
    w.stop(); q.processEvents()
    assert got == ["chars 60", "chars 80"], got

def test_capture_detects_short_line_swap():
    """Câu ngắn A -> trống thoáng qua -> câu ngắn B cùng độ dài: lệch trung bình < ngưỡng nhưng vẫn phải OCR B (không để A đứng mãi)."""
    q = QCoreApplication.instance() or QCoreApplication(sys.argv)
    seq = {"i": 0}
    def frame(off):                              # 20 "ký tự" 4x10px, B lệch nửa ô chữ so với A
        img = np.full((100, 940, 3), 40, np.uint8)
        for k in range(20): img[40:50, 20 + off + k * 10: 24 + off + k * 10] = 230
        return img
    A, B, blank = frame(0), frame(5), np.full((100, 940, 3), 40, np.uint8)
    def fake_grab(sct, r):
        seq["i"] += 1; i = seq["i"]
        return A if i < 15 else blank if i < 17 else B
    class Eng:
        name = "fake"; calls = 0
        def recognize(self, img): Eng.calls += 1; return [f"line {Eng.calls}"]
    cap.grab = fake_grab; cap.ocr.create = lambda n, l: Eng()
    class FakeMss:
        def close(self): pass
    cap.open_sct = lambda: FakeMss()
    assert float(np.abs(cap.signature(A) - cap.signature(B)).mean()) < 3.0      # đúng ca cũ bỏ sót
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); cfg.update(region={"x": 0, "y": 0, "w": 940, "h": 100}, interval_ms=20, stable_ms=100)
    w = cap.CaptureWorker(cfg); w.start()
    end = time.time() + 1.2
    while time.time() < end: q.processEvents(); time.sleep(0.01)
    w.stop()
    assert Eng.calls == 2, Eng.calls             # A rồi B

class FakeResp:
    def __init__(self, lines, status=200, js=None): self.lines, self.status_code, self._js, self.text = lines, status, js, ""
    def iter_lines(self, decode_unicode=True): return iter(self.lines)
    def json(self): return self._js

def test_streaming_parsers():
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); db = DB(Path(tempfile.mkdtemp()) / "t.db"); tr = Translator(cfg, db)
    cfg.update(gemini_key="k", dialog_engine="gemini")
    sse = [f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': t}]}}]})}" for t in ("Xin ", "chào.")]
    sent = {}
    def post(url, **kw): sent["url"], sent["json"] = url, kw["json"]; return FakeResp(sse)
    tr.s.post = post; parts = []
    out = tr.translate("Hello.", "Yangyang", [], parts.append)
    assert out[:2] == ("Xin chào.", "gemini") and parts == ["Xin ", "Xin chào."] and "streamGenerateContent" in sent["url"]
    assert sent["json"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0} and "Yangyang: Hello." in sent["json"]["contents"][0]["parts"][0]["text"]
    # 429 -> cooldown; chỉ Gemini thì báo lỗi
    tr.s.post = lambda url, **kw: FakeResp([], 429)
    try: tr.translate("x", "", [], None); assert False
    except Exception as e: assert "429" in str(e) and tr.cool["gemini"] > time.time()
    # Gemini lỗi/cooldown -> Google; engine riêng cho vùng chụp; chọn Google thì không gọi Gemini
    tr.google = lambda text: "Bản Google"; tr.db.cache_get = lambda k: None      # tắt cache để thử từng engine
    r = tr.translate("x", "", [], None, engine="ocr_gemini"); assert r[:2] == ("Bản Google", "google") and "Gemini lỗi" in r[2], r
    cfg["dialog_engine"] = "gemini_google"; assert tr.translate("x")[1] == "google"
    tr.cool.clear(); calls = []; tr.gemini = lambda *a, **k: calls.append(1) or "AI"
    cfg["dialog_engine"] = "google"; assert tr.translate("x") == ("Bản Google", "google", "") and not calls
    assert tr.translate("x", engine="ocr_gemini") == ("AI", "gemini", "")

def test_google_fallback_and_cache():
    import gamesub.translator as T
    calls = []
    class S:
        def get(self, url, params=None, timeout=None):
            calls.append(url)
            if "translate.googleapis" in url: return FakeResp([], 429)
            return FakeResp([], 200, [["Xin chào", "en"]])
    assert T.google_free(S(), "Hello", "vi", 5, {}) == "Xin chào" and len(calls) == 2      # 429 -> endpoint dự phòng
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); db = DB(Path(tempfile.mkdtemp()) / "t.db"); tr = Translator(cfg, db)
    n = []; tr.google = lambda text: n.append(1) or "Bản dịch"
    assert tr.translate("Same line.") == ("Bản dịch", "google", "") and tr.translate("Same line.") == ("Bản dịch", "google", "") and len(n) == 1

if __name__ == "__main__":
    test_capture_waits_for_stable_text(); print("PASS capture"); test_capture_skips_same_frame(); print("PASS skip same frame"); test_capture_rereads_slow_typing_tail(); print("PASS typing tail"); test_capture_detects_short_line_swap(); print("PASS short line swap"); test_capture_waits_for_target_app(); print("PASS target app"); test_google_fallback_and_cache(); print("PASS google fallback + cache"); test_streaming_parsers(); print("PASS translate")
