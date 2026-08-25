#!/usr/bin/env python3
"""Where the sixteen address-path rework sites are, so you can find them by eye.

The 2026-08-25 thermal finding: adh3..adh7 run at ~80 C on board #1 while it
executes real code. tools/contention_duty.py measured why -- adh1/3/5/6/7 contend
35% of the time under a real program and 0.3% under a NOP free-run, which is the
condition the 2026-08-24 FLIR image was taken in and therefore why it saw
nothing. adh0/2/4 and adl0/1/2 contend under both.

The fix is the operation already proven on the dor eight: 10k in series with
pin 3. This draws the map for it -- an overview plus a zoomed panel per cluster,
because the sixteen sit in two groups 40 mm apart and neither is findable by
counting.

Everything is derived, never drawn: positions from the fabricated board, roles
and driven nets from the netlist, duty from contention_duty.py. Neighbouring
designators are printed inside the zoom panels so you can navigate to a part
instead of measuring to it.

Usage:  python3 tools/mark_rework_adh.py [--render gen/board_top.png]
                                         [--out docs/rework-adh-marked.jpg]
"""
import argparse
import json
import os
import re
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mark_leds import fit_mapping, load_font  # noqa: E402

NETLIST = "gen/netlist.json"
PCB = "gen/board_routed_golden.kicad_pcb"

# net -> (duty under real code, duty under NOP free-run), from contention_duty.py
DUTY = {
    "adh0": (33.7, 14.3), "adh1": (35.0, 0.3), "adh2": (35.3, 48.0),
    "adh3": (35.0, 0.3), "adh4": (35.3, 48.0), "adh5": (35.0, 0.3),
    "adh6": (35.0, 0.3), "adh7": (35.0, 0.3),
    "adl0": (19.3, 24.7), "adl1": (20.0, 25.7), "adl2": (39.0, 24.0),
    "adl3": (40.7, 23.0), "adl4": (15.3, 25.3), "adl5": (37.0, 21.7),
    "adl6": (45.7, 34.3), "adl7": (45.7, 34.3),
}
# Measured hot with a FLIR on board #1, 2026-08-25, at ~80 C.
CONFIRMED_HOT = {"adh3", "adh4", "adh5", "adh6", "adh7",
                 "adl4", "adl5", "adl6", "adl7"}

RED = (255, 70, 70)
AMBER = (255, 176, 46)
GREEN = (80, 230, 140)
WHITE = (255, 255, 255)
DIM = (150, 160, 172)


def channel_net(c):
    """The channel net is whichever of pins 2/3 is not a rail -- the two roles
    use opposite conventions, so asking which pin is the rail is the only safe
    way to read it."""
    a, b = c["pins"]["2"], c["pins"]["3"]
    return b if a in ("vss", "vcc") else a


def load_positions(pcb_path):
    pos, layer = {}, {}
    txt = open(pcb_path, errors="ignore").read()
    for b in txt.split("(footprint ")[1:]:
        a = re.search(r"\(at ([-\d.]+) ([-\d.]+)", b)
        r = re.search(r'"Reference"\s+"([^"]+)"', b)
        l = re.search(r'\(layer "([^"]+)"', b)
        if a and r:
            pos[r.group(1)] = (float(a.group(1)), float(a.group(2)))
            layer[r.group(1)] = l.group(1) if l else "?"
    return pos, layer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", default="gen/board_top.png")
    ap.add_argument("--out", default="docs/rework-adh-marked.jpg")
    args = ap.parse_args()

    nl = json.load(open(NETLIST))
    pos, layer = load_positions(PCB)

    targets = []
    for c in nl["components"]:
        if c.get("role") != "vcc_side":
            continue
        net = channel_net(c)
        if net in DUTY and c["ref"] in pos:
            x, y = pos[c["ref"]]
            targets.append({"ref": c["ref"], "net": net, "x": x, "y": y,
                            "duty": DUTY[net], "side": layer[c["ref"]]})
    targets.sort(key=lambda t: t["net"])
    if len(targets) != len(DUTY):
        raise SystemExit("found %d targets, expected %d" % (len(targets), len(DUTY)))
    for t in targets:
        if t["side"] != "F.Cu":
            raise SystemExit("%s is on %s, not the top face" % (t["ref"], t["side"]))

    img = Image.open(args.render).convert("RGB")
    (X0, Y0, sx, sy), _ = fit_mapping(img)

    def px(x, y):
        return (X0 + x * sx, Y0 + y * sy)

    # ---- overview -----------------------------------------------------------
    ov = img.copy()
    d = ImageDraw.Draw(ov)
    f = load_font(max(22, int(img.width / 90)))
    fs = load_font(max(16, int(img.width / 130)))
    r = max(14, int(img.width / 150))
    for t in targets:
        cx, cy = px(t["x"], t["y"])
        col = RED if t["net"] in CONFIRMED_HOT else AMBER
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=5)
        d.text((cx + r + 6, cy - r - 2), t["net"], font=f, fill=col)
        d.text((cx + r + 6, cy + 4), t["ref"], font=fs, fill=WHITE)

    lg = ["ADDRESS-PATH REWORK SITES - 10k in series with pin 3",
          "",
          "RED    measured hottest on board #1 (FLIR, 2026-08-25)",
          "AMBER  same defect, not yet confirmed hot",
          "",
          "All 16 are on the TOP face. Same operation as the dor eight.",
          "adl6/adl7 are the busiest sites on the whole board at 45.7%%.",
          "adh1/3/5/6/7 contend 35%% under real code and 0.3%% under a NOP",
          "free-run -- which is why the 2026-08-24 thermal test saw nothing."]
    bw = max(d.textlength(s, font=f) for s in lg) + 40
    bh = len(lg) * (f.size + 9) + 26
    d.rectangle([20, 20, 20 + bw, 20 + bh], fill=(0, 0, 0))
    for i, s in enumerate(lg):
        d.text((40, 34 + i * (f.size + 9)), s, font=f,
               fill=RED if s.startswith("RED") else AMBER if s.startswith("AMBER") else WHITE)

    # ---- zoom panels, one per cluster --------------------------------------
    xs = sorted(t["x"] for t in targets)
    split = 185.0  # the two groups sit either side of this; verified below
    groups = [[t for t in targets if t["x"] < split],
              [t for t in targets if t["x"] >= split]]
    if not all(groups):
        raise SystemExit("cluster split at %.0f mm did not separate them" % split)

    all_refs = [(r_, p) for r_, p in pos.items() if layer.get(r_) == "F.Cu"]
    panels = []
    for g in groups:
        x0 = min(t["x"] for t in g) - 12
        x1 = max(t["x"] for t in g) + 12
        y0 = min(t["y"] for t in g) - 12
        y1 = max(t["y"] for t in g) + 12
        a, b = px(x0, y0)
        c_, e = px(x1, y1)
        crop = img.crop((int(a), int(b), int(c_), int(e)))
        scale = min(3.0, 1500.0 / max(1, crop.width))
        crop = crop.resize((int(crop.width * scale), int(crop.height * scale)),
                           Image.LANCZOS)
        pd = ImageDraw.Draw(crop)
        pf = load_font(26)
        pfs = load_font(19)

        def ppx(x, y):
            return ((X0 + x * sx - a) * scale, (Y0 + y * sy - b) * scale)

        # neighbouring designators, so a part can be navigated to
        for ref, (rx, ry) in all_refs:
            if x0 <= rx <= x1 and y0 <= ry <= y1 and not ref.startswith("TP"):
                if any(t["ref"] == ref for t in g):
                    continue
                qx, qy = ppx(rx, ry)
                pd.text((qx + 5, qy - 9), ref, font=pfs, fill=DIM)
        pr = int(20 * scale)
        for t in g:
            qx, qy = ppx(t["x"], t["y"])
            col = RED if t["net"] in CONFIRMED_HOT else AMBER
            pd.ellipse([qx - pr, qy - pr, qx + pr, qy + pr], outline=col, width=6)
            pd.text((qx + pr + 8, qy - pr - 4),
                    "%s  %s" % (t["net"], t["ref"]), font=pf, fill=col)
            pd.text((qx + pr + 8, qy + 4),
                    "duty %.0f%% run / %.1f%% nop" % t["duty"], font=pfs, fill=WHITE)
        title = "x %.0f-%.0f mm, y %.0f-%.0f mm   (grey = neighbouring designators)" % (
            x0, y0, x1, y1)
        pd.rectangle([0, 0, crop.width, 40], fill=(0, 0, 0))
        pd.text((12, 8), title, font=pf, fill=WHITE)
        panels.append(crop)

    # ---- compose ------------------------------------------------------------
    ow = 1500
    ov2 = ov.resize((ow, int(ov.height * ow / ov.width)), Image.LANCZOS)
    pw = max(p.width for p in panels)
    total_h = ov2.height + sum(p.height + 18 for p in panels)
    sheet = Image.new("RGB", (max(ow, pw), total_h), (0, 0, 0))
    sheet.paste(ov2, (0, 0))
    y = ov2.height
    for p in panels:
        y += 18
        sheet.paste(p, (0, y))
        y += p.height

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    sheet.save(args.out, quality=88)
    print("wrote %s  (%dx%d)" % (args.out, sheet.width, sheet.height))
    for t in targets:
        print("  %-5s %-7s x %7.2f  y %7.2f   duty %.1f%% run / %.1f%% nop%s"
              % (t["net"], t["ref"], t["x"], t["y"], t["duty"][0], t["duty"][1],
                 "   HOT" if t["net"] in CONFIRMED_HOT else ""))


if __name__ == "__main__":
    main()
