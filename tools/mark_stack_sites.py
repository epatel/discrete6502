#!/usr/bin/env python3
"""Where to point the FLIR for the stack-decrement contention test.

Board #1 decrements the stack pointer by 2 on every push while DEX and TXS/TSX
are correct (docs/stack-decrement-defect.md). The suspected cause is a control
line that cannot switch fully off, so S -> SB and SB -> S overlap. Contention
burns power, so the test is thermal: run `board_probe.py hold-push`, photograph
this area, then run `hold-dex` and photograph it again. A spot that appears only
under hold-push is the answer.

Two of the four parts here are the suspects and two are built-in controls --
same structure, same VCC-side site list, but DEX works on this board, so they
must stay cold in BOTH runs. Photographing all four in one frame is the point:
it makes the comparison internal to the image instead of between two sessions.

Positions come from the fabricated board and nets from the netlist; nothing here
is drawn by hand.

Usage:  python3 tools/mark_stack_sites.py [--render gen/board_top.png]
                                          [--out docs/stack-sites-marked.jpg]
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

# ref -> (net, what it does, is it a suspect)
SITES = [
    ("Q3907", "dpc4_SSB",  "S -> SB", True),
    ("Q3978", "dpc6_SBS",  "SB -> S", True),
    ("Q1944", "dpc5_SADL", "S -> ADL", True),
    ("Q552",  "dpc7_SS",   "S -> S hold", True),
    ("Q2818", "dpc2_XSB",  "X -> SB   CONTROL", False),
    ("Q3041", "dpc3_SBX",  "SB -> X   CONTROL", False),
]

# The frame to photograph, in board mm. Chosen to hold all six with margin.
CAPTURE = (48.0, 156.0, 92.0, 192.0)     # x0, y0, x1, y1

RED = (255, 70, 70)
GREEN = (80, 230, 140)
CYAN = (90, 210, 255)
WHITE = (255, 255, 255)
DIM = (150, 160, 172)
BLACK = (0, 0, 0)


def load_positions(refs):
    src = open(PCB, encoding="utf-8", errors="replace").read()
    starts = [m.start() for m in re.finditer(r"\(footprint ", src)]
    out, everything = {}, []
    for i, st in enumerate(starts):
        seg = src[st:starts[i + 1] if i + 1 < len(starts) else len(src)]
        r = re.search(r'"Reference"\s+"([A-Z]+\d+)"', seg)
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", seg)
        ly = re.search(r'\(layer "([^"]+)"', seg)
        if not (r and at and ly):
            continue
        rec = (r.group(1), float(at.group(1)), float(at.group(2)), ly.group(1))
        everything.append(rec)
        if rec[0] in refs:
            out[rec[0]] = rec
    return out, everything


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", default="gen/board_top.png")
    ap.add_argument("--out", default="docs/stack-sites-marked.jpg")
    args = ap.parse_args()

    nets = {c["ref"]: c for c in json.load(open(NETLIST))["components"]}
    refs = {r for r, _, _, _ in SITES}
    pos, everything = load_positions(refs)

    missing = refs - set(pos)
    if missing:
        raise SystemExit("not found on the board: %s" % sorted(missing))
    for ref, net, _, _ in SITES:
        c = nets[ref]
        if c["pins"]["2"] != net:
            raise SystemExit("%s pin 2 is %s, expected %s"
                             % (ref, c["pins"]["2"], net))
        if pos[ref][3] != "F.Cu":
            raise SystemExit("%s is on %s, not the top face" % (ref, pos[ref][3]))

    img = Image.open(args.render).convert("RGB")
    (X0, Y0, sx, sy), _ = fit_mapping(img)

    def px(x, y):
        return (X0 + x * sx, Y0 + y * sy)

    cx0, cy0 = px(CAPTURE[0], CAPTURE[1])
    cx1, cy1 = px(CAPTURE[2], CAPTURE[3])

    # ---- overview: the whole board, with the frame to shoot ------------------
    ov = img.copy()
    d = ImageDraw.Draw(ov)
    f = load_font(max(30, int(img.width / 70)))
    d.rectangle([cx0, cy0, cx1, cy1], outline=CYAN, width=8)
    d.text((cx1 + 18, cy0), "POINT THE FLIR HERE", font=f, fill=CYAN)
    d.text((cx1 + 18, cy0 + f.size + 8),
           "%.0f x %.0f mm" % (CAPTURE[2] - CAPTURE[0], CAPTURE[3] - CAPTURE[1]),
           font=f, fill=WHITE)
    for ref, net, _, suspect in SITES:
        _, x, y, _ = pos[ref]
        ex, ey = px(x, y)
        r = max(10, int(img.width / 200))
        d.ellipse([ex - r, ey - r, ex + r, ey + r],
                  outline=RED if suspect else GREEN, width=5)

    # ---- zoom panel ---------------------------------------------------------
    pad = 40
    crop = img.crop((int(cx0) - pad, int(cy0) - pad, int(cx1) + pad, int(cy1) + pad))
    scale = min(3.0, 2400 / crop.width)
    zoom = crop.resize((int(crop.width * scale), int(crop.height * scale)),
                       Image.LANCZOS)
    zd = ImageDraw.Draw(zoom)
    zf = load_font(34)
    zs = load_font(24)
    zt = load_font(19, bold=False)

    def zpx(x, y):
        ax, ay = px(x, y)
        return ((ax - (int(cx0) - pad)) * scale, (ay - (int(cy0) - pad)) * scale)

    # faint labels for neighbours, so you navigate by designator not by ruler
    for ref, x, y, layer in everything:
        if layer != "F.Cu" or ref in refs:
            continue
        if not (CAPTURE[0] <= x <= CAPTURE[2] and CAPTURE[1] <= y <= CAPTURE[3]):
            continue
        zx, zy = zpx(x, y)
        zd.text((zx + 7, zy - 9), ref, font=zt, fill=DIM)

    # Numbered badges, because all six sit on nearly one row and inline
    # labels overlap into mush. The key below carries the detail.
    for i, (ref, net, role, suspect) in enumerate(SITES, 1):
        _, x, y, _ = pos[ref]
        zx, zy = zpx(x, y)
        col = RED if suspect else GREEN
        r = 26
        zd.ellipse([zx - r, zy - r, zx + r, zy + r], outline=col, width=6)
        # pin 2 is the net pad: 0.89 mm left, 0.65 mm below centre (rot 0)
        p2x, p2y = zpx(x - 0.89, y + 0.65)
        zd.ellipse([p2x - 7, p2y - 7, p2x + 7, p2y + 7], outline=CYAN, width=3)
        # Badge above, unless another site sits directly above this one --
        # Q3907 is 2.8 mm below Q3041, so an upward badge would land on its
        # circle. Then go below instead.
        blocked = any(abs(pos[o][1] - x) < 2.0 and 0.5 < y - pos[o][2] < 6.0
                      for o, _, _, _ in SITES if o != ref)
        if blocked:
            by = zy + r + (34 if i % 2 else 66)
            zd.line([zx, zy + r, zx, by - 16], fill=col, width=3)
        else:
            by = zy - r - (34 if i % 2 else 66)
            zd.line([zx, zy - r, zx, by + 16], fill=col, width=3)
        bx = zx
        zd.ellipse([bx - 17, by - 17, bx + 17, by + 17], fill=col, outline=BLACK,
                   width=2)
        w = zd.textlength(str(i), font=zf)
        zd.text((bx - w / 2, by - zf.size / 2 - 3), str(i), font=zf, fill=BLACK)

    lg = ["STACK-DECREMENT CONTENTION TEST - where to photograph",
          "",
          "1  dpc4_SSB   Q3907   S -> SB        SUSPECT",
          "2  dpc6_SBS   Q3978   SB -> S        SUSPECT",
          "3  dpc5_SADL  Q1944   S -> ADL       SUSPECT",
          "4  dpc7_SS    Q552    S -> S hold    SUSPECT",
          "5  dpc2_XSB   Q2818   X -> SB        CONTROL",
          "6  dpc3_SBX   Q3041   SB -> X        CONTROL",
          "",
          "RED    suspects: the stack pointer's own control lines.",
          "       Board #1 decrements S by 2 on every push.",
          "GREEN  controls: the same structure for the X register.",
          "       DEX is correct on this board, so these must stay",
          "       cold in BOTH runs. If they heat too, the theory is wrong.",
          "CYAN   pin 2 - the net pad, if you scope instead of image.",
          "",
          "  board_probe.py hold-push   then photograph",
          "  board_probe.py hold-dex    then photograph again, same framing",
          "  board_probe.py hold-idle   neither pair exercised",
          "",
          "A spot under hold-push that is absent under hold-dex is contention.",
          "All three identical means it is a fab defect, not contention.",
          "",
          "Positions from gen/board_routed_golden.kicad_pcb; nets from",
          "gen/netlist.json. Top face, part rotation 0."]
    lh = zs.size + 9
    bh = lh * len(lg) + 26
    panel = Image.new("RGB", (zoom.width, zoom.height + bh), BLACK)
    panel.paste(zoom, (0, 0))
    pdraw = ImageDraw.Draw(panel)
    for i, line in enumerate(lg):
        col = WHITE if i == 0 else (RED if line.startswith("RED") else
                                    GREEN if line.startswith("GREEN") else
                                    CYAN if line.startswith("CYAN") else DIM)
        pdraw.text((24, zoom.height + 14 + i * lh), line,
                   font=zf if i == 0 else zs, fill=col)

    # ---- stack overview above the zoom --------------------------------------
    ow = panel.width
    ov2 = ov.resize((ow, int(ov.height * ow / ov.width)), Image.LANCZOS)
    final = Image.new("RGB", (ow, ov2.height + panel.height + 16), BLACK)
    final.paste(ov2, (0, 0))
    final.paste(panel, (0, ov2.height + 16))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    final.save(args.out, quality=88)
    print("wrote %s  (%d x %d)" % (args.out, final.width, final.height))
    print("capture frame: x %.1f..%.1f mm, y %.1f..%.1f mm (%.0f x %.0f mm)"
          % (CAPTURE[0], CAPTURE[2], CAPTURE[1], CAPTURE[3],
             CAPTURE[2] - CAPTURE[0], CAPTURE[3] - CAPTURE[1]))
    for ref, net, role, suspect in SITES:
        _, x, y, _ = pos[ref]
        print("  %-6s %-11s x=%6.2f y=%6.2f  %s%s"
              % (ref, net, x, y, role, "" if suspect else ""))


if __name__ == "__main__":
    main()
