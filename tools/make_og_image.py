#!/usr/bin/env python3
"""Compose the 1200x630 Open Graph card for docs/index.html.

Source of truth for the artwork is docs/img/board-front.jpg (the rendered top
face of the golden board); the palette and wording follow docs/index.html so the
link preview matches the page it links to. Re-run after re-rendering the board:

    python3 tools/make_og_image.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "docs" / "img" / "board-front.jpg"
OUT = ROOT / "docs" / "img" / "og-card.jpg"

W, H = 1200, 630
BG = (13, 20, 17)          # --bg
LINE = (34, 53, 43)        # --line
INK = (230, 239, 233)      # --ink
DIM = (157, 179, 167)      # --dim
FAINT = (111, 135, 123)    # --faint
GOLD = (232, 185, 59)      # --gold

SFNS = "/System/Library/Fonts/SFNS.ttf"
MONO = "/System/Library/Fonts/Supplemental/Andale Mono.ttf"


def sf(size, weight):
    f = ImageFont.truetype(SFNS, size)
    # SFNS is a variable font; set the weight axis (wght 400..860).
    f.set_variation_by_axes([weight])
    return f


def main():
    card = Image.new("RGB", (W, H), BG)

    # Board artwork, full-bleed on the right, cropped to a hair under full width
    # so the die texture reads rather than the empty margin.
    board = Image.open(BOARD).convert("RGB")
    scale = H / board.height
    board = board.resize((round(board.width * scale), H), Image.LANCZOS)
    bx = W - board.width
    card.paste(board, (bx, 0))

    # Fade the board's left edge into the background so the text has room.
    fade_w = 150
    fade = Image.new("RGB", (fade_w, H), BG)
    mask = Image.new("L", (fade_w, H))
    for x in range(fade_w):
        v = int(255 * (1 - x / fade_w) ** 1.4)
        mask.paste(v, (x, 0, x + 1, H))
    card.paste(fade, (bx, 0), mask)

    d = ImageDraw.Draw(card)

    # Gold rule at the very top, echoing the page's accent.
    d.rectangle([0, 0, W, 5], fill=GOLD)

    x = 64
    d.text((x, 96), "discrete6502", font=sf(76, 800), fill=GOLD)
    d.text((x, 190), "a MOS 6502 CPU built from", font=sf(33, 500), fill=INK)
    d.text((x, 232), "4,051 discrete transistors", font=sf(33, 700), fill=INK)

    d.text(
        (x, 300),
        "laid out as the original die",
        font=sf(25, 400),
        fill=DIM,
    )

    d.line([x, 360, x + 430, 360], fill=LINE, width=2)

    stats = [
        ("4,051", "SOT-323 FETs"),
        ("291 x 322", "mm, 6 layers"),
        ("5,328", "placements"),
    ]
    y = 390
    for value, label in stats:
        d.text((x, y), value, font=ImageFont.truetype(MONO, 30), fill=GOLD)
        d.text((x + 190, y + 5), label, font=sf(23, 400), fill=DIM)
        y += 48

    d.text(
        (x, 552),
        "epatel.github.io/discrete6502",
        font=ImageFont.truetype(MONO, 22),
        fill=FAINT,
    )

    card.save(OUT, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"{OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1024:.0f} KB  {W}x{H}")


if __name__ == "__main__":
    main()
