# -*- coding: utf-8 -*-
"""Vẽ biểu tượng ứng dụng (lịch + trăng) và lưu thành .ico nhiều kích thước. Cần Pillow."""
import os
import sys
from PIL import Image, ImageDraw

S = 256
ACCENT = (79, 195, 247, 255)
DARK = (27, 35, 48, 255)


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # thân lịch
    d.rounded_rectangle((16, 28, 240, 240), radius=40, fill=(255, 255, 255, 255))
    # dải màu phía trên
    d.rounded_rectangle((16, 28, 240, 100), radius=40, fill=ACCENT)
    d.rectangle((16, 64, 240, 100), fill=ACCENT)
    # khoen treo
    for x in (76, 180):
        d.rounded_rectangle((x - 10, 8, x + 10, 56), radius=10, fill=DARK)
    # trăng lưỡi liềm (âm lịch)
    d.ellipse((58, 118, 158, 218), fill=(255, 193, 7, 255))
    d.ellipse((84, 108, 184, 208), fill=(255, 255, 255, 255))
    # lưới ngày
    for r in range(3):
        for c in range(2):
            x = 170 + c * 30
            y = 128 + r * 30
            d.rounded_rectangle((x, y, x + 18, y + 18), radius=5, fill=(207, 216, 220, 255) if (r, c) != (1, 0) else ACCENT)
    return img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join("assets", "icon.ico")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img = draw()
    img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(os.path.splitext(out)[0] + ".png")
    print("saved", out)


if __name__ == "__main__":
    main()
