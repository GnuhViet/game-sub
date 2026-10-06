"""Ảnh minh họa cho README: python tools/screenshots.py -> docs/screenshots/<vi|en>/*.png
Vẽ thẳng các cửa sổ Qt ra ảnh (không cần mở game), dùng thư mục data tạm nên không đụng cài đặt thật."""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
import gamesub.config as C
C.DATA_DIR = Path(tempfile.mkdtemp()); C.CFG_PATH = C.DATA_DIR / "settings.json"
from gamesub import i18n; i18n.set_lang(LANG)
from PySide6.QtCore import QPoint
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QImage
from PySide6.QtWidgets import QApplication
from gamesub.config import Config
from gamesub.ui_overlay import Overlay, WordPopup
from gamesub.ui_dialogs import SettingsDialog

OUT = ROOT / "docs" / "screenshots" / LANG
SAMPLE = ("Aria", "We finally made it. The old lighthouse should be just past the ridge.",          # (nhân vật, câu gốc, bản dịch, nguồn, từ tra, nghĩa)
          "Cuối cùng cũng tới nơi. Ngọn hải đăng cũ chắc ở ngay sau sườn núi kia.", "Google Translate",
          "lighthouse", "/ˈlaɪt.haʊs/ (n.) ngọn hải đăng")

def scene(w, h):
    """Nền tối giả lập khung hình game (gradient) để overlay bán trong suốt nhìn rõ."""
    img = QImage(w, h, QImage.Format_ARGB32); p = QPainter(img); g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#2b3a55")); g.setColorAt(0.6, QColor("#3f5a4b")); g.setColorAt(1, QColor("#1c2230")); p.fillRect(img.rect(), g); p.end()
    return img

def main():
    main.app = QApplication(sys.argv); OUT.mkdir(parents=True, exist_ok=True)
    cfg = Config(); cfg["overlay_geom"] = [0, 0, 820, 150]
    ov = Overlay(cfg); ov.show_line(SAMPLE[0], SAMPLE[1], SAMPLE[2], SAMPLE[3]); ov._set_bar(True); ov.resize(820, 175)
    pop = WordPopup(cfg); pop.show_for(SAMPLE[4], "", "", SAMPLE[5], QPoint(0, 0), pinned=True, source="Google Translate"); pop.hide()
    W, H = 980, ov.height() + pop.height() + 90
    img = scene(W, H); p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
    oy = H - ov.height() - 30; p.drawPixmap((W - ov.width()) // 2, oy, ov.grab())
    p.drawPixmap(W // 2 + 60 - pop.width() // 2, oy - pop.height() - 8, pop.grab()); p.end()     # ngay trên chữ "lighthouse"
    img.save(str(OUT / "overlay.png"))
    d = SettingsDialog(cfg); d.resize(760, 640)
    from PySide6.QtWidgets import QTabWidget
    tabs = d.findChild(QTabWidget)
    for i, name in ((0, "settings_ocr"), (1, "settings_translate")):
        tabs.setCurrentIndex(i); d.grab().save(str(OUT / f"{name}.png"))
    print("->", OUT)

if __name__ == "__main__": main()
