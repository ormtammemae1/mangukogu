"""Draw the home-screen icons (four toy blocks). Run once: python deploy/make_icons.py"""
from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
BG = "#fbf7f2"
BLOCKS = ["#e0703f", "#f0b44c", "#5fb3a8", "#6a9fd8"]


def draw(size: int) -> Image.Image:
    s = 4  # draw large, then shrink for smooth edges
    big = size * s
    img = Image.new("RGB", (big, big), BG)
    d = ImageDraw.Draw(img)
    # Keep everything inside the central 80% so Android's maskable crop doesn't cut it.
    margin, gap = big * 0.2, big * 0.05
    cell = (big - 2 * margin - gap) / 2
    for i, color in enumerate(BLOCKS):
        x = margin + (i % 2) * (cell + gap)
        y = margin + (i // 2) * (cell + gap)
        d.rounded_rectangle((x, y, x + cell, y + cell), radius=cell * 0.22, fill=color)
    return img.resize((size, size), Image.LANCZOS)


for name, size in [("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)]:
    draw(size).save(STATIC / name)
    print("wrote", name)
