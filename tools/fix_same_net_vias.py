#!/usr/bin/env python3
"""Merge same-net via pairs closer than hole-to-hole allows.

The fine-grid router imposes no spacing between SAME-net vias (copper rules
don't care), but 0.2mm drills need >=0.25mm hole edge-to-edge => centers
>=0.45mm. Cluster same-net vias closer than that, keep one per cluster,
delete the rest, and stub each removed position to the survivor on BOTH
copper layers so every former layer-change point stays connected.

Run with KiCad's bundled python on the routed board, before DRC.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")
MIN_C = 0.45  # min same-net via center distance (0.2 drills, 0.25 hole-hole)


def main():
    board = pcbnew.LoadBoard(PCB)
    byname = defaultdict(list)
    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            byname[t.GetNetCode()].append((p.x / 1e6, p.y / 1e6, t))

    # endpoint index: which layers have copper touching a given point, per net
    endp = defaultdict(set)  # (code, round(x), round(y)) -> {layer}
    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            continue
        for pp in (t.GetStart(), t.GetEnd()):
            endp[(t.GetNetCode(), round(pp.x / 1e6, 2), round(pp.y / 1e6, 2))].add(t.GetLayer())

    removed = stubs = 0
    for code, vias in byname.items():
        if len(vias) < 2:
            continue
        # spatial hash
        grid = defaultdict(list)
        for i, (x, y, v) in enumerate(vias):
            grid[(int(x / MIN_C), int(y / MIN_C))].append(i)
        parent = list(range(len(vias)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, (x, y, v) in enumerate(vias):
            bx, by = int(x / MIN_C), int(y / MIN_C)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid.get((bx + dx, by + dy), ()):
                        if j <= i:
                            continue
                        if math.hypot(x - vias[j][0], y - vias[j][1]) < MIN_C:
                            parent[find(i)] = find(j)
        clusters = defaultdict(list)
        for i in range(len(vias)):
            clusters[find(i)].append(i)
        for members in clusters.values():
            if len(members) < 2:
                continue
            keep = members[0]
            kx, ky = vias[keep][0], vias[keep][1]
            for i in members[1:]:
                x, y, v = vias[i]
                board.Remove(v)
                removed += 1
                if math.hypot(x - kx, y - ky) > 0.01:
                    # stub only the layers that actually have copper at the
                    # removed position (blind all-layer stubs dangled)
                    layers = endp.get((code, round(x, 2), round(y, 2)), set())
                    if not layers:
                        layers = {pcbnew.F_Cu, pcbnew.B_Cu}
                    for layer in layers:
                        t = pcbnew.PCB_TRACK(board)
                        t.SetStart(pcbnew.VECTOR2I_MM(x, y))
                        t.SetEnd(pcbnew.VECTOR2I_MM(kx, ky))
                        t.SetWidth(pcbnew.FromMM(0.127))
                        t.SetLayer(layer)
                        t.SetNetCode(code)
                        board.Add(t)
                        stubs += 1

    # vias on top of same-net PTH pads are redundant (the pad spans all
    # layers) and their holes collide with the pad hole -- delete
    pth = defaultdict(list)  # netcode -> (x, y, bbox)
    for fp in board.Footprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and pad.GetNetCode() > 0:
                p = pad.GetPosition()
                bb = pad.GetBoundingBox()
                pth[pad.GetNetCode()].append(
                    (bb.GetLeft() / 1e6 + 0.3, bb.GetTop() / 1e6 + 0.3,
                     bb.GetRight() / 1e6 - 0.3, bb.GetBottom() / 1e6 - 0.3))
    onpad = 0
    for t in list(board.Tracks()):
        if t.GetClass() != "PCB_VIA":
            continue
        p = t.GetPosition()
        x, y = p.x / 1e6, p.y / 1e6
        for r in pth.get(t.GetNetCode(), ()):
            if r[0] < x < r[2] and r[1] < y < r[3]:
                board.Remove(t)
                removed += 1
                onpad += 1
                break

    print("removed %d same-net vias (%d on PTH pads), added %d stubs"
          % (removed, onpad, stubs))
    if removed:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        # drop short stubs left dangling by the merges
        conn = board.GetConnectivity()
        dang = 0
        for t in list(board.Tracks()):
            if t.GetClass() == "PCB_VIA" or t.GetLength() > pcbnew.FromMM(0.5):
                continue
            try:
                if conn.TestTrackEndpointDangling(t):
                    board.Remove(t)
                    dang += 1
            except Exception:
                break
        if dang:
            print("removed %d dangling stubs" % dang)
            board.BuildConnectivity()
        print("unconnected:", board.GetConnectivity().GetUnconnectedCount(True))
        board.Save(PCB)
        print("saved")


if __name__ == "__main__":
    main()
