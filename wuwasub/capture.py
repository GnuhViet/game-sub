"""Thread chụp vùng màn hình -> phát hiện thay đổi -> chờ ổn định (hiệu ứng chữ chạy) -> OCR."""
import time, traceback
import numpy as np
from PySide6.QtCore import QThread, Signal
from . import ocr
from .textnorm import join_lines

def grab(sct, r):
    shot = sct.grab({"left": int(r["x"]), "top": int(r["y"]), "width": max(1, int(r["w"])), "height": max(1, int(r["h"]))})
    return np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)[:, :, 2::-1]   # -> RGB

def signature(img):
    g = img.mean(axis=2); step = max(1, img.shape[1] // 96)
    return g[::step, ::step].astype(np.float32)

class CaptureWorker(QThread):
    text_ready = Signal(str, str)        # speaker, text
    status = Signal(str)
    error = Signal(str)

    def __init__(self, cfg):
        super().__init__(); self.cfg = cfg; self.running = True; self.paused = False
        self.force = False; self.reload_engine = False; self.snapshot_req = None

    def stop(self): self.running = False; self.wait(3000)

    def _engine(self):
        try:
            e = ocr.create(self.cfg["ocr_engine"], self.cfg["ocr_lang"]); self.status.emit(f"OCR: {e.name}"); return e
        except Exception as ex:
            self.error.emit(f"Không khởi tạo được OCR '{self.cfg['ocr_engine']}': {ex}"); return None

    def _ocr(self, eng, img):
        s = float(self.cfg["ocr_scale"] or 1)
        if abs(s - 1) > 0.01: img = ocr._resize(img, s)
        return join_lines(eng.recognize(img))

    def run(self):
        import mss
        sct = mss.mss(); eng = self._engine(); prev = None; pending = False; last_change = 0
        while self.running:
            t0 = time.time()
            try:
                if self.reload_engine: self.reload_engine = False; eng = self._engine()
                r = self.cfg["region"]
                if self.snapshot_req and r:
                    from PIL import Image
                    Image.fromarray(grab(sct, r)).save(self.snapshot_req); self.status.emit(f"Đã lưu ảnh vùng: {self.snapshot_req}"); self.snapshot_req = None
                if self.paused or not r or eng is None:
                    time.sleep(0.2); continue
                img = grab(sct, r); sig = signature(img)
                if prev is None or prev.shape != sig.shape or float(np.abs(sig - prev).mean()) > self.cfg["diff_threshold"]:
                    prev = sig; pending = True; last_change = time.time()
                if self.force or (pending and (time.time() - last_change) * 1000 >= self.cfg["stable_ms"]):
                    pending = False; self.force = False
                    text = self._ocr(eng, img)
                    spk = self._ocr(eng, grab(sct, self.cfg["speaker_region"])) if text and self.cfg["speaker_region"] else ""
                    self.text_ready.emit(spk, text)
            except Exception as ex:
                self.error.emit(f"Lỗi capture/OCR: {ex}"); traceback.print_exc(); time.sleep(1)
            time.sleep(max(0.02, self.cfg["interval_ms"] / 1000 - (time.time() - t0)))
        sct.close()
