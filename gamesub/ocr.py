"""OCR engines. Mỗi engine: recognize(np.ndarray RGB uint8) -> list[str] (các dòng, từ trên xuống)."""
import asyncio
import numpy as np
from .i18n import tr

class WindowsOcr:
    name = "windows"
    def __init__(self, lang="en-US"):
        try:
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.globalization import Language
            from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
            from winrt.windows.storage.streams import DataWriter
        except ImportError:
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.globalization import Language
            from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
            from winsdk.windows.storage.streams import DataWriter
        self.SB, self.PF, self.DW = SoftwareBitmap, BitmapPixelFormat, DataWriter
        self.engine = None
        if lang and OcrEngine.is_language_supported(Language(lang)):
            self.engine = OcrEngine.try_create_from_language(Language(lang))
        if self.engine is None: self.engine = OcrEngine.try_create_from_user_profile_languages()
        if self.engine is None: raise RuntimeError(tr("ocr.windows_ocr_has_no_lang", lang=lang))
        try: self.max_dim = int(OcrEngine.max_image_dimension)
        except Exception: self.max_dim = 10000
        self.loop = asyncio.new_event_loop()

    def recognize(self, img):
        h, w = img.shape[:2]
        if max(h, w) > self.max_dim:
            s = self.max_dim / max(h, w); img = _resize(img, s); h, w = img.shape[:2]
        rgba = np.dstack([img, np.full((h, w), 255, np.uint8)]).tobytes()
        dw = self.DW(); dw.write_bytes(rgba)
        bmp = self.SB.create_copy_from_buffer(dw.detach_buffer(), self.PF.RGBA8, w, h)   # bản có alpha tên là create_copy_with_alpha_from_buffer
        res = self.loop.run_until_complete(self._rec(bmp))
        return [l.text for l in res.lines]

    async def _rec(self, bmp): return await self.engine.recognize_async(bmp)

class RapidOcr:
    name = "rapidocr"
    def __init__(self, lang=None):
        from .engines import has_rapidocr
        try:
            from rapidocr_onnxruntime import RapidOCR; self.new = False
            # mặc định det phóng cạnh NGẮN lên ≥736px (vùng thoại 941x104 -> ~6600x736) và dùng mọi luồng: ~5.4s CPU/lần.
            # Không phóng, bỏ cls (chữ game luôn ngang), 2 luồng: ~0.8s CPU/lần, nhanh gấp 4, độ chính xác như cũ.
            self.eng = RapidOCR(det_limit_type="max", det_limit_side_len=1920, use_cls=False, intra_op_num_threads=2, inter_op_num_threads=1)
            return
        except ImportError as e:
            if has_rapidocr(): raise RuntimeError(tr("ocr.rapidocr_is_downloaded_but_failed", e=e)) from None
            try: from rapidocr import RapidOCR; self.new = True
            except ImportError: raise RuntimeError(tr("ocr.rapidocr_not_installed_settings_ocr")) from None
        self.eng = RapidOCR()

    def recognize(self, img):
        bgr = np.ascontiguousarray(img[:, :, ::-1])
        if self.new:
            o = self.eng(bgr)
            items = list(zip(o.boxes, o.txts)) if o.txts is not None else []
        else:
            res, _ = self.eng(bgr); items = [(b, t) for b, t, _ in (res or [])]
        return _lines([(float(np.mean([p[1] for p in b])), float(min(p[0] for p in b)), float(np.ptp([p[1] for p in b]) or 1), t) for b, t in items])

class TesseractOcr:
    name = "tesseract"
    def __init__(self, lang="eng"):
        import os, shutil, pytesseract; from .engines import tesseract_exe
        self.pt = pytesseract; self.lang = {"en-US": "eng", "en": "eng"}.get(lang, lang)
        exe = tesseract_exe()                              # engines/tesseract (nút Tải) > PATH > Program Files
        if not exe and not shutil.which("tesseract"):
            exe = next((p for d in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"))
                        if d and os.path.exists(p := os.path.join(d, "Tesseract-OCR", "tesseract.exe"))), None)
        if exe: pytesseract.pytesseract.tesseract_cmd = exe
        try: self.pt.get_tesseract_version()
        except Exception: raise RuntimeError(tr("ocr.tesseract_not_installed_settings_ocr")) from None
    def recognize(self, img):
        return [l for l in self.pt.image_to_string(img, lang=self.lang).splitlines() if l.strip()]

def _lines(boxes):
    """Gom box (y_center, x_left, height, text) thành dòng."""
    boxes.sort(); lines = []
    for y, x, h, t in boxes:
        if lines and abs(lines[-1][0] - y) < h * 0.6: lines[-1][1].append((x, t))
        else: lines.append([y, [(x, t)]])
    return [" ".join(t for _, t in sorted(parts)) for _, parts in lines]

def _resize(img, s):
    from PIL import Image
    h, w = img.shape[:2]
    return np.asarray(Image.fromarray(img).resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS))

ENGINES = {"windows": WindowsOcr, "rapidocr": RapidOcr, "tesseract": TesseractOcr}

def create(name, lang):
    return ENGINES[name](lang)
