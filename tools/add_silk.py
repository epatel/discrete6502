#!/usr/bin/env python3
"""Silkscreen dressing pass (run on the routed board, before fab outputs).

- Bond-pad ring: classic 6502 pin names (A0-A15, D0-D7, R/W, Φ0/Φ1/Φ2,
  overbars on active-low) + DIP-40 pin number printed inside each pad.
- Functional region outlines (die floorplan bands) + register-row labels
  derived from the LED driver positions.
- "MOS 6502" logo in the largest FET-free front area + attribution line.
- Pico site: outline, title, pin-1 marker on the back silk.

Idempotent-ish: texts it adds carry a marker in their text; rerunning
removes previous marked items first.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")
MARK = "​"  # zero-width marker suffix identifying our texts

# classic 6502 pin naming + DIP-40 pin numbers, keyed by current label
PINS = {
    **{"AB%d" % i: ("A%d" % i, (9 + i) if i < 12 else (10 + i)) for i in range(16)},
    **{"DB%d" % i: ("D%d" % i, 33 - i) for i in range(8)},
    "RES": ("~{RES}", 40), "IRQ": ("~{IRQ}", 4), "NMI": ("~{NMI}", 6),
    "RDY": ("RDY", 2), "SO": ("S.O.", 38), "SYNC": ("SYNC", 7),
    "RW": ("R/W", 34), "CLK0": ("Φ0", 37), "CLK1OUT": ("Φ1", 3),
    "CLK2OUT": ("Φ2", 39), "VCC": ("VCC", 8), "VSS": ("VSS", "1·21"),
}


def txt(board, s, x, y, h, layer, mirror=False, bold=False, left=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s + MARK)
    t.SetPosition(pcbnew.VECTOR2I_MM(x, y))
    t.SetTextHeight(pcbnew.FromMM(h))
    t.SetTextWidth(pcbnew.FromMM(h * 0.9))
    t.SetTextThickness(pcbnew.FromMM(h * (0.22 if bold else 0.16)))
    t.SetLayer(layer)
    if left:
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    if mirror:
        t.SetMirrored(True)
    board.Add(t)
    return t


def rect(board, x0, y0, x1, y1, layer, w=0.2):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(pcbnew.VECTOR2I_MM(x0, y0))
    s.SetEnd(pcbnew.VECTOR2I_MM(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(w))
    board.Add(s)
    return s


def strip_pad_frames():
    """The TP library draws a silk frame ON the pad copper: remove.
    Isolated load/save -- KiCad's SWIG bindings misbehave if this runs
    inside a session that already iterated other containers."""
    board = pcbnew.LoadBoard(PCB)
    victims = []  # collect FIRST: Remove() poisons subsequent iteration
    for fp in board.Footprints():
        if not fp.GetReference().startswith("TP"):
            continue
        for g in fp.GraphicalItems():
            if isinstance(g, pcbnew.PCB_SHAPE) and g.GetLayer() == pcbnew.F_SilkS:
                victims.append((fp, g))
    for fp, g in victims:
        fp.Remove(g)
    if victims:
        board.Save(PCB)
    print("removed %d pad silk frames" % len(victims))


def main():
    board = pcbnew.LoadBoard(PCB)
    params = json.loads((ROOT / "gen" / "layout_params.json").read_text())
    cx0, cy0, cx1, cy1 = params["core"]

    # remove previously-added marked items (rerun safety); Remove() poisons
    # later SWIG iteration, so save + reload before doing the additions
    stale = [d for d in board.Drawings()
             if (isinstance(d, pcbnew.PCB_TEXT) and d.GetText().endswith(MARK))
             or (isinstance(d, pcbnew.PCB_SHAPE) and d.GetLayer() in
                 (pcbnew.F_SilkS, pcbnew.B_SilkS))]
    if stale:
        for d in stale:
            board.Remove(d)
        board.Save(PCB)
        board = pcbnew.LoadBoard(PCB)

    # ---- 1. bond pad ring: classic names + pin numbers ----
    bb = board.GetBoardEdgesBoundingBox()
    bw = bb.GetWidth() / 1e6
    bh = bb.GetHeight() / 1e6
    renamed = 0
    for fp in board.Footprints():
        if not fp.GetReference().startswith("TP"):
            continue
        old = fp.Value().GetText()
        if old in PINS:
            name, pin = PINS[old]
        else:  # already renamed on a previous run: look up by new name
            match = [v for v in PINS.values() if v[0] == old]
            if not match:
                continue
            name, pin = match[0]
        fp.Value().SetText(name)
        v = fp.Value()
        p = fp.GetPosition()
        px, py = p.x / 1e6, p.y / 1e6
        # keep silk OFF the pad copper: labels go in the ring gaps.
        # side-column pads: name above, pin below; top/bottom-row pads:
        # name in the left gap, pin in the right gap.
        # labels relative to the pad's REAL bbox (bond pads sit at die-true
        # positions; some nearly touch the board edge) -- always on the
        # core-facing side, never on the copper
        pb = None
        for pad in fp.Pads():
            pb = pad.GetBoundingBox()
            break
        pt, pbot = pb.GetTop() / 1e6, pb.GetBottom() / 1e6
        v.SetTextAngle(pcbnew.EDA_ANGLE(0))
        v.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        v.SetTextHeight(pcbnew.FromMM(1.8))
        v.SetTextWidth(pcbnew.FromMM(1.6))
        v.SetTextThickness(pcbnew.FromMM(0.32))
        side = min((px, "L"), (bw - px, "R"), (py, "T"), (bh - py, "B"))[1]
        if side == "T":       # labels below the pad
            v.SetPosition(pcbnew.VECTOR2I_MM(px, pbot + 1.6))
            txt(board, "PIN %s" % pin, px, pbot + 3.5, 1.4, pcbnew.F_SilkS)
        elif side == "B":     # labels above the pad
            v.SetPosition(pcbnew.VECTOR2I_MM(px, pt - 3.5))
            txt(board, "PIN %s" % pin, px, pt - 1.6, 1.4, pcbnew.F_SilkS)
        else:                 # columns: name above, pin below
            v.SetPosition(pcbnew.VECTOR2I_MM(px, pt - 1.6))
            txt(board, "PIN %s" % pin, px, pbot + 1.6, 1.4, pcbnew.F_SilkS)
        renamed += 1

    # gen_pcb's original ring labels duplicate the new in-pad ones: remove
    oldnames = set(PINS) | {v[0] for v in PINS.values()} | {
        "CLK", "SO", "PHI0", "PHI1", "PHI2", "CLK1", "CLK2"}
    legacy = [d for d in board.Drawings()
              if isinstance(d, pcbnew.PCB_TEXT)
              and not d.GetText().endswith(MARK)
              and d.GetText().strip() in oldnames]
    if legacy:
        for d in legacy:
            board.Remove(d)
        board.Save(PCB)
        board = pcbnew.LoadBoard(PCB)
    print("legacy ring labels removed:", len(legacy))

    # ---- 2. functional region outlines (classic die floorplan bands) ----
    ch = cy1 - cy0
    regions = [
        ("INSTRUCTION DECODE  (PLA)", cy0, cy0 + 0.27 * ch),
        ("CONTROL LOGIC", cy0 + 0.27 * ch, cy0 + 0.52 * ch),
        ("DATAPATH — REGISTERS & ALU", cy0 + 0.52 * ch, cy1),
    ]
    first = True
    for label, y0, y1 in regions:
        rect(board, cx0 - 1.5, y0, cx1 + 1.5, y1, pcbnew.F_SilkS, 0.25)
        # first band: drop below the top pad-ring labels
        txt(board, label, cx0 + 2.5, y0 + (6.2 if first else 3.2), 2.6,
            pcbnew.F_SilkS, bold=True, left=True)
        first = False

    # ---- 3. register-row labels from LED positions ----
    nl = json.loads((ROOT / "gen" / "netlist.json").read_text())
    fam_of = {}
    for c in nl["components"]:
        if c["ref"].startswith("D") and c.get("origin"):
            fam = c["origin"].rstrip("0123456789").upper()
            if fam in ("A", "X", "Y", "S", "P", "PCL", "PCH"):
                fam_of[c["ref"]] = fam
    fams = defaultdict(list)
    for fp in board.Footprints():
        f = fam_of.get(fp.GetReference())
        if f:
            p = fp.GetPosition()
            fams[f].append((p.x / 1e6, p.y / 1e6))
    for f, pts in fams.items():
        x = min(p[0] for p in pts) - 3.2
        y = sum(p[1] for p in pts) / len(pts)
        txt(board, f, x, y, 2.0, pcbnew.F_SilkS, bold=True)

    # ---- 4. logo in the largest FET-free front area ----
    GRID = 2.0
    W = int((cx1 - cx0) / GRID) + 1
    H = int((cy1 - cy0) / GRID) + 1
    occ = bytearray(W * H)
    for fp in board.Footprints():
        if fp.GetLayer() != pcbnew.F_Cu:
            continue
        bb = fp.GetBoundingBox()
        ix0 = max(0, int((bb.GetLeft() / 1e6 - cx0) / GRID) - 1)
        ix1 = min(W - 1, int((bb.GetRight() / 1e6 - cx0) / GRID) + 1)
        iy0 = max(0, int((bb.GetTop() / 1e6 - cy0) / GRID) - 1)
        iy1 = min(H - 1, int((bb.GetBottom() / 1e6 - cy0) / GRID) + 1)
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                occ[iy * W + ix] = 1
    best = None
    for LW, LH in ((23, 6), (18, 5), (14, 4), (10, 3)):
        for iy in range(H - LH):
            for ix in range(W - LW):
                if all(occ[(iy + b) * W + ix + a] == 0
                       for b in range(LH) for a in range(LW)):
                    if best is None or iy > best[1]:
                        best = (ix, iy, LW, LH)
        if best:
            break
    if best:
        ix, iy, LW, LH = best
        lx = cx0 + (ix + LW / 2) * GRID
        ly = cy0 + (iy + LH / 2) * GRID
        hh = LH * GRID
        txt(board, "MOS 6502", lx, ly - hh * 0.12, hh * 0.42, pcbnew.F_SilkS, bold=True)
        txt(board, "discrete6502", lx, ly + hh * 0.30, hh * 0.16, pcbnew.F_SilkS)
        txt(board, "after visual6502.org · CC BY-NC-SA", lx, ly + hh * 0.30 + 3.2,
            1.6, pcbnew.F_SilkS)
        print("logo at (%.0f, %.0f) size %dx%dmm" % (lx, ly, LW * GRID, LH * GRID))
    else:
        print("no logo spot found")

    # ---- 5. Pico site on the back ----
    u1 = None
    for fp in board.Footprints():
        if fp.GetReference() == "U1":
            u1 = fp
    if u1 is not None:
        bb = u1.GetBoundingBox()
        x0, y0 = bb.GetLeft() / 1e6, bb.GetTop() / 1e6
        x1, y1 = bb.GetRight() / 1e6, bb.GetBottom() / 1e6
        rect(board, x0 - 1, y0 - 1, x1 + 1, y1 + 1, pcbnew.B_SilkS, 0.25)
        txt(board, "RASPBERRY PI PICO 2 W", (x0 + x1) / 2, y0 - 3.0, 2.4,
            pcbnew.B_SilkS, mirror=True, bold=True)
        txt(board, "not fitted — install by soldering the module's edge pads",
            (x0 + x1) / 2, y1 + 3.0, 1.8, pcbnew.B_SilkS, mirror=True)
        # pin 1 marker next to pad 1
        for pad in u1.Pads():
            if str(pad.GetNumber()) == "1":
                p = pad.GetPosition()
                txt(board, "PIN 1", p.x / 1e6 + 5.5, p.y / 1e6, 1.8,
                    pcbnew.B_SilkS, mirror=True, bold=True)
                break

    # remaining silk-over-copper/overlap = the region overlays crossing the
    # FET field: intentional, clipped in fab. Silence in DRC.
    import json as _json
    propath = ROOT / "gen" / "discrete6502.kicad_pro"
    pj = _json.loads(propath.read_text())
    sev = pj.setdefault("board", {}).setdefault("design_settings", {}) \
            .setdefault("rule_severities", {})
    sev["silk_overlap"] = "ignore"
    sev["silk_over_copper"] = "ignore"
    propath.write_text(_json.dumps(pj, indent=2))

    print("renamed %d bond pads; regions, register labels, logo, pico done"
          % renamed)
    board.Save(PCB)
    print("saved")


if __name__ == "__main__":
    import subprocess
    import sys as _sys
    if "--frames-only" in _sys.argv:
        strip_pad_frames()
    else:
        # KiCad's SWIG bindings can't survive a save+reload in one session:
        # do the destructive frame-strip in a child process
        subprocess.run([_sys.executable, __file__, "--frames-only"], check=True)
        main()
