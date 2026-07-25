#!/usr/bin/env python3
"""Stage 2 of board generation: power distribution (v6, sparse single-face).

The die-true placement leaves ~64% of the board empty, so power stitching
needs no site scheme, lanes, or chains: a generic collision-aware placer
drops a via next to every vss/vcc SMD pad (sharing same-net vias when one is
already reachable nearby) using occupancy bitmaps of both faces.

  - 4 copper layers; GND (vss) zone on In1.Cu, VCC zone on In2.Cu
  - every power SMD pad gets a track to a through-via into the planes
  - THT pads (bond pad ring, mounting holes) reach the planes directly
  - the Pico antenna keepout is treated as occupied on both faces
"""
import json
import math
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")

RES = 0.25             # occupancy bitmap raster, mm
INFLATE = 0.45         # copper inflation when marking (via r0.225 + clr 0.2)
VIA_DRILL, VIA_DIA = 0.2, 0.45
TRACK_W = 0.25
SEARCH_R = 8.0         # max via distance from its pad
SHARE_R = 3.0          # reuse same-net via within this radius
import json as _json
_P = _json.loads((ROOT / "gen" / "layout_params.json").read_text())
ANTENNA = tuple(_P["antenna"])
CORE = tuple(_P["core"])
PITCH = tuple(_P["pitch"])
SPOT_F = (1.05, 0.75)  # in-cell via spot for FRONT pads (by construction)
SPOT_B = (1.05, -0.75)  # mirror spot reserved for BACK pads


def mm(x, y):
    return pcbnew.VECTOR2I_MM(x, y)


class Bitmap:
    def __init__(self, w, h):
        self.nx = int(w / RES) + 2
        self.ny = int(h / RES) + 2
        self.occ = bytearray(self.nx * self.ny)

    def mark_rect(self, x0, y0, x1, y1):
        for ix in range(max(0, int(x0 / RES)), min(self.nx, int(x1 / RES) + 1)):
            for iy in range(max(0, int(y0 / RES)), min(self.ny, int(y1 / RES) + 1)):
                self.occ[iy * self.nx + ix] = 1

    def free(self, x, y):
        ix, iy = int(x / RES), int(y / RES)
        if not (0 <= ix < self.nx and 0 <= iy < self.ny):
            return False
        return not self.occ[iy * self.nx + ix]


def main():
    board = pcbnew.LoadBoard(PCB)
    board.SetCopperLayerCount(4)
    nets = board.GetNetsByName()
    vss_c = nets["vss"].GetNetCode()
    vcc_c = nets["vcc"].GetNetCode()
    power = (vss_c, vcc_c)

    bbox = board.GetBoardEdgesBoundingBox()
    bw, bh = bbox.GetWidth() / 1e6, bbox.GetHeight() / 1e6
    for netname, layer in (("vss", pcbnew.In1_Cu), ("vcc", pcbnew.In2_Cu)):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(nets[netname])
        chain = pcbnew.SHAPE_LINE_CHAIN()
        for x, y in [(bbox.GetLeft(), bbox.GetTop()), (bbox.GetRight(), bbox.GetTop()),
                     (bbox.GetRight(), bbox.GetBottom()), (bbox.GetLeft(), bbox.GetBottom())]:
            chain.Append(x, y)
        chain.SetClosed(True)
        z.Outline().AddOutline(chain)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetLocalClearance(pcbnew.FromMM(0.25))
        z.SetMinThickness(pcbnew.FromMM(0.2))
        board.Add(z)

    front = Bitmap(bw, bh)      # static: pads, antenna
    back = Bitmap(bw, bh)
    front_d = Bitmap(bw, bh)    # dynamic: vias and stitch tracks
    back_d = Bitmap(bw, bh)
    pads_todo = []
    for fp in board.Footprints():
        dnp = fp.IsDNP()
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            x0 = bb.GetLeft() / 1e6 - INFLATE
            y0 = bb.GetTop() / 1e6 - INFLATE
            x1 = bb.GetRight() / 1e6 + INFLATE
            y1 = bb.GetBottom() / 1e6 + INFLATE
            pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            onF = pad.IsOnLayer(pcbnew.F_Cu)
            if pth or onF:
                front.mark_rect(x0, y0, x1, y1)
            if pth or not onF:
                back.mark_rect(x0, y0, x1, y1)
            if dnp or pth:
                continue
            if pad.GetNetCode() in power:
                pads_todo.append((pad, pad.GetNetCode(), onF))
    front.mark_rect(*ANTENNA)
    back.mark_rect(*ANTENNA)

    vias = []  # (x, y, code)

    def add_via(x, y, code):
        v = pcbnew.PCB_VIA(board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetPosition(mm(x, y))
        v.SetDrill(pcbnew.FromMM(VIA_DRILL))
        v.SetWidth(pcbnew.FromMM(VIA_DIA))
        v.SetNetCode(code)
        board.Add(v)
        vias.append((x, y, code))
        for bm in (front, back, front_d, back_d):
            bm.mark_rect(x - 0.55, y - 0.55, x + 0.55, y + 0.55)

    def add_track(x0, y0, x1, y1, code, layer):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(mm(x0, y0))
        t.SetEnd(mm(x1, y1))
        t.SetWidth(pcbnew.FromMM(TRACK_W))
        t.SetLayer(layer)
        t.SetNetCode(code)
        board.Add(t)
        bm = front_d if layer == pcbnew.F_Cu else back_d
        d = math.hypot(x1 - x0, y1 - y0)
        for i in range(int(d / 0.4) + 2):
            tt = min(1.0, i * 0.4 / max(d, 0.01))
            x, y = x0 + (x1 - x0) * tt, y0 + (y1 - y0) * tt
            bm.mark_rect(x - 0.6, y - 0.6, x + 0.6, y + 0.6)

    def seg_clear(bm, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(d / 0.12))
        for i in range(n + 1):
            t = i / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if math.hypot(x - x0, y - y0) < 1.1:
                continue  # inside/near own pad
            if math.hypot(x - x1, y - y1) < 0.65:
                continue  # via's own footprint
            if not bm.free(x, y):
                return False
        return True

    # spiral offsets sorted by distance, precomputed
    offs = sorted(((dx * RES, dy * RES)
                   for dx in range(-int(SEARCH_R / RES), int(SEARCH_R / RES) + 1)
                   for dy in range(-int(SEARCH_R / RES), int(SEARCH_R / RES) + 1)),
                  key=lambda o: o[0] * o[0] + o[1] * o[1])

    placed = shared = failed = 0
    spot_used = set()
    # LED cells break the spot construction (0603 pads reach the corner)
    for fp in board.Footprints():
        if fp.GetValue() == "LED_RED":
            p = fp.GetPosition()
            ci = int((p.x / 1e6 - CORE[0]) / PITCH[0])
            cj = int((p.y / 1e6 - CORE[1]) / PITCH[1])
            spot_used.add((ci, cj, True))
            spot_used.add((ci, cj, False))

    def in_core(x, y):
        return CORE[0] < x < CORE[2] and CORE[1] < y < CORE[3]

    def fallback(pad, code, onF, px, py):
        nonlocal placed, failed
        fpc = pad.GetParentFootprint().GetPosition()
        ci = int((fpc.x / 1e6 - CORE[0]) / PITCH[0])
        cj = int((fpc.y / 1e6 - CORE[1]) / PITCH[1])
        key = (ci, cj, onF)
        spot = SPOT_F if onF else SPOT_B
        vx = CORE[0] + (ci + 0.5) * PITCH[0] + spot[0]
        vy = CORE[1] + (cj + 0.5) * PITCH[1] + spot[1]
        bm_d = front_d if onF else back_d
        if key in spot_used or not bm_d.free(vx, vy):
            return False
        # opposite-face copper only matters where the Pico module sits;
        # elsewhere the grid construction guarantees radial clearance
        if 18.0 < vx < 63.0 and 60.0 < vy < 138.0:
            bm_opp = back if onF else front
            if not bm_opp.free(vx, vy):
                return False
        spot_used.add(key)
        layer = pcbnew.F_Cu if onF else pcbnew.B_Cu
        add_via(vx, vy, code)
        add_track(px, py, px, vy, code, layer)
        add_track(px, vy, vx, vy, code, layer)
        placed += 1
        return True

    def spiral(pad, code, onF, px, py):
        nonlocal placed, shared
        bm = front if onF else back
        bm_d = front_d if onF else back_d
        layer = pcbnew.F_Cu if onF else pcbnew.B_Cu
        for ox, oy in offs:
            if ox * ox + oy * oy < 0.8:
                continue
            vx, vy = px + ox, py + oy
            ok = True
            for bm2 in (front, back, front_d, back_d):
                for dx2, dy2 in ((0, 0), (-0.5, 0), (0.5, 0), (0, -0.5), (0, 0.5)):
                    if not bm2.free(vx + dx2, vy + dy2):
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                continue
            if not (seg_clear(bm, px, py, vx, vy) and seg_clear(bm_d, px, py, vx, vy)):
                continue
            add_via(vx, vy, code)
            add_track(px, py, vx, vy, code, layer)
            placed += 1
            return True
        return False

    # phase 1: every core pad claims its deterministic in-cell spot
    remaining = []
    for pad, code, onF in pads_todo:
        p = pad.GetPosition()
        px, py = p.x / 1e6, p.y / 1e6
        fpc = pad.GetParentFootprint().GetPosition()
        if in_core(fpc.x / 1e6, fpc.y / 1e6):
            if not fallback(pad, code, onF, px, py):
                remaining.append((pad, code, onF, px, py))
        else:
            remaining.append((pad, code, onF, px, py))
    # phase 2: periphery + the few core leftovers use the spiral search
    for pad, code, onF, px, py in remaining:
        if spiral(pad, code, onF, px, py):
            continue
        failed += 1
        print("WARN: no via spot for", pad.GetParentFootprint().GetReference(),
              pad.GetNumber(), round(px, 1), round(py, 1))

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.BuildConnectivity()
    print("vias placed:", placed, "| pads sharing a via:", shared, "| failed:", failed)
    print("remaining unconnected pad pairs:",
          board.GetConnectivity().GetUnconnectedCount(True))
    board.Save(PCB)


if __name__ == "__main__":
    main()
