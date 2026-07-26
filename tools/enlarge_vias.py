#!/usr/bin/env python3
"""Grow every via to 0.55mm pad / 0.30mm drill, nudging what is in the way.

Why: JLCPCB prices the 0.2mm drill class as an extra, while 0.3mm is free
on 6-layer boards. Drilling our 0.45mm via pads at 0.3mm would leave a
0.075mm annular ring; growing the pads to 0.55mm restores the 0.125mm ring
we designed for, at no fab cost. Roughly 97% of vias have the room outright;
this pass tries to make the rest fit by moving them a fraction of a
millimetre (dragging their track endpoints, exactly like fix_via_pairs.py),
and only leaves a via at 0.45mm when no legal spot exists.

Note the drill grows for ALL vias -- a single 0.2mm hole anywhere would put
the whole board back in the paid class -- so hole-to-hole conflicts must be
nudged, not shrunk away.

Run with KiCad's bundled python, after the routing/finishing passes.
Re-run check_parity, check_gaps and DRC afterwards.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")

SIZES = (0.275, 0.26, 0.225)       # pad radii: 0.55/0.52/0.45 -> ring .125/.11/.075
# The last rung is today's 0.45mm pad, which at a 0.30mm drill leaves a
# 0.075mm ring -- below KiCad's default min_via_annular_width of 0.1 but
# within JLCPCB's capability (they pair a 0.30mm hole with a 0.40mm via,
# i.e. a 0.05mm ring). This pass relaxes that board rule to 0.075 to match
# the fab, and reports how many vias actually land on it.
DRILL = 0.30
CLR = 0.127                        # copper clearance
# hole-to-hole: JLCPCB's manufacturing minimum is 0.20mm edge-to-edge, and
# same-net holes breaking into one another is electrically harmless anyway
# (KiCad's stricter 0.25mm default is only a *warning* on this board). Keep
# the strict figure between different nets, where a merge would be a short.
HOLE_CLR_SAME = 0.20
HOLE_CLR_DIFF = 0.25
TRK_HW = 0.0635
BUCKET = 2.0
SEARCH_R = 0.6                     # how far a via may be nudged
STEP = 0.05


def main():
    board = pcbnew.LoadBoard(PCB)

    vias, tracks = [], []
    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            vias.append({"x": p.x / 1e6, "y": p.y / 1e6, "code": t.GetNetCode(),
                         "obj": t, "r": SIZES[0], "fixed": False})
        else:
            tracks.append(t)
    print("vias: %d, tracks: %d" % (len(vias), len(tracks)))

    # ---- spatial inventory -------------------------------------------------
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
            pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            if not (pth or pad.IsOnLayer(pcbnew.F_Cu) or pad.IsOnLayer(pcbnew.B_Cu)):
                continue
            bb = pad.GetBoundingBox()
            r = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                 bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            p = pad.GetPosition()
            put(p.x / 1e6, p.y / 1e6, ("rect", r, pad.GetNetCode(), pad))
    for t in tracks:
        s, e = t.GetStart(), t.GetEnd()
        seg = (s.x / 1e6, s.y / 1e6, e.x / 1e6, e.y / 1e6, t.GetWidth() / 2e6)
        # sample along the whole length: a segment indexed only at its ends is
        # invisible to a via sitting beside its middle (cost the first run 45
        # clearance errors and 5 shorts)
        L = math.hypot(seg[2] - seg[0], seg[3] - seg[1])
        n = max(1, int(L / 0.5))
        for i in range(n + 1):
            put(seg[0] + (seg[2] - seg[0]) * i / n,
                seg[1] + (seg[3] - seg[1]) * i / n, ("seg", seg, t.GetNetCode(), t))
    for v in vias:
        put(v["x"], v["y"], ("via", v, v["code"], v["obj"]))

    # a via sitting on a same-net pad is that pad's connection to the plane;
    # moving it off the pad silently breaks the net
    anchored = 0
    for fp in board.Footprints():
        for pad in fp.Pads():
            if not pad.HasHole() and not pad.IsOnLayer(pcbnew.F_Cu) \
                    and not pad.IsOnLayer(pcbnew.B_Cu):
                continue
            pp = pad.GetPosition()
            for it in nearby(pp.x / 1e6, pp.y / 1e6):
                if it[0] != "via" or it[2] != pad.GetNetCode():
                    continue
                v = it[1]
                if pad.HitTest(pcbnew.VECTOR2I_MM(v["x"], v["y"])):
                    v["fixed"] = True
                    anchored += 1
    print("vias anchored in a same-net pad (may resize, not move):", anchored)

    def d_rect(x, y, g):
        return math.hypot(max(g[0] - x, 0, x - g[2]), max(g[1] - y, 0, y - g[3]))

    def d_seg(x, y, g):
        sx, sy, ex, ey, hw = g
        ax, ay = ex - sx, ey - sy
        L2 = ax * ax + ay * ay
        tt = 0.0 if L2 == 0 else max(0.0, min(1.0,
                                              ((x - sx) * ax + (y - sy) * ay) / L2))
        return math.hypot(x - sx - ax * tt, y - sy - ay * tt) - hw

    def via_ok(x, y, code, r, me):
        """is a via of radius r legal at (x, y)?"""
        for it in nearby(x, y):
            if it[3] is me:
                continue
            if it[0] == "via":
                o = it[1]
                d = math.hypot(x - o["x"], y - o["y"])
                same = o["code"] == code
                if d < DRILL + (HOLE_CLR_SAME if same else HOLE_CLR_DIFF):
                    return False
                if not same and d < r + o["r"] + CLR:
                    return False
            elif it[2] != code:
                d = d_rect(x, y, it[1]) if it[0] == "rect" else d_seg(x, y, it[1])
                if d < r + CLR:
                    return False
        return True

    def seg_ok(x0, y0, x1, y1, code, layer, me):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 0.08))
        for i in range(n + 1):
            x = x0 + (x1 - x0) * i / n
            y = y0 + (y1 - y0) * i / n
            for it in nearby(x, y):
                if it[2] == code or it[3] is me:
                    continue
                if it[0] == "seg":
                    if it[3].GetLayer() != layer:
                        continue
                    if d_seg(x, y, it[1]) < TRK_HW + CLR:
                        return False
                elif it[0] == "via":
                    o = it[1]
                    if math.hypot(x - o["x"], y - o["y"]) < TRK_HW + CLR + o["r"]:
                        return False
                elif d_rect(x, y, it[1]) < TRK_HW + CLR:
                    return False
        return True

    # ---- pass 1: who does not fit at the target size? ----------------------
    bad = [v for v in vias
           if not via_ok(v["x"], v["y"], v["code"], SIZES[0], v["obj"])]
    print("vias needing attention at %.2fmm: %d of %d (%.1f%%)"
          % (SIZES[0] * 2, len(bad), len(vias), 100.0 * len(bad) / len(vias)))

    # ---- pass 2: shrink one step, else nudge, else fail --------------------
    shrunk = nudged = stuck = 0
    dists = []
    for v in bad:
        x0, y0, code, obj = v["x"], v["y"], v["code"], v["obj"]

        # cheapest fix first: one size down, no geometry change at all
        done = False
        for r in SIZES[1:]:
            if via_ok(x0, y0, code, r, obj):
                v["r"] = r
                shrunk += 1
                done = True
                break
        if done:
            continue
        if v["fixed"]:          # stitch via inside a pad: cannot be moved
            stuck += 1
            v["r"] = SIZES[-1]
            continue

        touch = [t for t in tracks if t.GetNetCode() == code and any(
            abs(pp.x / 1e6 - x0) < 0.02 and abs(pp.y / 1e6 - y0) < 0.02
            for pp in (t.GetStart(), t.GetEnd()))]
        k = int(SEARCH_R / STEP)
        cands = sorted((math.hypot(a * STEP, b * STEP), x0 + a * STEP, y0 + b * STEP)
                       for a in range(-k, k + 1) for b in range(-k, k + 1)
                       if math.hypot(a * STEP, b * STEP) <= SEARCH_R)
        for r in SIZES:
            for d, nx, ny in cands:
                if d == 0 or not via_ok(nx, ny, code, r, obj):
                    continue
                ok = True
                for t in touch:
                    ss, ee = t.GetStart(), t.GetEnd()
                    fixed = (ee if (abs(ss.x / 1e6 - x0) < 0.02
                                    and abs(ss.y / 1e6 - y0) < 0.02) else ss)
                    if not seg_ok(nx, ny, fixed.x / 1e6, fixed.y / 1e6,
                                  code, t.GetLayer(), t):
                        ok = False
                        break
                if not ok:
                    continue
                obj.SetPosition(pcbnew.VECTOR2I_MM(round(nx, 3), round(ny, 3)))
                for t in touch:
                    ss, ee = t.GetStart(), t.GetEnd()
                    if abs(ss.x / 1e6 - x0) < 0.02 and abs(ss.y / 1e6 - y0) < 0.02:
                        t.SetStart(pcbnew.VECTOR2I_MM(round(nx, 3), round(ny, 3)))
                    if abs(ee.x / 1e6 - x0) < 0.02 and abs(ee.y / 1e6 - y0) < 0.02:
                        t.SetEnd(pcbnew.VECTOR2I_MM(round(nx, 3), round(ny, 3)))
                v["x"], v["y"], v["r"] = nx, ny, r
                dists.append(d)
                nudged += 1
                done = True
                break
            if done:
                break
        if not done:
            stuck += 1
            v["r"] = SIZES[-1]

    print("shrunk to %.2fmm in place: %d | nudged: %d (median %.2fmm, max %.2fmm) "
          "| STUCK: %d" % (SIZES[-1] * 2, shrunk, nudged,
                           sorted(dists)[len(dists) // 2] if dists else 0,
                           max(dists) if dists else 0, stuck))
    if stuck:
        print("!! %d vias could not be resolved -- they keep a %.2fmm pad "
              "(ring %.3f); DRC will say whether that is legal"
              % (stuck, SIZES[-1] * 2, SIZES[-1] - DRILL / 2))

    # ---- apply sizes -------------------------------------------------------
    for v in vias:
        v["obj"].SetWidth(pcbnew.FromMM(round(v["r"] * 2, 3)))
        v["obj"].SetDrill(pcbnew.FromMM(DRILL))
    import collections as _c
    hist = _c.Counter(round(v["r"] * 2, 2) for v in vias)
    for dia, n in sorted(hist.items(), reverse=True):
        print("final: %5d vias at %.2fmm pad (ring %.3fmm)"
              % (n, dia, (dia - DRILL) / 2))

    if "--dry-run" in sys.argv:
        print("dry run, not saved")
        return

    # match the board rule to what the fab actually supports (see header)
    import json as _json
    pro = ROOT / "gen" / "discrete6502.kicad_pro"
    pj = _json.loads(pro.read_text())
    pj["board"]["design_settings"]["rules"]["min_via_annular_width"] = 0.075
    pj["board"]["design_settings"]["rules"]["min_via_diameter"] = 0.45
    pro.write_text(_json.dumps(pj, indent=2))
    print("min_via_annular_width -> 0.075 (JLC capability)")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    print("unconnected:", board.GetConnectivity().GetUnconnectedCount(True))
    board.Save(PCB)
    print("saved")


if __name__ == "__main__":
    main()
