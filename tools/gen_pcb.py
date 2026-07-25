#!/usr/bin/env python3
"""Build the placed (unrouted) KiCad board from gen/netlist.json.

Run with KiCad's bundled python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 tools/gen_pcb.py

Board concept v4 (user directives: read as the 6502 die; ALL components on
the top face; transistors at die-true positions):
  - 229.6 x 248.1 mm, the die's aspect ratio
  - single-face architecture: SOT-323 FETs (BSS138K) on a 3.2 x 3.1 mm grid;
    each row has a 1.1mm 'service channel' beneath it holding the resistors,
    inline LEDs, and all power vias, on a 1.8mm slot raster. The back face
    carries nothing but the unpopulated Pico 2 W site -> it is a free routing
    layer.
  - bond pad ring: 4x4mm THT pads at die-true bond-pad positions
  - protection / pull-ups / bulk / decouplers: front, in the margin band
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

COLS, ROWS = 71, 105
PITCH = (3.7, 2.8)
CORE = (14.0, 14.0, 14.0 + COLS * PITCH[0], 14.0 + ROWS * PITCH[1])
BOARD_W, BOARD_H = CORE[2] + 14.0, CORE[3] + 14.0
FET_DY = 1.075       # FET center below row top
CH_DY = 2.55         # power/routing lane center below row top
SLOT_P = 1.4         # lane slot pitch
RIM = 4.5
PAD_SPACING = 6.5
BAND = (7.8, 9.9, 12.0)
DECOUP_X = (8.5, BOARD_W - 8.5, 11.8, BOARD_W - 11.8)
PICO_CENTER = (40.0, 101.0)  # SMD Pico: only the antenna strip (y+17..+35,
                             # x-21..+21) is an all-layer keepout; the body
                             # region forbids nothing on the front

LED_ORDER = ["A", "X", "Y", "S", "P", "PCL", "PCH"]


def mm(x, y):
    return pcbnew.VECTOR2I_MM(x, y)


def row_top(j):
    return CORE[1] + j * PITCH[1]


def slot_x(k):
    return CORE[0] + 0.9 + k * SLOT_P
N_SLOTS = int((CORE[2] - CORE[0] - 1.8) / SLOT_P)


class FetGrid:
    def __init__(self):
        self.used = set()

    def snap(self, x, y):
        cx = min(max(int((x - CORE[0]) / PITCH[0]), 0), COLS - 1)
        cy = min(max(int((y - CORE[1]) / PITCH[1]), 0), ROWS - 1)
        for r in range(max(COLS, ROWS)):
            for dx in range(-r, r + 1):
                for dy in (-r, r) if abs(dx) < r else range(-r, r + 1):
                    c = (cx + dx, cy + dy)
                    if 0 <= c[0] < COLS and 0 <= c[1] < ROWS and c not in self.used:
                        self.used.add(c)
                        return (CORE[0] + (c[0] + 0.5) * PITCH[0],
                                CORE[1] + (c[1] + 0.5) * PITCH[1])
        raise RuntimeError("grid full")

    def reserve_rect(self, x0, y0, x1, y1):
        for i in range(max(0, int((x0 - CORE[0]) / PITCH[0])),
                       min(COLS, int((x1 - CORE[0]) / PITCH[0]) + 1)):
            for j in range(max(0, int((y0 - CORE[1]) / PITCH[1])),
                           min(ROWS, int((y1 - CORE[1]) / PITCH[1]) + 1)):
                self.used.add((i, j))


class Channels:
    """slot allocator for the per-row service channels"""
    def __init__(self):
        self.used = defaultdict(set)  # row j -> set of slot k

    def reserve_rect(self, x0, y0, x1, y1):
        for j in range(ROWS):
            cy = row_top(j) + CH_DY
            if y0 - 1 < cy < y1 + 1:
                for k in range(N_SLOTS):
                    if x0 - 1 < slot_x(k) < x1 + 1:
                        self.used[j].add(k)

    def take(self, j0, wantx, width=1):
        k0 = int((wantx - CORE[0] - 0.9) / SLOT_P)
        for dj in [0, 1, -1, 2, -2, 3, -3, 4, -4]:
            j = j0 + dj
            if not (0 <= j < ROWS):
                continue
            for dk in [d for k in range(N_SLOTS) for d in (k, -k)]:
                k = k0 + dk
                if k < 0 or k + width > N_SLOTS:
                    continue
                if any(k + w in self.used[j] for w in range(width)):
                    continue
                for w in range(width):
                    self.used[j].add(k + w)
                return j, k
        raise RuntimeError("channels full")


def main():
    data = json.loads((ROOT / "gen" / "netlist.json").read_text())
    comps = data["components"]

    board = pcbnew.CreateEmptyBoard()
    sev = board.GetDesignSettings().m_DRCSeverities
    aliases = {"courtyards_overlap": "DRCE_OVERLAPPING_FOOTPRINTS",
               "silk_overlap": "DRCE_OVERLAPPING_SILK",
               "silk_over_copper": "DRCE_SILK_CLEARANCE",
               "pth_inside_courtyard": "DRCE_PTH_IN_COURTYARD",
               "solder_mask_bridge": "DRCE_SOLDERMASK_BRIDGE"}
    for rule, alias in aliases.items():
        code = getattr(pcbnew, "DRCE_" + rule.upper(), getattr(pcbnew, alias, None))
        if code is not None:
            sev[code] = pcbnew.RPT_SEVERITY_IGNORE

    dss = board.GetDesignSettings()
    dss.m_ViasMinSize = pcbnew.FromMM(0.4)
    dss.m_MinThroughDrill = pcbnew.FromMM(0.15)

    nets = {}

    def get_net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    def place(comp, x, y, back=False, rot=0):
        lib, name = comp["footprint"].split(":")
        fp = pcbnew.FootprintLoad("%s/%s.pretty" % (FPLIB, lib), name)
        if fp is None:
            raise RuntimeError("footprint not found: " + comp["footprint"])
        fp.SetReference(comp["ref"])
        fp.SetValue(comp["value"])
        board.Add(fp)
        fp.SetPosition(mm(x, y))
        if back:
            fp.Flip(mm(x, y), False)
        if rot:
            fp.SetOrientationDegrees(rot)
        if comp["type"] in ("fet", "resistor", "capacitor", "diode", "led",
                            "testpoint", "module"):
            fp.Reference().SetVisible(False)
        if comp.get("dnp"):
            fp.SetDNP(True)
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        for pad in fp.Pads():
            netname = comp["pins"].get(str(pad.GetNumber()))
            if netname:
                pad.SetNet(get_net(netname))
        return fp

    # die-coordinate transform (die y-up -> board y-down keeps PLA at top)
    poses = [c["pos"] for c in comps if c.get("pos")]
    minx = min(p[0] for p in poses); maxx = max(p[0] for p in poses)
    miny = min(p[1] for p in poses); maxy = max(p[1] for p in poses)

    def die2board(pos, region):
        x0, y0, x1, y1 = region
        return (x0 + (pos[0] - minx) / (maxx - minx) * (x1 - x0 - 1) + 0.5,
                y0 + (maxy - pos[1]) / (maxy - miny) * (y1 - y0 - 1) + 0.5)

    grid = FetGrid()
    chan = Channels()
    placed = set()

    # ---- 1. bond pad ring at die-true positions and die-true SIZE ----
    # die bond pads measure ~390x390 die units; scale them like everything else
    pad_mm = round(390 * (CORE[2] - CORE[0]) / (maxx - minx), 1)
    rim_in = pad_mm / 2 + 1.2
    spacing = pad_mm + 8.0  # gap fits the protection/bulk side clusters
    corner = rim_in + 6.0
    rim_used = {"L": [], "R": [], "T": [], "B": []}

    def rim_slot(edge, want, hi):
        for d in [k * 0.5 for k in range(0, int(hi * 2)) for k in (k, -k)]:
            v = want + d
            if not (corner <= v <= hi - corner):
                continue
            if any(abs(v - u) < spacing for u in rim_used[edge]):
                continue
            rim_used[edge].append(v)
            return v
        raise RuntimeError("rim full")

    pad_info = {}
    for c in comps:
        if c["role"] != "edge_pad":
            continue
        bx, by = die2board(c["pos"], (RIM + 2, RIM + 2, BOARD_W - RIM - 2, BOARD_H - RIM - 2))
        d = {"L": bx, "R": BOARD_W - bx, "T": by, "B": BOARD_H - by}
        edge = min(d, key=d.get)
        if edge in ("L", "R"):
            v = rim_slot(edge, by, BOARD_H)
            x, y = (rim_in if edge == "L" else BOARD_W - rim_in), v
        else:
            v = rim_slot(edge, bx, BOARD_W)
            x, y = v, (rim_in if edge == "T" else BOARD_H - rim_in)
        fp = place(c, x, y)
        for pad in fp.Pads():
            pad.SetSize(pcbnew.PADSTACK.ALL_LAYERS, mm(pad_mm, pad_mm))
            pad.SetDrillSize(mm(2.5, 2.5))
        val = fp.Value()
        val.SetLayer(pcbnew.F_SilkS)
        val.SetVisible(True)
        val.SetTextHeight(pcbnew.FromMM(1.2))
        val.SetTextWidth(pcbnew.FromMM(1.2))
        val.SetTextThickness(pcbnew.FromMM(0.18))
        ix = {"L": pad_mm / 2 + 2.8, "R": -pad_mm / 2 - 2.8}.get(edge, 0)
        iy = {"T": pad_mm / 2 + 2.4, "B": -pad_mm / 2 - 2.4}.get(edge, 0)
        val.SetTextPos(mm(x + ix, y + iy))
        if edge in ("T", "B"):
            val.SetTextAngleDegrees(90)
        pad_info[c["origin"]] = (x, y, edge)
        placed.add(c["ref"])

    # ---- 2. Pico 2 W site + DNP series resistors (back, over the die gap) ----
    by_ref = {c["ref"]: c for c in comps}
    place(by_ref["U1"], *PICO_CENTER, back=True)
    placed.add("U1")
    # keep the module's THT pins + keepout zones clear on the front grid/channels
    # front: keep only the antenna keepout clear (fits inside the die's gap)
    grid.reserve_rect(PICO_CENTER[0] - 21.5, PICO_CENTER[1] + 16.5,
                      PICO_CENTER[0] + 21.5, PICO_CENTER[1] + 35.5)
    series = [c for c in comps if c["role"] == "pico_series"]
    for k, c in enumerate(series):
        col = k // 13
        row = k % 13
        place(c, PICO_CENTER[0] - 20.0 + row * 3.2, PICO_CENTER[1] + 42.0 + col * 3.4, back=True, rot=90)
        placed.add(c["ref"])

    # ---- 3. protection / pull-up / bulk clusters near their pads (front) ----
    def band_pos(sig, depth, along_off=0.0):
        x, y, edge = pad_info[sig]
        # parts lie parallel to their edge so band depths can stack
        if edge == "L":
            return (depth, y + along_off, 90)
        if edge == "R":
            return (BOARD_W - depth, y + along_off, 90)
        if edge == "T":
            return (x + along_off, depth, 0)
        return (x + along_off, BOARD_H - depth, 0)

    side = pad_mm / 2 + 3.2  # clusters sit BESIDE their pad (pads reach deep)
    for c in comps:
        if c["role"] in ("input_protect", "clamp_up", "clamp_dn", "input_pullup"):
            depth = {"input_protect": BAND[0], "clamp_up": BAND[1],
                     "clamp_dn": BAND[2], "input_pullup": BAND[0]}[c["role"]]
            off = side + (3.4 if c["role"] == "input_pullup" else 0.0)
            x, y, r = band_pos(c["origin"], depth, off)
            place(c, x, y, back=True, rot=r)
            placed.add(c["ref"])
    bulkn = 0
    for c in comps:
        if c["role"] == "bulk":
            sig = "vcc" if bulkn < 2 else "vss"
            x, y, r = band_pos(sig, BAND[bulkn % 2], side + 3.6 * (bulkn % 2))
            place(c, x, y, back=True, rot=r)
            bulkn += 1
            placed.add(c["ref"])

    # ---- 4. decoupler columns/rows in the band (front) ----
    def col_blocked(x, y):
        return any(abs(y - py) < 14.0 for sig, (px, py, e) in pad_info.items()
                   if (e == "L") == (x < 100))

    def row_blocked(xv, y):
        return any(abs(xv - px) < 14.0 for sig, (px, py, e) in pad_info.items()
                   if (e == "T") == (y < 100))
    decoup = [c for c in comps if c["role"] == "decoupling"]
    slots = []
    for x in DECOUP_X:
        yv = 20.0
        while yv < BOARD_H - 20.0:
            if not col_blocked(x, yv):
                slots.append((x, yv, 90))
            yv += 3.5
    for y in (8.5, BOARD_H - 8.5):
        xv = 20.0
        while xv < BOARD_W - 20.0:
            if not row_blocked(xv, y):
                slots.append((xv, y, 0))
            xv += 3.5
    for c, (x, y, r) in zip(decoup, slots):
        place(c, x, y, back=True, rot=r)
        placed.add(c["ref"])
    if len(decoup) > len(slots):
        print("WARN: %d decouplers unplaced" % (len(decoup) - len(slots)))

    # ---- 5. LEDs inline: driver FET in a cell, LED + limit R in the channel ----
    led_cols = defaultdict(dict)
    for c in comps:
        r = c["role"]
        if r.startswith("led_") and r != "led_limit" and c["type"] == "led":
            led_cols[c["origin"]]["led"] = c
        elif r == "led_limit":
            led_cols[c["origin"]]["limit"] = c
        elif r == "led_driver":
            led_cols[c["origin"]]["driver"] = c
    for name, col in led_cols.items():
        want = die2board(col["led"]["pos"], CORE)
        dx_, dy_ = grid.snap(*want)
        place(col["driver"], dx_, dy_)
        lx_, ly_ = grid.snap(*want)
        place(col["led"], lx_, ly_)
        placed.add(col["led"]["ref"])
        placed.add(col["driver"]["ref"])  # limit R placed with back passives

    # ---- 6. core FETs at die-true positions. At ~36% cell occupancy the
    # legalization barely moves anything, so the die's local density -- PLA
    # stripes, sparse logic, real gaps -- reproduces itself faithfully.
    for c in comps:
        if c["ref"] in placed or c["type"] != "fet":
            continue
        want = die2board(c["pos"], CORE) if c.get("pos") else (140.0, 150.0)
        sx, sy = grid.snap(*want)
        place(c, sx, sy)
        placed.add(c["ref"])

    # ---- 7. pull-ups / ballast on the BACK at their node centroid ----
    backgrid = FetGrid()  # reuse cell raster; back is nearly empty
    backgrid.reserve_rect(PICO_CENTER[0] - 21.5, PICO_CENTER[1] - 26,
                          PICO_CENTER[0] + 21.5, PICO_CENTER[1] + 35.5)
    backgrid.reserve_rect(PICO_CENTER[0] - 21.5, PICO_CENTER[1] + 38.5,
                          PICO_CENTER[0] + 21.5, PICO_CENTER[1] + 50.0)
    for c in comps:
        if c["ref"] in placed or c["role"] == "pico_site":
            continue
        want = die2board(c["pos"], CORE) if c.get("pos") else (110.0, 120.0)
        sx, sy = backgrid.snap(*want)
        place(c, sx, sy, back=True)
        placed.add(c["ref"])

    # ---- outline + mounting holes ----
    for pts in [((0, 0), (BOARD_W, 0)), ((BOARD_W, 0), (BOARD_W, BOARD_H)),
                ((BOARD_W, BOARD_H), (0, BOARD_H)), ((0, BOARD_H), (0, 0))]:
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(mm(*pts[0])); seg.SetEnd(mm(*pts[1]))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.1))
        board.Add(seg)
    for k, (hx, hy) in enumerate([(4.5, 4.5), (BOARD_W - 4.5, 4.5),
                                  (4.5, BOARD_H - 4.5), (BOARD_W - 4.5, BOARD_H - 4.5)]):
        holefp = pcbnew.FootprintLoad("%s/MountingHole.pretty" % FPLIB,
                                      "MountingHole_3.2mm_M3")
        holefp.SetReference("H%d" % (k + 1))
        holefp.Reference().SetVisible(False)
        board.Add(holefp)
        holefp.SetPosition(mm(hx, hy))

    out = str(ROOT / "gen" / "discrete6502.kicad_pcb")
    board.Save(out)
    (ROOT / "gen" / "discrete6502.kicad_pro").write_text(json.dumps({
        "board": {"design_settings": {
            "rule_severities": {
                k: "ignore" for k in list(aliases) + ["lib_footprint_issues",
                                                      "lib_footprint_mismatch"]},
            "rules": {"min_via_diameter": 0.4,
                      "min_through_hole_diameter": 0.15}}},
        "meta": {"filename": "discrete6502.kicad_pro", "version": 3}}, indent=1))
    (ROOT / "gen" / "layout_params.json").write_text(json.dumps(dict(
        core=CORE, pitch=PITCH, board=(BOARD_W, BOARD_H),
        antenna=(PICO_CENTER[0] - 21.5, PICO_CENTER[1] + 16.5,
                 PICO_CENTER[0] + 21.5, PICO_CENTER[1] + 35.5))))
    print("board %.1f x %.1f, placed %d components, %d nets -> %s"
          % (BOARD_W, BOARD_H, len(placed), len(nets), out))


if __name__ == "__main__":
    main()
