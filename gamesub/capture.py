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
    """Độ sáng trung bình theo ô ~1/96 bề ngang. Lấy trung bình cả ô (không lấy mẫu điểm) để nét chữ mảnh vẫn được tính."""
    g = img.mean(axis=2, dtype=np.float32); b = max(1, img.shape[1] // 96)
    h, w = (g.shape[0] // b) * b or g.shape[0], (g.shape[1] // b) * b or g.shape[1]
    if b > 1 and g.shape[0] >= b: g = g[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))
    return g

def changed(a, b, thr):
    """Cả vùng lệch trung bình > thr (đổi cảnh/đổi câu) HOẶC ≥2 ô lệch mạnh (vài ký tự mới hiện: chữ chạy, đoạn cuối câu, câu ngắn).
    Chỉ so trung bình thì ~20 ký tự cuối câu chỉ lệch ~1 -> không thấy -> OCR câu dở rồi kẹt đến khi bấm Quét lại."""
    if a is None or b is None or a.shape != b.shape: return True
    d = np.abs(a - b)
    return float(d.mean()) > thr or int((d > max(8.0, thr * 4)).sum()) >= 2

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
            self.error.emit(tr("ocr.couldnt_start_ocr_eng_e", eng=self.cfg["ocr_engine"], e=ex)); return None

    def _ocr(self, eng, img):
        s = float(self.cfg["ocr_scale"] or 1)
        if abs(s - 1) > 0.01: img = ocr._resize(img, s)
        return join_lines(eng.recognize(img))

    def run(self):
        sct = open_sct(); eng = self._engine(); prev = last_ocr = None; last_move = dirty_since = 0; waiting = False
        while self.running:
            t0 = time.time()
            try:
                if self.reload_engine: self.reload_engine = False; eng = self._engine()
                r = self.cfg["region"]
                if self.snapshot_req and r:
                    from PIL import Image
                    Image.fromarray(grab(sct, r)).save(self.snapshot_req); self.status.emit(tr("ocr.saved_region_image_path", path=self.snapshot_req)); self.snapshot_req = None
                if self.paused or not r or eng is None:
                    time.sleep(0.2); continue
                if not winapp.is_target(self.cfg["target_app"]):          # đang ở app khác -> không chụp
                    if not waiting: waiting = True; self.status.emit(tr("ocr.waiting_for_app", app=self.cfg["target_app"]))
                    time.sleep(0.3); continue
                if waiting: waiting = False; self.status.emit("")
                img = grab(sct, r); sig = signature(img); now = time.time(); thr = self.cfg["diff_threshold"]
                if changed(sig, prev, thr): last_move = now                # so với khung ngay trước: còn đang chạy chữ?
                prev = sig
                # so với khung đã OCR: nền nhấp nháy rồi về y cũ -> khỏi OCR lại; chữ đổi dù ít -> OCR lại
                dirty = changed(sig, last_ocr, thr)
                if not dirty: dirty_since = 0
                elif not dirty_since: dirty_since = now
                stable = (now - last_move) * 1000 >= self.cfg["stable_ms"]
                stuck = dirty_since and (now - dirty_since) * 1000 >= max(2000, 3 * self.cfg["stable_ms"])   # nền động không bao giờ đứng yên
                if self.force or (dirty and (stable or stuck)):
                    self.force = False; last_ocr = sig; dirty_since = 0
                    text = self._ocr(eng, img)
                    spk = self._ocr(eng, grab(sct, self.cfg["speaker_region"])) if text and self.cfg["speaker_region"] else ""
                    self.text_ready.emit(spk, text)
            except Exception as ex:
                self.error.emit(tr("ocr.capture_ocr_error_e", e=ex)); traceback.print_exc(); time.sleep(1)
            time.sleep(max(0.02, self.cfg["interval_ms"] / 1000 - (time.time() - t0)))
        sct.close()
