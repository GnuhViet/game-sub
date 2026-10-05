import os, sys, time, json, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from PySide6.QtCore import QCoreApplication
import wuwasub.capture as cap
from wuwasub.config import Config
from wuwasub.db import DB
from wuwasub.translator import Translator

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

class FakeResp:
    def __init__(self, lines, status=200, js=None): self.lines, self.status_code, self._js, self.text = lines, status, js, ""
    def iter_lines(self, decode_unicode=True): return iter(self.lines)
    def json(self): return self._js

def test_streaming_parsers():
    cfg = Config(Path(tempfile.mkdtemp()) / "s.json"); db = DB(Path(tempfile.mkdtemp()) / "t.db"); tr = Translator(cfg, db)
    cfg.update(gemini_key="k", openai_key="k", chain=["gemini"])
    sse = [f"data: {json.dumps({'candidates': [{'content': {'parts': [{'text': t}]}}]})}" for t in ("Xin ", "chào.")]
    sent = {}
    def post(url, **kw): sent["url"], sent["json"] = url, kw["json"]; return FakeResp(sse)
    tr.s.post = post; parts = []
    out = tr.translate("Hello.", "Yangyang", [], parts.append)
    assert out == ("Xin chào.", "gemini") and parts == ["Xin ", "Xin chào."] and "streamGenerateContent" in sent["url"]
    assert sent["json"]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0} and "Yangyang: Hello." in sent["json"]["contents"][0]["parts"][0]["text"]
    oai = [f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}" for t in ("Tạm ", "biệt")] + ["data: [DONE]"]
    tr.s.post = lambda url, **kw: FakeResp(oai); cfg["chain"] = ["openai"]
    assert tr.translate("Bye", "", [], lambda _: None) == ("Tạm biệt", "openai")
    # 429 -> cooldown -> fallback
    tr.s.post = lambda url, **kw: FakeResp([], 429); cfg["chain"] = ["gemini", "openai"]
    try: tr.translate("x", "", [], None); assert False
    except Exception as e: assert "429" in str(e) and tr.cool["gemini"] > time.time()

if __name__ == "__main__":
    test_capture_waits_for_stable_text(); print("PASS capture"); test_streaming_parsers(); print("PASS translate")
