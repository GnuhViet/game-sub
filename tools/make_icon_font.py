"""Cắt font Material Design Icons (MDI6) chỉ còn các icon app dùng -> gamesub/assets/mdi6.ttf + mdi6.json (tên -> mã).
Cần: pip install fonttools qtawesome (chỉ lúc chạy script này). Thêm icon: thêm tên vào NAMES rồi chạy lại.
Font MDI: Pictogrammers, Apache License 2.0 — https://github.com/Templarian/MaterialDesign-Webfont"""
import json
from pathlib import Path
import qtawesome
from fontTools import subset

NAMES = ["account", "arrow-down", "arrow-up", "book-open-variant", "camera", "close", "cog", "eraser", "folder-open",
         "information-outline", "lock", "lock-open-variant", "pause", "play", "refresh", "selection-drag", "selection-search",
         "skip-next", "skip-previous", "tag", "translate", "translate-off", "window-minimize"]

SRC = Path(qtawesome.__file__).parent / "fonts"
OUT = Path(__file__).resolve().parent.parent / "gamesub" / "assets"

def main():
    font = next(SRC.glob("materialdesignicons6-webfont-[0-9]*.ttf"))
    charmap = json.loads(next(SRC.glob("materialdesignicons6-webfont-charmap-*.json")).read_text("utf-8"))
    codes = {n: int(charmap[n], 16) for n in NAMES}
    opts = subset.Options(); opts.name_IDs = ["*"]; opts.notdef_outline = True; opts.layout_features = []
    s = subset.Subsetter(opts); f = subset.load_font(str(font), opts)
    s.populate(unicodes=list(codes.values())); s.subset(f); subset.save_font(f, str(OUT / "mdi6.ttf"), opts)
    (OUT / "mdi6.json").write_text(json.dumps(codes, indent=1) + "\n", "utf-8")
    print(f"{font.name} -> {OUT / 'mdi6.ttf'} ({(OUT / 'mdi6.ttf').stat().st_size} B, {len(codes)} icon)")

if __name__ == "__main__": main()
