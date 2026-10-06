"""Đa ngôn ngữ: python tests/test_i18n.py"""
import json, os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32": os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))   # offscreen không có font hệ thống
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import i18n_check
from gamesub import i18n

# 1) mọi key dùng trong code có trong vi.json; mọi ngôn ngữ đủ key, biến {…} khớp; không còn chuỗi tiếng Việt viết thẳng
errs, _ = i18n_check.check(); assert not errs, "\n".join(errs)
todo = i18n_check.scan()[1]; assert not todo, "\n".join(f"{w} {s}" for w, s in todo)
assert list(i18n.LANGS)[0] == "vi" and i18n.LANGS["en"] == "English"

# 2) tr: chọn ngôn ngữ, điền biến; key lạ -> trả lại key; ngôn ngữ thiếu key -> lấy tiếng Việt
i18n.set_lang("en"); assert i18n.lang() == "en"
assert i18n.tr("app.saved_w_vocabulary", w="wake") == "Saved “wake” to vocabulary"
assert i18n.tr("không.có.key") == "không.có.key"
i18n._table = {"_name": "Test"}; assert i18n.tr("tray.settings") == "Cài đặt"       # thiếu key -> tiếng Việt
i18n.set_lang("vi"); assert i18n.tr("tray.settings") == "Cài đặt"
i18n.set_lang(""); assert i18n.lang() in i18n.LANGS                                    # "" = theo Windows
i18n.set_lang("xx"); assert i18n.lang() in i18n.LANGS                                  # mã không có file -> theo Windows

# 3) thả file ngôn ngữ mới vào thư mục -> tự nhận (không sửa code)
d = Path(tempfile.mkdtemp()); old = i18n.DIR
for f in old.glob("*.json"): (d / f.name).write_text(f.read_text("utf-8"), "utf-8")
(d / "ja.json").write_text(json.dumps({"_name": "日本語", "tray.settings": "設定"}, ensure_ascii=False), "utf-8")
i18n.DIR = d; assert i18n._langs()["ja"] == "日本語"; i18n.LANGS = i18n._langs()
i18n.set_lang("ja"); assert i18n.tr("tray.settings") == "設定" and i18n.tr("tray.quit") == "Thoát"
i18n.DIR = old; i18n.LANGS = i18n._langs(); i18n.set_lang("vi")

# 4) giao diện dựng được bằng tiếng Anh (bảng hằng N_ dịch lúc dùng)
i18n.set_lang("en")
from PySide6.QtWidgets import QApplication, QTabWidget
q = QApplication(sys.argv)
from gamesub import config
from gamesub.ui_dialogs import SettingsDialog
from gamesub.ui_overlay import Overlay
cfg = config.Config(ROOT / "tests" / "_nonexistent.json")
sd = SettingsDialog(cfg); tabs = sd.findChild(QTabWidget)
assert [tabs.tabText(i) for i in range(tabs.count())] == ["OCR", "Translation", "Prompt", "Characters", "Dictionary", "Appearance", "Hotkeys"]
assert sd.windowTitle() == "Settings" and sd.w["display"][0].itemText(0) == "Both (source + translation)"
ov = Overlay(dict(cfg)); assert ov.btns["prev"].toolTip().startswith("Previous line")
i18n.set_lang("vi")
print("I18N OK")
