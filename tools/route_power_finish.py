#!/usr/bin/env python3
"""Finish power stitching: connect leftover vss/vcc pads to their planes.

route_power.py leaves ~50 pads unstitched (its via-spot search gave up);
after signal routing the free space changed anyway. For every vss/vcc pad
with no same-net copper touching it, find the nearest EXACT-geometry-legal
via spot (clearance to all other-net copper on F+B, hole-to-hole to other
vias), drop a via there and a short track from the pad. A via anywhere
reaches the plane, so this always terminates unless a pad is truly walled in.

Run with KiCad's bundled python AFTER signal routing, BEFORE final DRC.
"""
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")

TRACK_W = 0.25
VIA_DRILL, VIA_DIA = 0.2, 0.45
CLR = 0.127
VIA_NEED = VIA_DIA / 2 + CLR          # via center to other-net copper edge
TRK_NEED = TRACK_W / 2 + CLR          # track centerline to other-net copper edge
HOLE_NEED = 0.25 + VIA_DRILL          # hole-to-hole (edge) -> center distance

BUCKET = 2.0


def main():
    t0 = time.time()
    board = pcbnew.LoadBoard(PCB)
    vss = board.GetNetsByName()["vss"].GetNetCode()
    vcc = board.GetNetsByName()["vcc"].GetNetCode()
    power = {vss, vcc}

    # copper inventory bucketed by position: (kind, geom, netcode, layers)
    buckets = defaultdict(list)

    def put(x, y, item):
        buckets[(int(x / BUCKET), int(y / BUCKET))].append(item)

    def nearby(x, y):
        bx, by = int(x / BUCKET), int(y / BUCKET)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for it in buckets.get((bx + dx, by + dy), ()):
                    yield it

    pads_power = []
    for fp in board.Footprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            r = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                 bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            onF = pad.IsOnLayer(pcbnew.F_Cu)
            onB = pad.IsOnLayer(pcbnew.B_Cu)
            layers = (0, 1) if pth else ((0,) if onF else ()) + ((1,) if onB else ())
            if not layers:
                continue
            p = pad.GetPosition()
            x, y = p.x / 1e6, p.y / 1e6
            code = pad.GetNetCode()
            put(x, y, ("rect", r, code, layers, None))
            if code in power:
                pads_power.append((x, y, r, code, layers,
                                   fp.GetReference() + "." + str(pad.GetNumber())))
    for t in board.Tracks():
        code = t.GetNetCode()
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            x, y = p.x / 1e6, p.y / 1e6
            put(x, y, ("via", (x, y, t.GetWidth() / 2e6), code, (0, 1), None))
        else:
            s, e = t.GetStart(), t.GetEnd()
            L = 0 if t.GetLayer() == pcbnew.F_Cu else 1
            seg = (s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6, t.GetWidth() / 2e6)
            put((seg[0] + seg[2]) / 2, (seg[1] + seg[3]) / 2,
                ("seg", seg, code, (L,), None))
            # long segments: bucket at both ends too
            put(seg[0], seg[1], ("seg", seg, code, (L,), None))
            put(seg[2], seg[3], ("seg", seg, code, (L,), None))

    # keepout zones (vias not allowed)
    keep = []
    allz = list(board.Zones())
    for fp in board.Footprints():
        allz.extend(fp.Zones())
    for z in allz:
        if z.GetIsRuleArea() and z.GetDoNotAllowVias():
            zb = z.GetBoundingBox()
            keep.append((zb.GetLeft() / 1e6, zb.GetTop() / 1e6,
                         zb.GetRight() / 1e6, zb.GetBottom() / 1e6))

    def d_rect(x, y, r):
        return math.hypot(max(r[0] - x, 0, x - r[2]), max(r[1] - y, 0, y - r[3]))

    def d_seg(x, y, s):
        sx, sy, ex, ey, hw = s
        ax, ay = ex - sx, ey - sy
        L2 = ax * ax + ay * ay
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - sx) * ax + (y - sy) * ay) / L2))
        return max(0.0, math.hypot(x - sx - ax * t, y - sy - ay * t) - hw)

    def dist_item(x, y, it):
        kind, g = it[0], it[1]
        if kind == "rect":
            return d_rect(x, y, g)
        if kind == "via":
            return max(0.0, math.hypot(x - g[0], y - g[1]) - g[2])
        return d_seg(x, y, g)

    def touches_same_net(x, y, r, code, layers):
        for it in nearby(x, y):
            if it[2] != code:
                continue
            if it[0] == "rect":
                continue  # pads of same net don't stitch each other to a plane
            if not (set(layers) & set(it[3])):
                continue  # copper on another layer can't stitch this pad
            if dist_item(x, y, it) < 0.01 or (
                    it[0] == "via" and r[0] - 0.05 < it[1][0] < r[2] + 0.05
                    and r[1] - 0.05 < it[1][1] < r[3] + 0.05):
                return True
            if it[0] == "seg":
                # track endpoint inside pad rect counts
                sx, sy, ex, ey, hw = it[1]
                for px, py in ((sx, sy), (ex, ey)):
                    if r[0] - 0.05 < px < r[2] + 0.05 and r[1] - 0.05 < py < r[3] + 0.05:
                        return True
        return False

    def via_legal(x, y, code):
        for k in keep:
            if k[0] - VIA_NEED < x < k[2] + VIA_NEED and k[1] - VIA_NEED < y < k[3] + VIA_NEED:
                return False
        for it in nearby(x, y):
            if it[0] == "via":
                if math.hypot(x - it[1][0], y - it[1][1]) < (HOLE_NEED
                        if it[2] == code else max(HOLE_NEED, VIA_NEED + it[1][2])):
                    return False
            elif it[2] != code:
                if dist_item(x, y, it) < VIA_NEED:
                    return False
        return True

    def track_legal(x0, y0, x1, y1, code, L):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.1))
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = y0 + (y1 - y0) * i / n
            for it in nearby(x, y):
                if it[2] == code or L not in it[3]:
                    continue
                if dist_item(x, y, it) < TRK_NEED:
                    return False
        return True

    todo = [p for p in pads_power if not touches_same_net(p[0], p[1], p[2], p[3], p[4])]
    print("power pads needing stitching: %d" % len(todo), flush=True)

    LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
    done = failed = 0
    fails = []
    for x, y, r, code, layers, ref in todo:
        L = layers[0] if len(layers) == 1 else 1
        best = None
        # spiral over candidate via spots on a 0.1 grid, nearest first
        RAD = 3.0
        cands = []
        step = 0.1
        n = int(RAD / step)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                cx, cy = x + i * step, y + j * step
                cands.append((math.hypot(i * step, j * step), cx, cy))
        cands.sort()
        for d, cx, cy in cands:
            if not via_legal(cx, cy, code):
                continue
            if d <= 0.05:
                best = (cx, cy, None)
                break
            if track_legal(x, y, cx, cy, code, L):
                best = (cx, cy, None)
                break
            # L-shaped escape: corner at (cx,y) or (x,cy)
            ok_corner = None
            for kx, ky in ((cx, y), (x, cy)):
                if (track_legal(x, y, kx, ky, code, L)
                        and track_legal(kx, ky, cx, cy, code, L)):
                    ok_corner = (kx, ky)
                    break
            if ok_corner:
                best = (cx, cy, ok_corner)
                break
        attach = None
        if best is None:
            # no legal via spot: attach to nearby same-net copper with a track
            targets = []
            for it in nearby(x, y):
                if it[2] != code or L not in it[3]:
                    continue
                if it[0] == "seg":
                    sx, sy, ex, ey, hw = it[1]
                    ax, ay = ex - sx, ey - sy
                    L2 = ax * ax + ay * ay
                    tt = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - sx) * ax + (y - sy) * ay) / L2))
                    px, py = sx + ax * tt, sy + ay * tt
                    targets.append((math.hypot(px - x, py - y), px, py))
                elif it[0] == "via":
                    targets.append((math.hypot(it[1][0] - x, it[1][1] - y),
                                    it[1][0], it[1][1]))
            targets.sort()
            for d, px, py in targets:
                if track_legal(x, y, px, py, code, L):
                    attach = (px, py, None)
                    break
                for kx, ky in ((px, y), (x, py)):
                    if (track_legal(x, y, kx, ky, code, L)
                            and track_legal(kx, ky, px, py, code, L)):
                        attach = (px, py, (kx, ky))
                        break
                if attach:
                    break
        if best is None and attach is None:
            failed += 1
            fails.append(ref)
            continue
        cx, cy, corner = best if best else attach
        if best:
            v = pcbnew.PCB_VIA(board)
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetPosition(pcbnew.VECTOR2I_MM(round(cx, 3), round(cy, 3)))
            v.SetDrill(pcbnew.FromMM(VIA_DRILL))
            v.SetWidth(pcbnew.FromMM(VIA_DIA))
            v.SetNetCode(code)
            board.Add(v)
            put(cx, cy, ("via", (cx, cy, VIA_DIA / 2), code, (0, 1), None))

        def emit_seg(x0, y0, x1, y1):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I_MM(round(x0, 3), round(y0, 3)))
            t.SetEnd(pcbnew.VECTOR2I_MM(round(x1, 3), round(y1, 3)))
            t.SetWidth(pcbnew.FromMM(TRACK_W))
            t.SetLayer(LAYERS[L])
            t.SetNetCode(code)
            board.Add(t)
            put((x0 + x1) / 2, (y0 + y1) / 2,
                ("seg", (x0, y0, x1, y1, TRACK_W / 2), code, (L,), None))

        if math.hypot(cx - x, cy - y) > 0.05:
            if corner:
                emit_seg(x, y, corner[0], corner[1])
                emit_seg(corner[0], corner[1], cx, cy)
            else:
                emit_seg(x, y, cx, cy)
        done += 1

    print("stitched %d, failed %d %s" % (done, failed, fails[:10]), flush=True)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    print("unconnected after power finish:",
          board.GetConnectivity().GetUnconnectedCount(True), flush=True)
    board.Save(PCB)
    print("saved, %.0fs" % (time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
