"""Thread chụp vùng màn hình -> phát hiện thay đổi -> chờ ổn định (hiệu ứng chữ chạy) -> OCR."""
import time, traceback
import numpy as np
from PySide6.QtCore import QThread, Signal
from . import ocr, winapp
from .textnorm import join_lines
from .i18n import tr

def open_sct():
    import mss
    return mss.MSS() if hasattr(mss, "MSS") else mss.mss()          # mss>=10 đổi tên mss() -> MSS()

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
            self.error.emit(tr("Không khởi tạo được OCR '{eng}': {e}", eng=self.cfg["ocr_engine"], e=ex)); return None

    def _ocr(self, eng, img):
        s = float(self.cfg["ocr_scale"] or 1)
        if abs(s - 1) > 0.01: img = ocr._resize(img, s)
        return join_lines(eng.recognize(img))

    def run(self):
        sct = open_sct(); eng = self._engine(); prev = last_ocr = None; pending = False; last_change = 0; waiting = False
        while self.running:
            t0 = time.time()
            try:
                if self.reload_engine: self.reload_engine = False; eng = self._engine()
                r = self.cfg["region"]
                if self.snapshot_req and r:
                    from PIL import Image
                    Image.fromarray(grab(sct, r)).save(self.snapshot_req); self.status.emit(tr("Đã lưu ảnh vùng: {path}", path=self.snapshot_req)); self.snapshot_req = None
                if self.paused or not r or eng is None:
                    time.sleep(0.2); continue
                if not winapp.is_target(self.cfg["target_app"]):          # đang ở app khác -> không chụp
                    if not waiting: waiting = True; self.status.emit(tr("Chờ {app}…", app=self.cfg["target_app"]))
                    time.sleep(0.3); continue
                if waiting: waiting = False; self.status.emit("")
                img = grab(sct, r); sig = signature(img)
                if prev is None or prev.shape != sig.shape or float(np.abs(sig - prev).mean()) > self.cfg["diff_threshold"]:
                    prev = sig; pending = True; last_change = time.time()
                if self.force or (pending and (time.time() - last_change) * 1000 >= self.cfg["stable_ms"]):
                    pending = False
                    same = last_ocr is not None and last_ocr.shape == sig.shape and float(np.abs(sig - last_ocr).mean()) <= self.cfg["diff_threshold"]
                    if not same or self.force:                     # ảnh y như lần OCR trước (nền nhấp nháy rồi về cũ) -> khỏi OCR lại
                        self.force = False; last_ocr = sig
                        text = self._ocr(eng, img)
                        spk = self._ocr(eng, grab(sct, self.cfg["speaker_region"])) if text and self.cfg["speaker_region"] else ""
                        self.text_ready.emit(spk, text)
            except Exception as ex:
                self.error.emit(tr("Lỗi capture/OCR: {e}", e=ex)); traceback.print_exc(); time.sleep(1)
            time.sleep(max(0.02, self.cfg["interval_ms"] / 1000 - (time.time() - t0)))
        sct.close()
