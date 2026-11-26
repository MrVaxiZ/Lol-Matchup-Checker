"""Draws the app icon (gold crossed swords in a hexagon, dark background) with Pillow.

    python packaging/make_icon.py

Writes packaging/icon.ico (for the .exe) and lol_matchup_checker/assets/icon.png (window icon).
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024  # drawn large, scaled down for each icon size
BG = (14, 19, 24, 255)
GOLD = (200, 170, 110, 255)
GOLD_LIGHT = (240, 216, 160, 255)
GOLD_DARK = (122, 106, 72, 255)
TEAL = (10, 200, 185)
ROOT = Path(__file__).resolve().parent.parent


def hexagon(cx, cy, r, rot=90):
    return [(cx + r * math.cos(math.radians(rot + 60 * i)), cy + r * math.sin(math.radians(rot + 60 * i)))
            for i in range(6)]


def sword(length=760, blade_w=70):
    """One upright sword on a transparent layer, centred on the layer."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = S // 2
    top = (S - length) // 2
    tip, blade_end = top, top + int(length * 0.68)
    # blade with a ridge (light left half, darker right half)
    d.polygon([(cx, tip), (cx + blade_w // 2, tip + blade_w), (cx + blade_w // 2, blade_end), (cx - blade_w // 2, blade_end),
               (cx - blade_w // 2, tip + blade_w)], fill=GOLD)
    d.polygon([(cx, tip), (cx - blade_w // 2, tip + blade_w), (cx - blade_w // 2, blade_end), (cx, blade_end)], fill=GOLD_LIGHT)
    d.line([(cx, tip + 30), (cx, blade_end - 10)], fill=GOLD_DARK, width=6)
    # cross-guard with pointed ends
    gy, gw, gh = blade_end, 250, 44
    d.polygon([(cx - gw // 2 - 30, gy + gh // 2), (cx - gw // 2, gy), (cx + gw // 2, gy), (cx + gw // 2 + 30, gy + gh // 2),
               (cx + gw // 2, gy + gh), (cx - gw // 2, gy + gh)], fill=GOLD)
    # grip and pommel
    grip_top, grip_bottom = gy + gh, gy + gh + int(length * 0.2)
    d.rectangle([cx - 24, grip_top, cx + 24, grip_bottom], fill=GOLD_DARK)
    for y in range(grip_top + 14, grip_bottom, 26):  # wrapping
        d.line([(cx - 24, y), (cx + 24, y - 10)], fill=GOLD, width=6)
    d.ellipse([cx - 44, grip_bottom - 8, cx + 44, grip_bottom + 80], fill=GOLD)
    d.ellipse([cx - 18, grip_bottom + 18, cx + 18, grip_bottom + 54], fill=TEAL + (255,))
    return layer


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2
    d.polygon(hexagon(c, c, 500), fill=GOLD_DARK)  # outer rim
    d.polygon(hexagon(c, c, 470), fill=GOLD)
    d.polygon(hexagon(c, c, 440), fill=BG)

    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([c - 260, c - 260, c + 260, c + 260], fill=TEAL + (110,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(110)))

    blade = sword()
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for angle in (45, -45):
        rotated = blade.rotate(angle, resample=Image.BICUBIC, center=(c, c))
        mask = rotated.split()[3]
        shadow.paste((0, 0, 0, 170), (14, 18), mask)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    for angle in (45, -45):
        img.alpha_composite(blade.rotate(angle, resample=Image.BICUBIC, center=(c, c)))
    # keep everything inside the hexagon
    hex_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hex_mask).polygon(hexagon(c, c, 500), fill=255)
    img.putalpha(Image.composite(img.split()[3], Image.new("L", (S, S), 0), hex_mask))
    return img


if __name__ == "__main__":
    icon = draw()
    (ROOT / "lol_matchup_checker" / "assets").mkdir(exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(ROOT / "lol_matchup_checker" / "assets" / "icon.png")
    icon.save(ROOT / "packaging" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.resize((512, 512), Image.LANCZOS).save(ROOT / "packaging" / "icon_preview.png")
    print("icon written")
