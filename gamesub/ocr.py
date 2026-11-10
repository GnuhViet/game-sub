"""OCR engines. Mỗi engine: recognize(np.ndarray RGB uint8) -> list[str] (các dòng, từ trên xuống);
boxes(img) -> [(x, y, w, h, text)] khung từng dòng (pixel của img) — dùng cho Gợi ý vùng."""
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

    def _run(self, img):
        h, w = img.shape[:2]; s = 1.0
        if max(h, w) > self.max_dim:
            s = self.max_dim / max(h, w); img = _resize(img, s); h, w = img.shape[:2]
        rgba = np.dstack([img, np.full((h, w), 255, np.uint8)]).tobytes()
        dw = self.DW(); dw.write_bytes(rgba)
        bmp = self.SB.create_copy_from_buffer(dw.detach_buffer(), self.PF.RGBA8, w, h)   # bản có alpha tên là create_copy_with_alpha_from_buffer
        return self.loop.run_until_complete(self._rec(bmp)), s

    def recognize(self, img): return [l.text for l in self._run(img)[0].lines]

    def boxes(self, img):
        res, s = self._run(img); out = []
        for l in res.lines:
            rs = [w.bounding_rect for w in l.words]
            if not rs: continue
            x0, y0 = min(r.x for r in rs), min(r.y for r in rs); x1, y1 = max(r.x + r.width for r in rs), max(r.y + r.height for r in rs)
            out.append((x0 / s, y0 / s, (x1 - x0) / s, (y1 - y0) / s, l.text))
        return out

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

    def _items(self, img):
        bgr = np.ascontiguousarray(img[:, :, ::-1])
        if self.new:
            o = self.eng(bgr)
            return list(zip(o.boxes, o.txts)) if o.txts is not None else []
        res, _ = self.eng(bgr); return [(b, t) for b, t, _ in (res or [])]

    def boxes(self, img):
        out = []
        for b, t in self._items(img):
            xs, ys = [float(p[0]) for p in b], [float(p[1]) for p in b]
            out.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), t))
        return out

    def recognize(self, img):
        items = self._items(img)
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
    def boxes(self, img):
        d = self.pt.image_to_data(img, lang=self.lang, output_type=self.pt.Output.DICT); ln = {}
        for i, t in enumerate(d["text"]):
            if not t.strip(): continue
            k = (d["block_num"][i], d["par_num"][i], d["line_num"][i]); x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
            a = ln.setdefault(k, [x, y, x + w, y + h, []]); a[0], a[1], a[2], a[3] = min(a[0], x), min(a[1], y), max(a[2], x + w), max(a[3], y + h); a[4].append(t)
        return [(x0, y0, x1 - x0, y1 - y0, " ".join(ts)) for x0, y0, x1, y1, ts in ln.values()]

def _lines(boxes):
    """Gom box (y_center, x_left, height, text) thành dòng."""
    boxes.sort(); lines = []
    for y, x, h, t in boxes:
        if lines and abs(lines[-1][0] - y) < h * 0.6: lines[-1][1].append((x, t))
        else: lines.append([y, [(x, t)]])
    return [" ".join(t for _, t in sorted(parts)) for _, parts in lines]

def blocks(lines, min_chars=4):
    """Gom khung dòng [(x, y, w, h, text)] thành khối chữ (hộp thoại, đoạn dẫn…) -> [(x, y, w, h, text)], khối to trước.
    2 dòng cùng khối: cao gần bằng nhau, cách nhau theo chiều dọc < 1.2 lần cao dòng, chồng / gần nhau theo chiều ngang."""
    ls = sorted([list(l[:4]) + [str(l[4]).strip()] for l in lines if l[2] > 0 and l[3] > 0 and str(l[4]).strip()], key=lambda l: (l[1], l[0]))
    out = []
    for x, y, w, h, t in ls:
        for b in out:
            bx, by, bw, bh, lh, ts = b
            if not (0.6 < h / lh < 1.65): continue
            gap_y = y - (by + bh); gap_x = max(bx - (x + w), x - (bx + bw))
            if -h < gap_y < 1.2 * max(h, lh) and gap_x < 2 * max(h, lh):
                nx, ny = min(bx, x), min(by, y); b[:] = [nx, ny, max(bx + bw, x + w) - nx, max(by + bh, y + h) - ny, max(lh, h), ts + [t]]; break
        else: out.append([x, y, w, h, h, [t]])
    res = [(x, y, w, h, " ".join(ts)) for x, y, w, h, _, ts in out if len("".join(ts).replace(" ", "")) >= min_chars]
    return sorted(res, key=lambda b: -b[2] * b[3])

def _resize(img, s):
    from PIL import Image
    h, w = img.shape[:2]
    return np.asarray(Image.fromarray(img).resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS))

ENGINES = {"windows": WindowsOcr, "rapidocr": RapidOcr, "tesseract": TesseractOcr}

def create(name, lang):
    return ENGINES[name](lang)
