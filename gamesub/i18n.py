"""Đa ngôn ngữ giao diện: mỗi ngôn ngữ 1 file locales/<mã>.json = {"_name": "Tên ngôn ngữ", "key": "chữ"}.
Code gọi tr("key") / tr("key", n=5) (biến trong chữ dạng {n}); bảng hằng (tooltip, menu) đánh dấu N_("key") rồi tr() lúc dùng.
vi.json là ngôn ngữ gốc, đủ mọi key; ngôn ngữ khác thiếu key thì lấy chữ tiếng Việt.
Thêm ngôn ngữ: copy en.json thành <mã>.json (vd ja.json), đổi "_name" và dịch phần giá trị — app tự nhận, không cần sửa code.
Ngôn ngữ chọn 1 lần lúc khởi động (main.py gọi set_lang trước khi import giao diện) -> đổi ngôn ngữ cần mở lại app."""
import json
from pathlib import Path

DIR = Path(__file__).resolve().parent / "locales"
BASE = "vi"

def _read(code):
    try: return json.loads((DIR / f"{code}.json").read_text("utf-8"))
    except (OSError, ValueError) as e: print(f"locales/{code}.json lỗi:", e); return {}

def _langs():
    out = {BASE: _read(BASE).get("_name", BASE)}
    for p in sorted(DIR.glob("*.json")):
        if p.stem != BASE: out[p.stem] = _read(p.stem).get("_name", p.stem)
    return out

LANGS = _langs()                    # {mã: tên hiển thị}, tiếng Việt đứng đầu
_lang, _base, _table = BASE, _read(BASE), {}

def system_lang():
    """Ngôn ngữ Windows nếu có file dịch, không thì English (hoặc tiếng Việt)."""
    try:
        from PySide6.QtCore import QLocale
        code = QLocale.system().name().split("_")[0]
    except Exception: code = BASE
    return code if code in LANGS else ("en" if "en" in LANGS else BASE)

def set_lang(code):
    """code "" = theo Windows."""
    global _lang, _table
    _lang = code if code in LANGS else system_lang()
    _table = {} if _lang == BASE else _read(_lang)

def lang(): return _lang

def tr(key, **kw):
    s = _table.get(key) or _base.get(key) or key
    return s.format(**kw) if kw else s

def N_(key):
    """Đánh dấu key cần dịch nhưng dịch lúc dùng (bảng tooltip, menu…): tr(TIPS[k])."""
    return key
