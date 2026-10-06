"""Đa ngôn ngữ giao diện. Chuỗi gốc (tiếng Việt) viết thẳng trong code và bọc tr("…"); bản dịch nằm ở
locales/<mã>.py dạng T = {chuỗi gốc: bản dịch}. Biến trong chuỗi dùng {tên}: tr("Đã lưu «{w}»", w=word).
Ngôn ngữ chọn 1 lần lúc khởi động (main.py gọi set_lang trước khi import giao diện) -> đổi ngôn ngữ cần mở lại app.
Thêm ngôn ngữ: copy locales/en.py thành locales/<mã>.py, dịch phần giá trị, thêm vào TABLES (locales/__init__.py) và LANGS."""
LANGS = {"vi": "Tiếng Việt", "en": "English"}
_lang, _table = "vi", {}

def system_lang():
    """Ngôn ngữ Windows: tiếng Việt -> vi, còn lại -> en."""
    try:
        from PySide6.QtCore import QLocale
        return "vi" if QLocale.system().language() == QLocale.Vietnamese else "en"
    except Exception: return "vi"

def set_lang(code):
    """code "" = theo Windows."""
    global _lang, _table
    _lang = code if code in LANGS else system_lang()
    from .locales import TABLES
    _table = TABLES.get(_lang, {})

def lang(): return _lang

def tr(s, **kw):
    s = _table.get(s, s)
    return s.format(**kw) if kw else s

def N_(s):
    """Đánh dấu chuỗi cần dịch nhưng dịch lúc dùng (bảng tooltip, menu…): tr(TIPS[k])."""
    return s
