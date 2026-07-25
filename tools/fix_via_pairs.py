#!/usr/bin/env python3
"""Nudge apart different-net via pairs closer than clearance allows.

The router's grid can't express sub-cell alignments, so a handful of
via pairs emit at < 0.577mm (via dia 0.45 + clearance 0.127). For each
offending pair, try moving one via (then the other) to a nearby
exact-geometry-legal spot on a fine raster, dragging the endpoints of its
connected tracks along (segments tilt slightly; their new geometry is
clearance-checked too).

Run with KiCad's bundled python after fix_same_net_vias.py; re-run DRC after.
"""
import math
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")

VIA_R = 0.225
CLR = 0.127
NEED_VV = 2 * VIA_R + CLR          # via-via center distance (0.577)
NEED_VC = VIA_R + CLR              # via center to other copper edge (0.352)
NEED_HH = 0.25 + 0.2               # hole-to-hole -> center distance (0.45)
TRK_HW = 0.0635
BUCKET = 2.0


def main():
    board = pcbnew.LoadBoard(PCB)

    vias = []
    tracks = []
    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            vias.append([p.x / 1e6, p.y / 1e6, t.GetNetCode(), t])
        else:
            tracks.append(t)

    # offending different-net pairs
    grid = defaultdict(list)
    for i, (x, y, code, v) in enumerate(vias):
        grid[(int(x), int(y))].append(i)
    pairs = []
    for i, (x, y, code, v) in enumerate(vias):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((int(x) + dx, int(y) + dy), ()):
                    if j <= i or vias[j][2] == code:
                        continue
                    if math.hypot(x - vias[j][0], y - vias[j][1]) < NEED_VV - 1e-6:
                        pairs.append((i, j))
    print("offending via pairs:", len(pairs))
    if not pairs:
        return

    # copper inventory for exact checks (bucketed)
    buckets = defaultdict(list)

    def put(x, y, item):
        buckets[(int(x / BUCKET), int(y / BUCKET))].append(item)

    def nearby(x, y):
        bx, by = int(x / BUCKET), int(y / BUCKET)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for it in buckets.get((bx + dx, by + dy), ()):
                    yield it

    for fp in board.Footprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            r = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                 bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            onF = pad.IsOnLayer(pcbnew.F_Cu)
            onB = pad.IsOnLayer(pcbnew.B_Cu)
            if not (pth or onF or onB):
                continue
            p = pad.GetPosition()
            put(p.x / 1e6, p.y / 1e6, ("rect", r, pad.GetNetCode(), pth))
    for t in tracks:
        s, e = t.GetStart(), t.GetEnd()
        seg = (s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6, t.GetWidth() / 2e6)
        for px, py in ((seg[0], seg[1]), (seg[2], seg[3]),
                       ((seg[0] + seg[2]) / 2, (seg[1] + seg[3]) / 2)):
            put(px, py, ("seg", seg, t.GetNetCode(), t))
    for x, y, code, v in vias:
        put(x, y, ("via", (x, y), code, v))

    def d_item(x, y, it):
        kind, g = it[0], it[1]
        if kind == "rect":
            return math.hypot(max(g[0] - x, 0, x - g[2]), max(g[1] - y, 0, y - g[3]))
        if kind == "via":
            return math.hypot(x - g[0], y - g[1])
        sx, sy, ex, ey, hw = g
        ax, ay = ex - sx, ey - sy
        L2 = ax * ax + ay * ay
        tt = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - sx) * ax + (y - sy) * ay) / L2))
        return math.hypot(x - sx - ax * tt, y - sy - ay * tt) - hw

    def via_ok(x, y, code, skip):
        for it in nearby(x, y):
            if it[3] is skip:
                continue
            if it[0] == "via":
                dd = d_item(x, y, it)
                if it[2] == code:
                    if dd < NEED_HH:
                        return False
                elif dd < max(NEED_VV, NEED_HH):
                    return False
            elif it[2] != code:
                if it[0] == "rect" and it[3]:  # PTH pad: hole clearance too
                    if d_item(x, y, it) < NEED_VC:
                        return False
                elif d_item(x, y, it) < NEED_VC:
                    return False
        return True

    def seg_ok(x0, y0, x1, y1, code, layer):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.08))
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = y0 + (y1 - y0) * i / n
            for it in nearby(x, y):
                if it[2] == code:
                    continue
                if it[0] == "seg" and it[3].GetLayer() != layer:
                    continue
                if d_item(x, y, it) < TRK_HW + CLR + (VIA_R if it[0] == "via" else 0):
                    return False
        return True

    moved = failed = 0
    for i, j in pairs:
        done = False
        for vi in (i, j):
            x0, y0, code, v = vias[vi]
            other = vias[j if vi == i else i]
            # this via's connected track endpoints
            touch = [t for t in tracks if t.GetNetCode() == code and any(
                abs(pp.x / 1e6 - x0) < 0.02 and abs(pp.y / 1e6 - y0) < 0.02
                for pp in (t.GetStart(), t.GetEnd()))]
            cands = []
            R = 2.0
            step = 0.065
            k = int(R / step)
            for a in range(-k, k + 1):
                for b in range(-k, k + 1):
                    nx, ny = x0 + a * step, y0 + b * step
                    if math.hypot(nx - other[0], ny - other[1]) < NEED_VV:
                        continue
                    cands.append((math.hypot(a * step, b * step), nx, ny))
            cands.sort()
            for d, nx, ny in cands:
                if not via_ok(nx, ny, code, v):
                    continue
                segs_fine = True
                for t in touch:
                    s, e = t.GetStart(), t.GetEnd()
                    fixed = (e if (abs(s.x / 1e6 - x0) < 0.02 and abs(s.y / 1e6 - y0) < 0.02)
                             else s)
                    if not seg_ok(nx, ny, fixed.x / 1e6, fixed.y / 1e6, code, t.GetLayer()):
                        segs_fine = False
                        break
                if not segs_fine:
                    continue
                # commit
                v.SetPosition(pcbnew.VECTOR2I_MM(round(nx, 3), round(ny, 3)))
                for t in touch:
                    s, e = t.GetStart(), t.GetEnd()
                    if abs(s.x / 1e6 - x0) < 0.02 and abs(s.y / 1e6 - y0) < 0.02:
                        t.SetStart(pcbnew.VECTOR2I_MM(round(nx, 3), round(ny, 3)))
                    if abs(e.x / 1e6 - x0) < 0.02 and abs(e.y / 1e6 - y0) < 0.02:
                        t.SetEnd(pcbnew.VECTOR2I_MM(round(nx, 3), round(ny, 3)))
                vias[vi][0], vias[vi][1] = nx, ny
                put(nx, ny, ("via", (nx, ny), code, v))
                print("moved via [%s] (%.2f,%.2f) -> (%.2f,%.2f), d=%.2f"
                      % (board.FindNet(code).GetNetname(), x0, y0, nx, ny, d))
                moved += 1
                done = True
                break
            if done:
                break
        if not done:
            failed += 1
            print("FAILED pair at (%.2f,%.2f)" % (vias[i][0], vias[i][1]))

    print("moved %d, failed %d" % (moved, failed))
    if moved:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        print("unconnected:", board.GetConnectivity().GetUnconnectedCount(True))
        board.Save(PCB)
        print("saved")


if __name__ == "__main__":
    main()
