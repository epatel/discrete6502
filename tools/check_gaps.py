#!/usr/bin/env python3
"""Independent connectivity check: per net, union-find over pads/tracks/vias
with geometric touch tests; reports cluster counts and the closest inter-
cluster gap (position, distance, layers) for every broken net.
Writes gen/gaps.json. Run with KiCad's bundled python."""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
board = pcbnew.LoadBoard(str(ROOT / "gen" / "discrete6502.kicad_pcb"))

F, B = 0, 3
LMAP = {}  # populated after pcbnew import resolves layer ids


def seg_dist(a, b, c, d):
    # min distance between segments ab and cd (2D)
    def dot(u, v): return u[0] * v[0] + u[1] * v[1]

    def pt_seg(p, a, b):
        ab = (b[0] - a[0], b[1] - a[1])
        t = 0.0
        L2 = dot(ab, ab)
        if L2 > 0:
            t = max(0.0, min(1.0, dot((p[0] - a[0], p[1] - a[1]), ab) / L2))
        q = (a[0] + ab[0] * t, a[1] + ab[1] * t)
        return math.hypot(p[0] - q[0], p[1] - q[1])
    if max(a[0], b[0]) < min(c[0], d[0]) - 5 or max(c[0], d[0]) < min(a[0], b[0]) - 5:
        return 9e9
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


nets = defaultdict(list)  # code -> items: (kind, layerset, geom, halfwidth)
for fp in board.Footprints():
    for pad in fp.Pads():
        code = pad.GetNetCode()
        if code <= 0:
            continue
        p = pad.GetPosition()
        pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        Ls = ((0, 1, 2, 3) if pth
              else ((F,) if pad.IsOnLayer(pcbnew.F_Cu) else (B,)))
        bb = pad.GetBoundingBox()
        hw = max(bb.GetWidth(), bb.GetHeight()) / 2e6
        nets[code].append(("pad", Ls, ((p.x / 1e6, p.y / 1e6),) * 2, hw,
                           fp.GetReference() + "." + str(pad.GetNumber())))

for t in board.Tracks():
    code = t.GetNetCode()
    if code <= 0:
        continue
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition()
        nets[code].append(("via", (0, 1, 2, 3), ((p.x / 1e6, p.y / 1e6),) * 2, 0.225, "via"))
    else:
        s, e = t.GetStart(), t.GetEnd()
        L = {pcbnew.F_Cu: 0, pcbnew.In2_Cu: 1, pcbnew.In3_Cu: 2}.get(t.GetLayer(), B)
        nets[code].append(("trk", (L,), ((s.x / 1e6, s.y / 1e6), (e.x / 1e6, e.y / 1e6)),
                           t.GetWidth() / 2e6, "trk"))

vss = board.GetNetsByName()["vss"].GetNetCode()
vcc = board.GetNetsByName()["vcc"].GetNetCode()

broken = []
gapcls = defaultdict(int)
for code, items in nets.items():
    if code in (vss, vcc) or len(items) < 2:
        continue
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def touch(a, b):
        if not (set(a[1]) & set(b[1])):
            return False
        d = seg_dist(a[2][0], a[2][1], b[2][0], b[2][1])
        return d <= a[3] + b[3] + 0.005

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j) and touch(items[i], items[j]):
                parent[find(i)] = find(j)
    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)
    if len(clusters) == 1:
        continue
    ks = sorted(clusters.values(), key=len, reverse=True)
    # closest pair between biggest cluster and each minor cluster
    for minor in ks[1:]:
        bestd, bestpair = 9e9, None
        for i in ks[0]:
            for j in minor:
                d = seg_dist(items[i][2][0], items[i][2][1],
                             items[j][2][0], items[j][2][1]) - items[i][3] - items[j][3]
                if d < bestd:
                    bestd, bestpair = d, (i, j)
        i, j = bestpair
        samelayer = bool(set(items[i][1]) & set(items[j][1]))
        cls = ("layer-mismatch" if not samelayer else
               "tiny" if bestd < 0.05 else "small" if bestd < 0.5 else "big")
        gapcls[cls] += 1
        broken.append(dict(net=board.FindNet(code).GetNetname(), gap=round(bestd, 3),
                           cls=cls, a=items[i][4], b=items[j][4],
                           pos=[round(items[j][2][0][0], 2), round(items[j][2][0][1], 2)]))

print("broken nets/clusters:", len(broken))
print("classes:", dict(gapcls))
for x in broken[:12]:
    print(" ", x)
(ROOT / "gen" / "gaps.json").write_text(json.dumps(broken))
