"""Vẽ icon app -> gamesub/assets/icon.png + icon.ico (python tools/make_icon.py).
Ô vuông bo góc nền xanh đêm, bong bóng thoại vàng, 2 dòng phụ đề (câu gốc mờ + bản dịch đậm)."""
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024                                            # vẽ to rồi thu nhỏ cho mượt
OUT = Path(__file__).resolve().parent.parent / "gamesub" / "assets"

def lerp(a, b, t): return tuple(round(x + (y - x) * t) for x, y in zip(a, b))

def draw():
    bg = Image.new("RGBA", (S, S))
    top, bot = (52, 70, 122), (17, 22, 40)          # gradient chéo xanh đêm
    px = bg.load()
    for y in range(S):
        for x in range(S): px[x, y] = lerp(top, bot, (x + y) / (2 * S)) + (255,)
    mask = Image.new("L", (S, S)); ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=230, fill=255)
    img = Image.new("RGBA", (S, S)); img.paste(bg, mask=mask)
    d = ImageDraw.Draw(img)
    gold, dark = (232, 194, 106, 255), (17, 22, 40, 255)
    # bong bóng thoại + đuôi
    d.rounded_rectangle((150, 190, 874, 700), radius=150, fill=gold)
    d.polygon([(300, 640), (470, 640), (270, 850)], fill=gold)
    # 2 dòng phụ đề: dòng gốc mảnh/mờ, dòng dịch dày/đậm
    d.rounded_rectangle((270, 330, 754, 400), radius=35, fill=(17, 22, 40, 150))
    d.rounded_rectangle((270, 470, 680, 560), radius=45, fill=dark)
    return img

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    img = draw()
    img.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("->", OUT)

if __name__ == "__main__": main()
