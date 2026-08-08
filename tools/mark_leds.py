#!/usr/bin/env python3
"""Mark the 55 register LEDs on the board render, grouped by register.

Produces docs/leds-marked.jpg: the top-face render with every LED ringed in its
register's colour, each bit numbered, and the P flags named. This is the map you
need at bring-up, when "watch the A LEDs count" has to become "watch these eight
LEDs, this one is bit 0".

Everything comes from the board and the netlist, never from a drawing:

  - LED positions from gen/board_routed_golden.kicad_pcb (footprint origins)
  - register grouping and bit index from gen/netlist.json (`role` and `origin`)
  - the mm-to-pixel mapping is fitted on the render's own board extents, then
    *verified* by checking that all 55 computed positions land on LED pad pixels

Usage:  python3 tools/mark_leds.py [--render gen/board_top.png] [--out docs/leds-marked.jpg]
"""

import argparse
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

BOARD_W, BOARD_H = 290.7, 322.0     # outline, mm (tools/gen_pcb.py)

# 6502 P register bit names. Bit 5 has no flip-flop on the die, which is why
# there are 7 flag LEDs and not 8 -- p5 is absent from the netlist by nature.
P_FLAG_NAMES = {0: "C", 1: "Z", 2: "I", 3: "D", 4: "B", 6: "V", 7: "N"}

# One colour per register. Chosen to stay distinguishable against dark green and
# against each other, including for the common forms of colour blindness: the
# groups are also separated by position, so colour is a convenience not the only
# channel.
# `head_dx` pulls a column header sideways. Y and X sit only 3.8 mm apart --
# about 29 px -- so their headers must be splayed or they overlap illegibly.
GROUPS = {
    "led_Y":   {"label": "Y",   "colour": (0, 230, 140),   "side": "left",  "head_dx": -130},
    "led_X":   {"label": "X",   "colour": (0, 200, 255),   "side": "right", "head_dx": -55},
    "led_S":   {"label": "S",   "colour": (255, 210, 0),   "side": "right", "head_dx": 55},
    "led_A":   {"label": "A",   "colour": (255, 90, 60),   "side": "right", "head_dx": 0},
    "led_PCH": {"label": "PCH", "colour": (190, 130, 255), "side": "right", "head_dx": 0},
    "led_PCL": {"label": "PCL", "colour": (255, 100, 210), "side": "right", "head_dx": 0},
    "led_P":   {"label": "P",   "colour": (255, 255, 255), "side": "right", "head_dx": 0},
}

BANNER_H = 300   # black band added above the render, so the legend hides nothing

FONT_DIR = "/System/Library/Fonts/Supplemental"


def load_font(size, bold=True):
    for name in (("Arial Bold.ttf" if bold else "Arial.ttf"), "Arial.ttf"):
        p = os.path.join(FONT_DIR, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def parse_footprints(pcb_path):
    """Reference -> (x, y) in mm, straight out of the board file."""
    refs, cur_at, cur_fp = {}, None, None
    pat_at = re.compile(r"^\s*\(at ([-\d.]+) ([-\d.]+)")
    pat_ref = re.compile(r'\(property "Reference" "([^"]+)"')
    pat_fp = re.compile(r'^\s*\(footprint "([^"]+)"')
    with open(pcb_path) as f:
        for line in f:
            m = pat_fp.match(line)
            if m:
                cur_fp, cur_at = m.group(1), None
                continue
            if cur_fp and cur_at is None:
                m = pat_at.match(line)
                if m:
                    cur_at = (float(m.group(1)), float(m.group(2)))
                    continue
            m = pat_ref.search(line)
            if m and cur_at:
                refs[m.group(1)] = cur_at
                cur_fp, cur_at = None, None
    return refs


def fit_mapping(img):
    """Fit mm -> pixels on the render's own board extents.

    The render is the board outline on a black field, so the non-black bounding
    box *is* the outline. Verified by aspect ratio before it is trusted.
    """
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(int)
    ys, xs = np.where(a.sum(axis=2) > 60)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    w, h = x1 - x0 + 1, y1 - y0 + 1
    aspect, want = w / h, BOARD_W / BOARD_H
    if abs(aspect - want) / want > 0.01:
        raise SystemExit(f"render aspect {aspect:.4f} does not match the board "
                         f"{want:.4f}; this render is not a plain top view")
    return (x0, y0, w / BOARD_W, h / BOARD_H), (aspect, want)


def verify_mapping(img, points):
    """Confirm every LED lands on a pad pixel, and that this is not luck."""
    import numpy as np
    import random
    a = np.asarray(img.convert("RGB")).astype(int)

    def bright(px, py, half=1, thr=740):
        box = a[py - half:py + half + 1, px - half:px + half + 1]
        return box.size and box.sum(axis=2).max() > thr

    hit = sum(1 for px, py in points if bright(int(round(px)), int(round(py))))
    random.seed(7)
    H, W = a.shape[:2]
    ctrl = sum(1 for _ in range(2000)
               if bright(random.randint(200, W - 200), random.randint(200, H - 200)))
    return hit, len(points), ctrl / 2000.0


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcb", default=os.path.join(here, "gen/board_routed_golden.kicad_pcb"))
    ap.add_argument("--netlist", default=os.path.join(here, "gen/netlist.json"))
    ap.add_argument("--render", default=os.path.join(here, "gen/board_top.png"))
    ap.add_argument("--out", default=os.path.join(here, "docs/leds-marked.jpg"))
    args = ap.parse_args()

    nl = json.load(open(args.netlist))
    leds = [c for c in nl["components"] if c.get("type") == "led"]
    if len(leds) != 55:
        print(f"note: {len(leds)} LEDs in the netlist, expected 55", file=sys.stderr)

    pos = parse_footprints(args.pcb)
    missing = [c["ref"] for c in leds if c["ref"] not in pos]
    if missing:
        raise SystemExit(f"LEDs in the netlist but not on the board: {missing}")

    render = Image.open(args.render).convert("RGB")
    (X0, Y0, sx, sy), (aspect, want) = fit_mapping(render)

    # Grow the canvas upward and keep the render intact: a legend drawn over the
    # board would cover the bond-pad labels, which are part of what the picture
    # is for.
    img = Image.new("RGB", (render.size[0], render.size[1] + BANNER_H), (0, 0, 0))
    img.paste(render, (0, BANNER_H))
    Y0 += BANNER_H

    def to_px(x, y):
        return (X0 + x * sx, Y0 + y * sy)

    # Verify against the untouched render, so the black banner cannot dilute the
    # random-background rate and flatter the result.
    pts = [(X0 + pos[c["ref"]][0] * sx, (Y0 - BANNER_H) + pos[c["ref"]][1] * sy)
           for c in leds]
    hit, total, ctrl = verify_mapping(render, pts)
    print(f"mapping: {sx:.3f} px/mm, aspect {aspect:.4f} vs board {want:.4f}")
    print(f"verify : {hit}/{total} LEDs land on a pad pixel "
          f"(random background rate {ctrl:.1%})")
    if hit != total:
        raise SystemExit("mapping failed verification; refusing to draw")

    d = ImageDraw.Draw(img, "RGBA")
    f_bit = load_font(26)
    f_name = load_font(46)
    f_leg = load_font(30)
    f_legs = load_font(24, bold=False)
    f_title = load_font(54)

    # --- rings and per-bit labels -------------------------------------------
    by_group = {}
    for c in leds:
        by_group.setdefault(c["role"], []).append(c)

    for role, members in by_group.items():
        g = GROUPS[role]
        col = g["colour"]
        for c in members:
            bit = int(re.sub(r"\D", "", c["origin"]))
            px, py = to_px(*pos[c["ref"]])
            # Ring: two rings, dark halo under bright colour, so it reads on
            # both the green field and the white pad.
            d.ellipse([px - 12, py - 12, px + 12, py + 12], outline=(0, 0, 0, 200), width=6)
            d.ellipse([px - 12, py - 12, px + 12, py + 12], outline=col + (255,), width=3)

            if role == "led_P":
                text = f"P{bit} {P_FLAG_NAMES.get(bit, '?')}"
                tx, ty = px + 20, py - 14
            else:
                text = str(bit)
                tx = px + 20 if g["side"] == "right" else px - 20 - 15
                ty = py - 15
            # dark outline so small text survives a busy background
            for dx in (-2, 0, 2):
                for dy in (-2, 0, 2):
                    if dx or dy:
                        d.text((tx + dx, ty + dy), text, font=f_bit, fill=(0, 0, 0, 230))
            d.text((tx, ty), text, font=f_bit, fill=col + (255,))

    # --- column headers ------------------------------------------------------
    for role, members in by_group.items():
        if role == "led_P":
            continue
        g = GROUPS[role]
        col = g["colour"]
        xs = [to_px(*pos[c["ref"]])[0] for c in members]
        ys = [to_px(*pos[c["ref"]])[1] for c in members]
        cx, top = sum(xs) / len(xs), min(ys)
        # Leader from the column up to a header that may be splayed sideways.
        hx = cx + g["head_dx"]
        head_y = top - 78
        d.line([cx, top - 20, cx, head_y + 30], fill=col + (255,), width=4)
        if g["head_dx"]:
            d.line([cx, head_y + 30, hx, head_y + 12], fill=col + (255,), width=4)
        label = g["label"]
        w = d.textlength(label, font=f_name)
        tx, ty = hx - w / 2, head_y - 44
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    d.text((tx + dx, ty + dy), label, font=f_name, fill=(0, 0, 0, 235))
        d.text((tx, ty), label, font=f_name, fill=col + (255,))

    # --- P flag block header -------------------------------------------------
    pm = by_group.get("led_P", [])
    if pm:
        col = GROUPS["led_P"]["colour"]
        xs = [to_px(*pos[c["ref"]])[0] for c in pm]
        ys = [to_px(*pos[c["ref"]])[1] for c in pm]
        d.rounded_rectangle([min(xs) - 45, min(ys) - 45, max(xs) + 130, max(ys) + 45],
                            radius=18, outline=col + (170,), width=3)
        label = "P  status flags"
        tx, ty = min(xs) - 45, min(ys) - 92
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    d.text((tx + dx, ty + dy), label, font=f_name, fill=(0, 0, 0, 235))
        d.text((tx, ty), label, font=f_name, fill=col + (255,))

    # --- banner legend, across the top, covering nothing ---------------------
    d.text((60, 34), "REGISTER LEDs", font=f_title, fill=(255, 255, 255, 255))
    d.text((62, 104), "55 LEDs, each buffered by its own gate-tap FET.",
           font=f_legs, fill=(175, 175, 182, 255))
    d.text((62, 142), "BIT 0 IS AT THE TOP of every column; bit 7 at the bottom.",
           font=f_leg, fill=(255, 210, 90, 255))
    d.text((62, 190), "P bit 5 has no LED: the 6502 has no bit-5 flag.  "
                      "Positions from the board file, not a drawing.",
           font=f_legs, fill=(175, 175, 182, 255))

    order = ["led_A", "led_X", "led_Y", "led_S", "led_PCL", "led_PCH", "led_P"]
    desc = {
        "led_A": "accumulator", "led_X": "index X", "led_Y": "index Y",
        "led_S": "stack pointer", "led_PCL": "PC low byte",
        "led_PCH": "PC high byte", "led_P": "status flags",
    }
    cols = 4
    bx, by_, cw, ch = 1120, 60, 310, 92
    for i, role in enumerate(order):
        if role not in by_group:
            continue
        g = GROUPS[role]
        gx = bx + (i % cols) * cw
        gy = by_ + (i // cols) * ch
        d.ellipse([gx, gy + 6, gx + 28, gy + 34], outline=g["colour"] + (255,), width=5)
        d.text((gx + 46, gy), f"{g['label']}", font=f_leg, fill=g["colour"] + (255,))
        d.text((gx + 46 + max(46, d.textlength(g['label'], font=f_leg) + 14), gy + 4),
               f"{len(by_group[role])}x  {desc[role]}", font=f_legs,
               fill=(210, 210, 215, 255))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    if args.out.lower().endswith((".jpg", ".jpeg")):
        img.save(args.out, quality=88, optimize=True)
    else:
        img.save(args.out)
    print(f"wrote {args.out} ({os.path.getsize(args.out)/1024:.0f} KB, {img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    sys.exit(main())
