#!/usr/bin/env python3
"""Mark the VCC-side FETs — the driver-contention sites — on the board render.

Produces docs/hotsites-marked.jpg: the top-face render with every enhancement-mode
VCC-side FET ringed and grouped by what it drives. This is the map for a thermal
sweep, when "find the hot FETs" has to become "check these, in this order".

Why these parts: the netlist transform preserved topology but not device ratios.
The 1,018 depletion loads correctly became 10k resistors, but 164 VCC-side FETs
kept the same BSS138W as their pull-down — a 1:1 ratio where ratioed NMOS needs a
weak load. A contended site burns ~0.9 W at 5 V in a package rated ~0.3 W. See
"Driver contention" in project-plan.md.

Two facts narrow the search, and both come from the netlist rather than a guess:

  - 22 of the 164 have NO pull-down on their net, so they can never contend and
    can never be hot. They are drawn hollow.
  - the 8 gated by dor0..dor7 are the sites the rev A hand rework fixes. On a
    reworked board they must be COLD. A hot one there means the rework did not
    take, which is a different fault from the ratio defect.

Grouping reflects workload. Under a NOP free-run the address increments every
cycle, so the 32 address-path sites (ab/adh/adl) switch maximally and are the
prime suspects; unclocked, the contended set is instead whatever the undefined
dynamic nodes happen to select. Filming both states and diffing them is what
turns "something is hot" into "this net is contending".

Everything comes from the board and the netlist, never from a drawing:

  - FET positions from gen/board_routed_golden.kicad_pcb (footprint origins)
  - role, driven net and gate from gen/netlist.json
  - the mm-to-pixel mapping is reused from tools/mark_leds.py, which fits it on
    the render's own board extents and verifies it lands on real pad pixels

Usage:  python3 tools/mark_hotsites.py [--render gen/board_top.png]
                                       [--out docs/hotsites-marked.jpg]
"""

import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mark_leds import fit_mapping, load_font, parse_footprints  # noqa: E402

NETLIST = "gen/netlist.json"
PCB = "gen/board_routed_golden.kicad_pcb"

# Ordered most-suspect first; the first matching rule wins.
GROUPS = [
    ("rework", "reworked (dor0-7) - must be COLD", (0, 210, 120)),
    ("addr", "address path (ab/adh/adl) - NOP free-run worst case", (255, 70, 60)),
    ("data", "data path (db/idb)", (255, 170, 0)),
    ("clock", "clock (cclk/cp1/clk)", (190, 130, 255)),
    ("other", "other internal nodes", (0, 190, 255)),
]
GROUP_COLOUR = {k: c for k, _, c in GROUPS}


def classify(comp, has_pulldown):
    """Bucket one VCC-side FET by what it drives. Gate decides the rework case."""
    net = comp["pins"]["2"]
    if comp["pins"]["1"].startswith("dor"):
        return "rework"
    if net.startswith(("ab", "adh", "adl")):
        return "addr"
    if net.startswith(("db", "idb")):
        return "data"
    if net.startswith(("cclk", "cp", "clk", "clock")):
        return "clock"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", default="gen/board_top.png")
    ap.add_argument("--out", default="docs/hotsites-marked.jpg")
    ap.add_argument("--pcb", default=PCB)
    ap.add_argument("--netlist", default=NETLIST)
    args = ap.parse_args()

    comps = json.load(open(args.netlist))["components"]

    # A site can only contend if something pulls its net down. Anything else is
    # a load with nothing to fight, so it cannot dissipate and cannot be hot.
    #
    # The channel net is whichever of pins 2/3 is not a rail -- the two roles use
    # opposite conventions (pull-down: pin2=vss, pin3=net; VCC-side: pin2=net,
    # pin3=vcc), so asking "which pin is the rail" is the only safe way to read it.
    def channel_net(c):
        a, b = c["pins"]["2"], c["pins"]["3"]
        return b if a in ("vss", "vcc") else a

    pulldown_nets = {
        channel_net(c) for c in comps if c.get("role") == "pulldown"
    }

    sites = [c for c in comps if c.get("role") == "vcc_side"]
    if not sites:
        sys.exit("no vcc_side FETs in the netlist -- wrong file?")

    pos = parse_footprints(args.pcb)
    render = Image.open(args.render).convert("RGB")
    (X0, Y0, sx, sy), _ = fit_mapping(render)
    draw = ImageDraw.Draw(render, "RGBA")

    counts, missing, contend = {}, [], 0
    for c in sites:
        ref = c["ref"]
        if ref not in pos:
            missing.append(ref)
            continue
        grp = classify(c, channel_net(c) in pulldown_nets)
        live = channel_net(c) in pulldown_nets
        contend += live
        counts[grp] = counts.get(grp, 0) + 1

        x, y = pos[ref]
        px, py = X0 + x * sx, Y0 + y * sy
        col = GROUP_COLOUR[grp]
        r = 26
        if live:
            draw.ellipse((px - r, py - r, px + r, py + r), outline=col + (255,), width=7)
        else:
            # cannot contend: hollow, thin, so it reads as "ignore this one"
            draw.ellipse((px - r, py - r, px + r, py + r), outline=col + (110,), width=3)

    font = load_font(46)
    small = load_font(34)
    pad, lh = 34, 62
    box_h = lh * (len(GROUPS) + 3) + pad
    draw.rectangle((30, 30, 1180, 30 + box_h), fill=(0, 0, 0, 205))
    draw.text((60, 58), "VCC-side FETs - contention / thermal map", font=font, fill=(255, 255, 255))
    yy = 58 + lh
    for key, label, col in GROUPS:
        n = counts.get(key, 0)
        if not n:
            continue
        draw.ellipse((66, yy + 8, 96, yy + 38), outline=col + (255,), width=6)
        draw.text((120, yy + 4), "%-3d %s" % (n, label), font=small, fill=(235, 235, 235))
        yy += lh
    draw.text((60, yy + 8),
              "thick = has a pull-down, can contend (%d)" % contend,
              font=small, fill=(235, 235, 235))
    draw.text((60, yy + 8 + lh),
              "thin  = no pull-down, cannot be hot (%d)" % (len(sites) - len(missing) - contend),
              font=small, fill=(170, 170, 170))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    render.save(args.out, quality=88)

    print("sites marked : %d of %d" % (sum(counts.values()), len(sites)))
    for key, label, _ in GROUPS:
        if counts.get(key):
            print("   %-7s %3d  %s" % (key, counts[key], label))
    print("can contend  : %d   (cannot: %d)" % (contend, sum(counts.values()) - contend))
    if missing:
        print("NOT PLACED   : %d (%s)" % (len(missing), ", ".join(missing[:8])))
    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
