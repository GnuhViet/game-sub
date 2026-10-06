"""Đa ngôn ngữ: python tests/test_i18n.py"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import i18n_check
from gamesub import i18n

# 1) mọi chuỗi tr()/N_() có bản dịch, biến {…} khớp; không còn chuỗi tiếng Việt chưa bọc
errs = i18n_check.check(); assert not errs, "\n".join(errs)
todo = i18n_check.scan()[1]; assert not todo, "\n".join(f"{w} {s}" for w, s in todo)

# 2) tr: chọn ngôn ngữ, điền biến, chuỗi chưa có bản dịch thì giữ nguyên
i18n.set_lang("en"); assert i18n.lang() == "en"
assert i18n.tr("Đã lưu «{w}» vào sổ từ", w="wake") == "Saved “wake” to vocabulary"
assert i18n.tr("chuỗi lạ") == "chuỗi lạ"
i18n.set_lang("vi"); assert i18n.tr("Cài đặt") == "Cài đặt"
i18n.set_lang(""); assert i18n.lang() in i18n.LANGS                     # "" = theo Windows

# 3) giao diện dựng được bằng tiếng Anh (chuỗi ở mức module dịch lúc dùng)
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
