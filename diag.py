"""Tự kiểm tra trên Windows các phần chưa test được: DPI/đa màn hình, mss chụp game, OCR, hotkey.
Chạy: diag.bat (hoặc python diag.py). Báo cáo ghi ra data/diag.txt + ảnh data/diag_*.png."""
import platform, sys, time, traceback
import numpy as np
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QRect
from wuwasub.config import Config, DATA_DIR
from wuwasub.ui_region import to_physical
from wuwasub.capture import grab, open_sct
from wuwasub import ocr

SAMPLE = "Rover, you finally woke up. Let's head to Jinzhou."
out = []
def log(s=""): print(s); out.append(str(s))
def section(t): log(); log(f"== {t} ==")

def dpi_awareness():
    if sys.platform != "win32": return "n/a"
    import ctypes; u32 = ctypes.windll.user32
    try:
        ctx = u32.GetThreadDpiAwarenessContext()
        return {0: "unaware", 1: "system", 2: "per-monitor"}.get(u32.GetAwarenessFromDpiAwarenessContext(ctx), "?")
    except Exception as e: return f"? ({e})"

def sample_image(scale=1.0):
    from PIL import Image, ImageDraw, ImageFont
    size = int(28 * scale)
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try: font = ImageFont.truetype(name, size); break
        except OSError: font = None
    if font is None: font = ImageFont.load_default(size=size)
    w = int(font.getlength(SAMPLE)) + 40
    img = Image.new("RGB", (w, size * 2 + 20), (20, 24, 30)); ImageDraw.Draw(img).text((20, 10), SAMPLE, fill=(240, 240, 240), font=font)
    return np.asarray(img)

def check_screens(cfg):
    section("Màn hình (Qt) vs mss")
    log(f"DPI awareness: {dpi_awareness()}")
    with open_sct() as sct:
        mons = sct.monitors[1:]
        for m in mons: log(f"mss  : x={m['left']} y={m['top']} {m['width']}x{m['height']}")
        for s in QGuiApplication.screens():
            g = s.geometry(); p = to_physical(s, QRect(0, 0, g.width(), g.height()))
            hit = any((m["left"], m["top"], m["width"], m["height"]) == (p["x"], p["y"], p["w"], p["h"]) for m in mons)
            log(f"Qt   : {s.name()} geom={g.x()},{g.y()} {g.width()}x{g.height()} DPR={s.devicePixelRatio()} -> physical {p} "
                + ("OK" if hit else "!! KHÔNG khớp mss — vùng chụp sẽ lệch"))
        for key in ("region", "speaker_region"):
            r = cfg[key]
            if not r: log(f"{key}: chưa chọn"); continue
            img = grab(sct, r); path = DATA_DIR / f"diag_{key}.png"
            from PIL import Image; Image.fromarray(img).save(path)
            mean, std = float(img.mean()), float(img.std())
            log(f"{key}: {r} -> {path.name} (sáng TB {mean:.0f}, độ tương phản {std:.0f})"
                + ("  !! ảnh gần như đen/đồng màu: mss không chụp được game (thử Borderless, tắt HDR) hoặc vùng sai" if std < 4 else ""))

def check_ocr(cfg):
    section("OCR")
    img = sample_image()
    from PIL import Image; Image.fromarray(img).save(DATA_DIR / "diag_ocr_sample.png")
    for name in ocr.ENGINES:
        try:
            t0 = time.time(); e = ocr.create(name, cfg["ocr_lang"]); t1 = time.time()
            lines = e.recognize(img); t2 = time.time()
            text = " ".join(lines)
            from rapidfuzz import fuzz
            log(f"{name:10s}: init {t1 - t0:.2f}s, nhận dạng {(t2 - t1) * 1000:.0f}ms, khớp {fuzz.ratio(text, SAMPLE):.0f}% -> {text!r}")
            if cfg["region"]:
                with open_sct() as sct: log(f"{'':10s}  vùng thoại hiện tại -> {' | '.join(e.recognize(grab(sct, cfg['region'])))!r}")
        except Exception as ex:
            log(f"{name:10s}: lỗi {type(ex).__name__}: {ex}")
            if name == cfg["ocr_engine"]: log(traceback.format_exc().rstrip())

def check_hotkeys(cfg):
    section("Hotkey")
    if sys.platform != "win32": log("Bỏ qua (không phải Windows)"); return
    import ctypes; from wuwasub.hotkeys import parse; u32 = ctypes.windll.user32
    for n, (action, seq) in enumerate(cfg["hotkeys"].items(), 0xB000):
        if not seq: continue
        mods, vk = parse(seq)
        ok = vk is not None and u32.RegisterHotKey(None, n, mods | 0x4000, vk)
        if ok: u32.UnregisterHotKey(None, n)
        log(f"{action:8s} {seq:10s}: " + ("OK" if ok else "!! không đăng ký được (trùng app khác hoặc sai cú pháp) — WuWaSub đang chạy cũng gây trùng"))

def main():
    app = QGuiApplication(sys.argv); DATA_DIR.mkdir(parents=True, exist_ok=True); cfg = Config()
    log(f"WuWa Sub diag — {time.strftime('%Y-%m-%d %H:%M')}")
    import PySide6, mss
    log(f"{platform.platform()} | Python {platform.python_version()} | PySide6 {PySide6.__version__} | mss {mss.__version__ if hasattr(mss, '__version__') else '?'}")
    log(f"ocr_engine={cfg['ocr_engine']} ocr_lang={cfg['ocr_lang']} ocr_scale={cfg['ocr_scale']}")
    from wuwasub import winapp
    log(f"WuWaSub quyền admin: {winapp.self_elevated()} | target_app={cfg['target_app'] or '(không lọc)'}"
        + "".join(f" | {exe} admin: {winapp.elevated(pid)}" for pid, exe in [winapp.foreground()] if exe))
    try:
        from wuwasub.spacing import Spacer; log("Tách từ dính: 'Rover,youfinallywoke up.' -> " + repr(Spacer().fix('Rover,youfinallywoke up.')))
    except Exception as ex: log(f"Tách từ dính: lỗi {ex}")
    for f in (check_screens, check_ocr, check_hotkeys):
        try: f(cfg)
        except Exception: log(traceback.format_exc().rstrip())
    section("Kiểm tra tay")
    log("1. Mở game (Borderless), bật WuWaSub: overlay có nổi trên game không? Alt+Tab có mất overlay không?")
    log("2. Mở data/diag_region.png: đúng khung thoại không (không lệch, không đen)?")
    (DATA_DIR / "diag.txt").write_text("\n".join(out), "utf-8"); log(); log(f"Đã ghi {DATA_DIR / 'diag.txt'} — gửi file này khi báo lỗi.")
    del app

if __name__ == "__main__":
    main()
