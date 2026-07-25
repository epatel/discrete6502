#!/usr/bin/env python3
"""Stage 3 v2: negotiated-congestion signal router (PathFinder-style).

The greedy router (route_signals.py) saturated at ~46% -- congestion
collapse, not a capacity wall. This driver restores the pre-signal
snapshot, extracts the obstacle grid + net pads, hands them to the C core
(tools/route_nc.c: route through conflicts, iteratively penalize shared
cells and rip-up/reroute conflicted nets until no cell is shared), then
emits the resulting tracks/vias into the board.

Grid semantics identical to route_signals.py v13 (G=0.3, single-cell
stamping, via ring checks, stubs + junction anchor-bridges).

Run with KiCad's bundled python, after route_power.py. Verify with
tools/check_gaps.py -- never trust the router's own tally alone.
"""
import json
import math
import shutil
import subprocess
import sys
import time
from array import array
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")
SNAP = str(ROOT / "gen" / "board_presignal.kicad_pcb")

# 0.127/0.127 (5 mil) rules -- within JLCPCB 4-layer standard capability.
# G=0.26: track pitch grid, adjacent cells = 0.133 gap >= 0.127 legal spacing.
# G=0.13 (env ROUTE_NC_G): fine grid -- C core runs SCALE=2 body/halo
# stamping (different nets >= 2 cells apart), halved quantization loss.
# INFLATE = clearance 0.127 + half-track 0.0635 + margin.
import os
G = float(os.environ.get("ROUTE_NC_G", "0.26"))
TRACK_W = 0.127
VIA_DRILL, VIA_DIA = 0.2, 0.45
INFLATE = 0.2

SCRATCH = ROOT / "gen"
BIN_IN = SCRATCH / "route_nc_in.bin"
BIN_OUT = SCRATCH / "route_nc_out.bin"
CBIN = SCRATCH / "route_nc"


def main():
    t0 = time.time()
    shutil.copyfile(SNAP, PCB)  # always start from the pre-signal snapshot
    board = pcbnew.LoadBoard(PCB)
    ncopper = board.GetDesignSettings().GetCopperLayerCount()
    # routing layers: 0=F.Cu [,1=In2,2=In3] ,last=B.Cu
    RL = 4 if ncopper >= 6 else 2
    KLAYERS = ((pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu)
               if RL == 4 else (pcbnew.F_Cu, pcbnew.B_Cu))
    BOT = RL - 1
    lidx = {k: i for i, k in enumerate(KLAYERS)}
    print("copper layers: %d -> %d routing layers" % (ncopper, RL), flush=True)
    bbox = board.GetBoardEdgesBoundingBox()
    W = int(bbox.GetWidth() / 1e6 / G) + 2
    H = int(bbox.GetHeight() / 1e6 / G) + 2
    NL = W * H
    blocked = [bytearray(NL) for _ in range(RL)]

    def cell(x, y):
        return int(y / G) * W + int(x / G)

    def mark(layer, x0, y0, x1, y1, val=1):
        iy0 = max(0, math.ceil(y0 / G - 0.5))
        iy1 = min(H - 1, math.floor(y1 / G - 0.5))
        ix0 = max(0, math.ceil(x0 / G - 0.5))
        ix1 = min(W - 1, math.floor(x1 / G - 0.5))
        for iy in range(iy0, iy1 + 1):
            base = iy * W
            for ix in range(ix0, ix1 + 1):
                blocked[layer][base + ix] = val

    def rect_cells(layer, x0, y0, x1, y1):
        out = []
        iy0 = max(0, math.ceil(y0 / G - 0.5))
        iy1 = min(H - 1, math.floor(y1 / G - 0.5))
        ix0 = max(0, math.ceil(x0 / G - 0.5))
        ix1 = min(W - 1, math.floor(x1 / G - 0.5))
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                out.append(layer * NL + iy * W + ix)
        return out

    nets_pads = defaultdict(list)
    vss_c = board.GetNetsByName()["vss"].GetNetCode()
    vcc_c = board.GetNetsByName()["vcc"].GetNetCode()

    pad_rects = []  # (layers, rect) -- marked AFTER the hard mask snapshot
    for fp in board.Footprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            r = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                 bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            onF = pad.IsOnLayer(pcbnew.F_Cu)
            onB = pad.IsOnLayer(pcbnew.B_Cu)
            layers = (tuple(range(RL)) if pth
                      else ((0,) if onF else ()) + ((BOT,) if onB else ()))
            if not layers:
                continue  # paste/mask-only pads (Pico anchors) have no copper
            pad_rects.append((layers, r))
            code = pad.GetNetCode()
            if code > 0:
                p = pad.GetPosition()
                nets_pads[code].append((p.x / 1e6, p.y / 1e6, layers, r))

    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            x, y = p.x / 1e6, p.y / 1e6
            rr = t.GetWidth() / 2e6
            for L in range(RL):
                mark(L, x - rr - INFLATE, y - rr - INFLATE, x + rr + INFLATE, y + rr + INFLATE)
        else:
            s, e = t.GetStart(), t.GetEnd()
            L = lidx.get(t.GetLayer(), 0 if t.GetLayer() == pcbnew.F_Cu else BOT)
            hw = t.GetWidth() / 2e6 + INFLATE
            sx, sy = s.x / 1e6, s.y / 1e6
            ex, ey = e.x / 1e6, e.y / 1e6
            if abs(sx - ex) < 1e-6 or abs(sy - ey) < 1e-6:
                x0, x1 = sorted((sx, ex))
                y0, y1 = sorted((sy, ey))
                mark(L, x0 - hw, y0 - hw, x1 + hw, y1 + hw)
            else:
                # diagonal: rasterize along the line -- the bounding rect of a
                # long diagonal over-blocks a huge area (sealed real pads)
                n = max(1, int(math.hypot(ex - sx, ey - sy) / (G / 2)))
                for i in range(n + 1):
                    x = sx + (ex - sx) * i / n
                    y = sy + (ey - sy) * i / n
                    mark(L, x - hw, y - hw, x + hw, y + hw)
    # keepouts: use the board's real rule-area zones (the Pico library's RF /
    # antenna keepouts), NOT the oversized layout_params antenna rect -- that
    # rect sealed four Pico pads that the real zones don't cover
    nko = 0
    allzones = list(board.Zones())
    for fp in board.Footprints():  # footprint-embedded keepouts (the Pico's)
        allzones.extend(fp.Zones())
    for z in allzones:
        if not z.GetIsRuleArea() or not z.GetDoNotAllowTracks():
            continue
        zb = z.GetBoundingBox()
        # keepouts (RF/antenna) apply to ALL routing layers regardless of the
        # zone's declared layer list -- inner-layer copper under an antenna
        # is just as bad
        for L in range(RL):
            mark(L, zb.GetLeft() / 1e6 - INFLATE, zb.GetTop() / 1e6 - INFLATE,
                 zb.GetRight() / 1e6 + INFLATE, zb.GetBottom() / 1e6 + INFLATE)
            nko += 1
    print("keepout zones marked:", nko, flush=True)
    for L in range(RL):
        mark(L, 0, 0, bbox.GetWidth() / 1e6, 1.0)
        mark(L, 0, 0, 1.0, bbox.GetHeight() / 1e6)
        mark(L, 0, bbox.GetHeight() / 1e6 - 1.0, bbox.GetWidth() / 1e6, bbox.GetHeight() / 1e6)
        mark(L, bbox.GetWidth() / 1e6 - 1.0, 0, bbox.GetWidth() / 1e6, bbox.GetHeight() / 1e6)

    # snapshot the NON-PAD obstacle mask: carve must never release these
    # cells (a pad's carve rect can overlap a power stitch via's protection
    # ring -- routing then hugs the via: 350 clearance violations' worth)
    hard = [bytes(b) for b in blocked]
    for layers, r in pad_rects:
        for L in layers:
            mark(L, r[0] - INFLATE, r[1] - INFLATE, r[2] + INFLATE, r[3] + INFLATE)

    netlist = [(code, pads) for code, pads in nets_pads.items()
               if code not in (vss_c, vcc_c) and len(pads) >= 2]
    netlist.sort(key=lambda np: len(np[1]))
    total_conns = sum(len(p) - 1 for _, p in netlist)
    print("nets: %d, connections: %d, grid %dx%d" %
          (len(netlist), total_conns, W, H), flush=True)

    # ---- serialize for the C core ----
    anchors = {}  # (netcode, idx) -> pad center
    out = array("i", [W, H, len(netlist)])
    blob = b"".join(bytes(b) for b in blocked)
    body = array("i")
    for code, pads in netlist:
        body.append(len(pads))
        for x, y, layers, r in pads:
            body.append(layers[0] * NL + cell(x, y))
            # goal cells strictly INSIDE the pad copper (shrunk by 0.1) so the
            # off-grid stubs grid-point->pad-center always run over the net's
            # own pad -- stubs grazing neighboring power vias caused 150+
            # clearance violations when goals could sit at the pad edge
            SH = 0.1
            rs = (r[0] + SH, r[1] + SH, r[2] - SH, r[3] - SH)
            if rs[2] - rs[0] < G or rs[3] - rs[1] < G:
                rs = r  # pad too small to shrink; keep full rect
            goal = []
            for L in layers:
                iy0 = max(0, math.ceil(rs[1] / G - 0.5))
                iy1 = min(H - 1, math.floor(rs[3] / G - 0.5))
                ix0 = max(0, math.ceil(rs[0] / G - 0.5))
                ix1 = min(W - 1, math.floor(rs[2] / G - 0.5))
                if iy1 < iy0 or ix1 < ix0:  # degenerate: center cell only
                    iy0 = iy1 = min(H - 1, max(0, int(y / G)))
                    ix0 = ix1 = min(W - 1, max(0, int(x / G)))
                for iy in range(iy0, iy1 + 1):
                    for ix in range(ix0, ix1 + 1):
                        idx = L * NL + iy * W + ix
                        goal.append(idx)
                        anchors[(code, idx)] = (x, y)
            body.append(len(goal))
            body.extend(goal)
            carve = []
            for L in layers:
                carve.extend(idx for idx in
                             rect_cells(L, r[0] - INFLATE, r[1] - INFLATE,
                                        r[2] + INFLATE, r[3] + INFLATE)
                             if not hard[idx // NL][idx % NL])
            body.append(len(carve))
            body.extend(carve)
    with open(BIN_IN, "wb") as f:
        out.tofile(f)
        f.write(blob)
        body.tofile(f)
    print("wrote %s (%.1f MB), %.0fs" %
          (BIN_IN, BIN_IN.stat().st_size / 1e6, time.time() - t0), flush=True)

    # ---- compile + run the C core (streams its own progress) ----
    csrc = ROOT / "tools" / "route_nc.c"
    if not CBIN.exists() or CBIN.stat().st_mtime < csrc.stat().st_mtime:
        subprocess.run(["cc", "-O3", "-o", str(CBIN), str(csrc)], check=True)
        print("compiled route_nc", flush=True)
    os.environ["ROUTE_NC_SCALE"] = "2" if G < 0.2 else "1"
    os.environ["ROUTE_NC_LAYERS"] = str(RL)
    os.environ.setdefault("ROUTE_NC_CAP", "16000000" if G < 0.2 else "4000000")
    rc = subprocess.run([str(CBIN), str(BIN_IN), str(BIN_OUT),
                         str(SCRATCH / "route_nc_over.txt")]).returncode
    if rc != 0:
        print("route_nc failed rc=%d" % rc)
        sys.exit(1)

    # ---- read paths back and emit ----
    data = array("i")
    with open(BIN_OUT, "rb") as f:
        data.frombytes(f.read())
    pos = 0
    nn = data[pos]; pos += 1
    assert nn == len(netlist)

    LAYERS = KLAYERS

    def seg(x0, y0, x1, y1, L, code):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I_MM(x0, y0))
        t.SetEnd(pcbnew.VECTOR2I_MM(x1, y1))
        t.SetWidth(pcbnew.FromMM(TRACK_W))
        t.SetLayer(LAYERS[L])
        t.SetNetCode(code)
        board.Add(t)

    def emit(pts, code, endpoints):
        (sx, sy), (tx, ty) = endpoints
        if abs(pts[0][1] - sx) > 0.01 or abs(pts[0][2] - sy) > 0.01:
            seg(sx, sy, pts[0][1], pts[0][2], pts[0][0], code)
        if abs(pts[-1][1] - tx) > 0.01 or abs(pts[-1][2] - ty) > 0.01:
            seg(pts[-1][1], pts[-1][2], tx, ty, pts[-1][0], code)
        i = 0
        while i < len(pts) - 1:
            L = pts[i][0]
            j = i + 1
            while j < len(pts) and pts[j][0] == L:
                j += 1
            run = pts[i:j]
            k = 0
            while k < len(run) - 1:
                m = k + 1
                if run[m][1] == run[k][1]:
                    while m < len(run) - 1 and run[m + 1][1] == run[k][1]:
                        m += 1
                elif run[m][2] == run[k][2]:
                    while m < len(run) - 1 and run[m + 1][2] == run[k][2]:
                        m += 1
                seg(run[k][1], run[k][2], run[m][1], run[m][2], L, code)
                k = m
            if j < len(pts):
                v = pcbnew.PCB_VIA(board)
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetPosition(pcbnew.VECTOR2I_MM(run[-1][1], run[-1][2]))
                v.SetDrill(pcbnew.FromMM(VIA_DRILL))
                v.SetWidth(pcbnew.FromMM(VIA_DIA))
                v.SetNetCode(code)
                board.Add(v)
            i = j

    ok = fail = 0
    fails = []
    for code, pads in netlist:
        nrec = data[pos]; pos += 1
        for _ in range(nrec):
            pi = data[pos]; plen = data[pos + 1]; pos += 2
            path = data[pos:pos + plen]; pos += plen
            if plen == 0:
                fail += 1
                fails.append(dict(net=board.FindNet(code).GetNetname(),
                                  a=(pads[pi][0], pads[pi][1], pads[pi][2][0])))
                continue
            pts = []
            for idx in path:
                L, c = idx // NL, idx % NL
                cy, cx = divmod(c, W)
                pts.append((L, (cx + 0.5) * G, (cy + 0.5) * G))
            a = anchors.get((code, path[-1]))
            jx, jy = pts[-1][1], pts[-1][2]
            emit(pts, code, ((pads[pi][0], pads[pi][1]), a if a else (jx, jy)))
            ok += 1

    print("emitted %d connections, %d failed, %.0fs" %
          (ok, fail, time.time() - t0), flush=True)
    (ROOT / "gen" / "route_failures.json").write_text(json.dumps(fails[:4000]))

    # sync design rules to the 0.127 track/clearance actually routed
    pro = ROOT / "gen" / "discrete6502.kicad_pro"
    pj = json.loads(pro.read_text())
    for c in pj.get("net_settings", {}).get("classes", []):
        c["clearance"] = 0.127
        c["track_width"] = 0.127
    pj.setdefault("board", {}).setdefault("design_settings", {}) \
      .setdefault("rules", {})["min_clearance"] = 0.127
    pro.write_text(json.dumps(pj, indent=2))

    bds = board.GetDesignSettings()
    bds.m_MinClearance = pcbnew.FromMM(0.127)
    bds.m_TrackMinWidth = pcbnew.FromMM(0.12)
    bds.m_ViasMinSize = pcbnew.FromMM(0.4)
    bds.m_MinThroughDrill = pcbnew.FromMM(0.15)
    for rule in ("DRCE_OVERLAPPING_FOOTPRINTS", "DRCE_OVERLAPPING_SILK",
                 "DRCE_SILK_CLEARANCE", "DRCE_PTH_IN_COURTYARD",
                 "DRCE_SOLDERMASK_BRIDGE"):
        code2 = getattr(pcbnew, rule, None)
        if code2 is not None:
            bds.m_DRCSeverities[code2] = pcbnew.RPT_SEVERITY_IGNORE
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    print("unconnected after routing:",
          board.GetConnectivity().GetUnconnectedCount(True), flush=True)
    board.Save(PCB)
    print("saved", flush=True)


if __name__ == "__main__":
    main()
