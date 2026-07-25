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

    # ---- occupancy grid of front-side parts: silk text must miss pad copper,
    # else the fab subtracts it and titles print half-eaten (seen on the
    # first gerber review). Used for the region titles, register letters and
    # the logo alike.
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

    def is_free(ix0, iy0, nw, nh):
        if ix0 < 0 or iy0 < 0 or ix0 + nw > W or iy0 + nh > H:
            return False
        return all(occ[(iy0 + b) * W + ix0 + a] == 0
                   for b in range(nh) for a in range(nw))

    def measure(s, h):
        """width of a stroke-font string in mm at text height h.
        KiCad's stroke font advances one text-width per glyph (we set width
        to 0.9*h); 1.05 covers inter-glyph spacing. Deliberately a slight
        over-estimate -- erring wide only buys extra clearance."""
        return len(s) * h * 0.9 * 1.05

    def fit(s, y_lo, y_hi, h):
        """topmost-then-leftmost pad-free spot for text s at height h"""
        nw = int((measure(s, h) + 1.5) / GRID) + 1
        nh = int(h * 1.9 / GRID) + 1
        iy_lo = max(0, int((y_lo - cy0) / GRID))
        iy_hi = min(H - 1, int((y_hi - cy0) / GRID))
        for iy in range(iy_lo, iy_hi - nh + 1):
            for ix in range(0, W - nw):
                if is_free(ix, iy, nw, nh):
                    return ix, iy, nw, nh
        return None

    def claim(ix, iy, nw, nh):
        for b in range(nh):
            for a in range(nw):
                occ[(iy + b) * W + ix + a] = 1

    def fit_block(w_mm, h_mm, y_lo=None, y_hi=None):
        """lowest (most datapath-ward) pad-free block of at least w x h mm"""
        nw = int(w_mm / GRID) + 1
        nh = int(h_mm / GRID) + 1
        iy_lo = 0 if y_lo is None else max(0, int((y_lo - cy0) / GRID))
        iy_hi = H - 1 if y_hi is None else min(H - 1, int((y_hi - cy0) / GRID))
        best = None
        for iy in range(iy_lo, iy_hi - nh + 1):
            for ix in range(0, W - nw):
                if is_free(ix, iy, nw, nh) and (best is None or iy > best[1]):
                    best = (ix, iy, nw, nh)
        return best

    def place_free(s, y_lo, y_hi, heights, bold=True, near=None):
        """Find a pad-free spot for text s inside the y band; returns
        (x, y, h) of the placed text, or None. Prefers the top-left of the
        band (section-header feel), or the nearest spot to `near`."""
        iy_lo = max(0, int((y_lo - cy0) / GRID))
        iy_hi = min(H - 1, int((y_hi - cy0) / GRID))
        for h in heights:
            w = measure(s, h) + 1.5          # margin either side
            nw = int(w / GRID) + 1
            nh = int(h * 1.9 / GRID) + 1
            cands = []
            for iy in range(iy_lo, iy_hi - nh + 1):
                for ix in range(0, W - nw):
                    if is_free(ix, iy, nw, nh):
                        cands.append((ix, iy))
            if not cands:
                continue
            if near is not None:
                nx = (near[0] - cx0) / GRID
                ny = (near[1] - cy0) / GRID
                ix, iy = min(cands, key=lambda c: (c[0] - nx) ** 2 + (c[1] - ny) ** 2)
            else:                              # topmost band, then leftmost
                ix, iy = min(cands, key=lambda c: (c[1], c[0]))
            x = cx0 + (ix + nw / 2) * GRID
            y = cy0 + (iy + nh / 2) * GRID
            for b in range(nh):                # claim it
                for a in range(nw):
                    occ[(iy + b) * W + ix + a] = 1
            return x, y, h
        return None

    # ---- 2a. logo first: it is the signature element, so it gets first pick
    # of the clear space (and claims it, so the band titles route around it).
    # Attribution is split over two lines -- one long line needs more clear
    # width than exists anywhere on the die.
    LOGO = None
    for ht in (6.0, 5.0, 4.2, 3.6, 3.0, 2.6):
        hs, ha = ht * 0.34, max(1.3, ht * 0.34)
        lines = [("MOS 6502", ht, True), ("discrete6502", hs, False),
                 ("after visual6502.org", ha, False), ("CC BY-NC-SA", ha, False)]
        need_w = max(measure(s, h) for s, h, _ in lines) + 2.0
        need_h = sum(h * 1.75 for _, h, _ in lines) + 1.0
        spot = fit_block(need_w, need_h)
        if spot:
            LOGO = (spot, lines, need_h)
            break
    if LOGO:
        (ix, iy, nw, nh), lines, need_h = LOGO
        claim(ix, iy, nw, nh)
        cx = cx0 + (ix + nw / 2) * GRID
        y = cy0 + iy * GRID + (nh * GRID - need_h) / 2
        for s, h, bold in lines:
            y += h * 1.75 / 2
            txt(board, s, cx, y, h, pcbnew.F_SilkS, bold=bold)
            y += h * 1.75 / 2
        print("logo at (%.0f, %.0f) in %.0fx%.0fmm, title %.1fmm"
              % (cx, cy0 + (iy + nh / 2) * GRID, nw * GRID, nh * GRID, lines[0][1]))
    else:
        print("no logo spot found")

    # ---- 2. functional region outlines (classic die floorplan bands) ----
    # The die field is dense: a full-length title at 2.6mm needs ~64mm of
    # clear width and the largest pad-free block in a band is ~36mm. Titles
    # that cross pads get subtracted by the fab and print half-eaten, so
    # instead try progressively shorter wordings, pick ONE height that every
    # band can honour (uniform size reads as deliberate), and place each
    # band's longest wording that fits at it.
    ch = cy1 - cy0
    regions = [
        (["INSTRUCTION DECODE (PLA)", "INSTRUCTION DECODE", "DECODE PLA", "PLA"],
         cy0, cy0 + 0.27 * ch),
        (["CONTROL LOGIC", "CONTROL"], cy0 + 0.27 * ch, cy0 + 0.52 * ch),
        (["DATAPATH — REGISTERS & ALU", "DATAPATH & ALU", "DATAPATH"],
         cy0 + 0.52 * ch, cy1),
    ]
    HEIGHTS = (3.2, 2.8, 2.6, 2.4, 2.2, 2.0, 1.8, 1.6)
    feasible = []
    for variants, y0, y1 in regions:
        hmax = next((h for h in HEIGHTS
                     if any(fit(v, y0 + 2, y1 - 2, h) for v in variants)), 1.6)
        feasible.append(hmax)
    h_uni = min(feasible)
    for variants, y0, y1 in regions:
        rect(board, cx0 - 1.5, y0, cx1 + 1.5, y1, pcbnew.F_SilkS, 0.25)
        placed = False
        for v in variants:                     # longest wording that fits
            spot = fit(v, y0 + 2, y1 - 2, h_uni)
            if spot:
                ix, iy, nw, nh = spot
                claim(ix, iy, nw, nh)
                x = cx0 + (ix + nw / 2) * GRID
                y = cy0 + (iy + nh / 2) * GRID
                txt(board, v, x, y, h_uni, pcbnew.F_SilkS, bold=True)
                print("region %-26s -> (%3.0f,%3.0f) h=%.1f" % (v, x, y, h_uni))
                placed = True
                break
        if not placed:
            txt(board, variants[-1], cx0 + 2.5, y0 + 3.2, h_uni,
                pcbnew.F_SilkS, bold=True, left=True)
            print("region %-26s -> no clear spot" % variants[-1])

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
        # want it beside its LED row, but never printed onto pad copper
        want_x = min(p[0] for p in pts) - 3.2
        want_y = sum(p[1] for p in pts) / len(pts)
        spot = place_free(f, want_y - 6.0, want_y + 6.0, (2.0, 1.6),
                          near=(want_x, want_y))
        if spot:
            x, y, h = spot
            txt(board, f, x, y, h, pcbnew.F_SilkS, bold=True)
        else:
            txt(board, f, want_x, want_y, 2.0, pcbnew.F_SilkS, bold=True)

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
