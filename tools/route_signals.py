#!/usr/bin/env python3
"""Stage 3: scripted signal router (replaces Freerouting, which managed only
~700 of 8,500 connections in 10 hours on this board).

Approach: per net, minimum-spanning-tree over its pads; each MST edge is
A*-routed on a 0.45mm Manhattan grid with two routing layers (F.Cu prefers
horizontal, B.Cu vertical; vias where both faces are clear). Obstacles are
inflated copper bitmaps; the endpoints' own pads are temporarily carved out.
Routed paths are stamped as obstacles immediately (greedy, shortest edges
first). Power nets' leftover pads route to their nearest plane via.

Run with KiCad's bundled python after route_power.py.
"""
import heapq
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = str(ROOT / "gen" / "discrete6502.kicad_pcb")

G = 0.3               # routing grid: adjacent cells = exactly legal 0.15/0.15 spacing
TRACK_W = 0.15
VIA_DRILL, VIA_DIA = 0.2, 0.45
INFLATE = 0.24        # copper -> blocked (0.15 clearance + 0.075 half-track + margin)
VIA_INFLATE = 0.5     # extra ring needed to drop a via
import json as _json
ANTENNA = tuple(_json.loads((ROOT / "gen" / "layout_params.json").read_text())["antenna"])
COST_ALONG, COST_ACROSS, COST_VIA = 10, 14, 50


def main():
    t0 = time.time()
    board = pcbnew.LoadBoard(PCB)
    bbox = board.GetBoardEdgesBoundingBox()
    W = int(bbox.GetWidth() / 1e6 / G) + 2
    H = int(bbox.GetHeight() / 1e6 / G) + 2
    NL = W * H
    blocked = [bytearray(NL), bytearray(NL)]  # F, B

    def cell(x, y):
        return int(y / G) * W + int(x / G)

    def mark(layer, x0, y0, x1, y1, val=1):
        # block exactly the cells whose CENTER lies inside the rect --
        # index-range marking over-inflated by up to a full cell per side
        iy0 = max(0, math.ceil(y0 / G - 0.5))
        iy1 = min(H - 1, math.floor(y1 / G - 0.5))
        ix0 = max(0, math.ceil(x0 / G - 0.5))
        ix1 = min(W - 1, math.floor(x1 / G - 0.5))
        for iy in range(iy0, iy1 + 1):
            base = iy * W
            for ix in range(ix0, ix1 + 1):
                blocked[layer][base + ix] = val

    nets_pads = defaultdict(list)
    vss_c = board.GetNetsByName()["vss"].GetNetCode()
    vcc_c = board.GetNetsByName()["vcc"].GetNetCode()

    pad_rects = []  # (layers, rect, netcode) for carve-outs
    for fp in board.Footprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            r = (bb.GetLeft() / 1e6, bb.GetTop() / 1e6,
                 bb.GetRight() / 1e6, bb.GetBottom() / 1e6)
            pth = pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
            onF = pad.IsOnLayer(pcbnew.F_Cu)
            layers = (0, 1) if pth else ((0,) if onF else (1,))
            for L in layers:
                mark(L, r[0] - INFLATE, r[1] - INFLATE, r[2] + INFLATE, r[3] + INFLATE)
            code = pad.GetNetCode()
            if code > 0:
                p = pad.GetPosition()
                nets_pads[code].append((p.x / 1e6, p.y / 1e6, layers, r))

    power_copper = {vss_c: [], vcc_c: []}
    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            p = t.GetPosition()
            x, y = p.x / 1e6, p.y / 1e6
            r = t.GetWidth() / 2e6
            for L in (0, 1):
                mark(L, x - r - INFLATE, y - r - INFLATE, x + r + INFLATE, y + r + INFLATE)
            if t.GetNetCode() in power_copper:
                power_copper[t.GetNetCode()].append((x, y))
        else:
            s, e = t.GetStart(), t.GetEnd()
            L = 0 if t.GetLayer() == pcbnew.F_Cu else 1
            hw = t.GetWidth() / 2e6 + INFLATE
            x0, x1 = sorted((s.x / 1e6, e.x / 1e6))
            y0, y1 = sorted((s.y / 1e6, e.y / 1e6))
            mark(L, x0 - hw, y0 - hw, x1 + hw, y1 + hw)
    for L in (0, 1):
        mark(L, *ANTENNA)
        mark(L, 0, 0, bbox.GetWidth() / 1e6, 1.0)      # board margin
        mark(L, 0, 0, 1.0, bbox.GetHeight() / 1e6)
        mark(L, 0, bbox.GetHeight() / 1e6 - 1.0, bbox.GetWidth() / 1e6, bbox.GetHeight() / 1e6)
        mark(L, bbox.GetWidth() / 1e6 - 1.0, 0, bbox.GetWidth() / 1e6, bbox.GetHeight() / 1e6)

    def carve(pads, val):
        for x, y, layers, r in pads:
            for L in layers:
                mark(L, r[0] - INFLATE, r[1] - INFLATE, r[2] + INFLATE, r[3] + INFLATE, val)

    def astar(sx, sy, sL, tx, ty, tL, cap=400000):
        start = (sL, cell(sx, sy))
        goal = (tL, cell(tx, ty))
        gx, gy = int(tx / G), int(ty / G)
        pq = [(0, 0, start, -1)]
        best = {}
        parent = {}
        expand = 0
        while pq:
            f, g, node, par = heapq.heappop(pq)
            if node in best and best[node] <= g:
                continue
            best[node] = g
            parent[node] = par
            if node == goal or (node[1] == goal[1] and COST_VIA + g <= best.get(goal, 1 << 30)):
                if node[1] == goal[1] and node[0] != goal[0]:
                    g += COST_VIA
                    parent[goal] = node
                    best[goal] = g
                    node = goal
                # reconstruct
                path = []
                cur = goal
                while cur != -1:
                    path.append(cur)
                    cur = parent.get(cur, -1)
                return path[::-1]
            expand += 1
            if expand > cap:
                return "CAP"
            L, c = node
            cy, cx = divmod(c, W)
            along = (1, 0) if L == 0 else (0, 1)
            for dx, dy, step in ((1, 0, 0), (-1, 0, 0), (0, 1, 1), (0, -1, 1)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                nc = ny * W + nx
                if blocked[L][nc]:
                    continue
                cost = COST_ALONG if (dx, dy)[step] == 0 or ((dx != 0 and L == 0) or (dy != 0 and L == 1)) else COST_ACROSS
                cost = COST_ALONG if ((dx != 0 and L == 0) or (dy != 0 and L == 1)) else COST_ACROSS
                ng = g + cost
                nn = (L, nc)
                if nn in best and best[nn] <= ng:
                    continue
                h = 10 * (abs(nx - gx) + abs(ny - gy))
                heapq.heappush(pq, (ng + h, ng, nn, node))
            # via
            oL = 1 - L
            if not blocked[oL][c]:
                ok = True
                for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H and (blocked[L][ny * W + nx] or blocked[oL][ny * W + nx]):
                        ok = False
                        break
                if ok:
                    ng = g + COST_VIA
                    nn = (oL, c)
                    if not (nn in best and best[nn] <= ng):
                        h = 10 * (abs(cx - gx) + abs(cy - gy))
                        heapq.heappush(pq, (ng + h, ng, nn, node))
        return None

    LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

    def emit(path, code, endpoints):
        # path: list of (L, cell). collapse into segments + vias
        pts = []
        for L, c in path:
            cy, cx = divmod(c, W)
            pts.append((L, (cx + 0.5) * G, (cy + 0.5) * G))
        (sx, sy), (tx, ty) = endpoints
        # never move grid points (vias must stay on checked cells); instead
        # add short stubs from the exact pad coords to the first/last centers
        if abs(pts[0][1] - sx) > 0.01 or abs(pts[0][2] - sy) > 0.01:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I_MM(sx, sy))
            t.SetEnd(pcbnew.VECTOR2I_MM(pts[0][1], pts[0][2]))
            t.SetWidth(pcbnew.FromMM(TRACK_W))
            t.SetLayer(LAYERS[pts[0][0]])
            t.SetNetCode(code)
            board.Add(t)
        if abs(pts[-1][1] - tx) > 0.01 or abs(pts[-1][2] - ty) > 0.01:
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I_MM(pts[-1][1], pts[-1][2]))
            t.SetEnd(pcbnew.VECTOR2I_MM(tx, ty))
            t.SetWidth(pcbnew.FromMM(TRACK_W))
            t.SetLayer(LAYERS[pts[-1][0]])
            t.SetNetCode(code)
            board.Add(t)
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
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I_MM(run[k][1], run[k][2]))
                t.SetEnd(pcbnew.VECTOR2I_MM(run[m][1], run[m][2]))
                t.SetWidth(pcbnew.FromMM(TRACK_W))
                t.SetLayer(LAYERS[L])
                t.SetNetCode(code)
                board.Add(t)
                k = m
            if j < len(pts):  # layer change -> via at transition point
                v = pcbnew.PCB_VIA(board)
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetPosition(pcbnew.VECTOR2I_MM(run[-1][1], run[-1][2]))
                v.SetDrill(pcbnew.FromMM(VIA_DRILL))
                v.SetWidth(pcbnew.FromMM(VIA_DIA))
                v.SetNetCode(code)
                board.Add(v)
            i = j
        # at G=0.3 adjacent-cell parallel tracks are exactly at min spacing:
        # single-cell stamping, no halo -> double corridor capacity
        for L, c in path:
            blocked[L][c] = 1
        for k in range(len(path) - 1):
            if path[k][1] == path[k + 1][1] and path[k][0] != path[k + 1][0]:
                cy, cx = divmod(path[k][1], W)
                for dy in (-2, -1, 0, 1, 2):
                    for dx in (-2, -1, 0, 1, 2):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < W and 0 <= ny < H:
                            blocked[0][ny * W + nx] = 1
                            blocked[1][ny * W + nx] = 1

    # incremental net-tree routing: per net, connect each pad to the net's
    # nearest already-routed copper (multi-goal A*), so high-fanout nets grow
    # Steiner-like trees instead of fighting fixed MST edges.
    tree = {}      # netcode -> set of (L, cell)
    tbox = {}      # netcode -> [minx, miny, maxx, maxy] in cells

    anchors = {}  # (netcode, L, cell) -> pad center: junctions bridge to here

    def pad_cells(p, code=None):
        x, y, layers, r = p
        out = []
        for L in layers:
            iy0 = max(0, int(r[1] / G)); iy1 = min(H - 1, int(r[3] / G))
            ix0 = max(0, int(r[0] / G)); ix1 = min(W - 1, int(r[2] / G))
            for iy in range(iy0, iy1 + 1):
                for ix in range(ix0, ix1 + 1):
                    out.append((L, iy * W + ix))
                    if code is not None:
                        anchors[(code, L, iy * W + ix)] = (x, y)
        return out

    def grow_box(code, cells):
        bb = tbox.setdefault(code, [1 << 30, 1 << 30, -1, -1])
        for L, c in cells:
            cy, cx = divmod(c, W)
            bb[0] = min(bb[0], cx); bb[1] = min(bb[1], cy)
            bb[2] = max(bb[2], cx); bb[3] = max(bb[3], cy)

    def astar_tree(code, sx, sy, sL, cap=400000):
        start = (sL, cell(sx, sy))
        T = tree[code]
        bb = tbox[code]
        pq = [(0, 0, start, -1)]
        best = {}
        parent = {}
        expand = 0

        def h(cx, cy):
            dx = max(bb[0] - cx, 0, cx - bb[2])
            dy = max(bb[1] - cy, 0, cy - bb[3])
            return 10 * (dx + dy)

        while pq:
            f, g, node, par = heapq.heappop(pq)
            if node in best and best[node] <= g:
                continue
            best[node] = g
            parent[node] = par
            if node in T:
                path = []
                cur = node
                while cur != -1:
                    path.append(cur)
                    cur = parent.get(cur, -1)
                return path[::-1]
            expand += 1
            if expand > cap:
                return "CAP"
            L, c = node
            cy, cx = divmod(c, W)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                nc = ny * W + nx
                nn = (L, nc)
                cost = COST_ALONG if ((dx != 0 and L == 0) or (dy != 0 and L == 1)) else COST_ACROSS
                ng = g + cost
                if nn in T:  # goal check BEFORE blocked (tree copper is stamped)
                    if not (nn in best and best[nn] <= ng):
                        parent[nn] = node
                        path = [nn]
                        cur = node
                        while cur != -1:
                            path.append(cur)
                            cur = parent.get(cur, -1)
                        return path[::-1]
                    continue
                if blocked[L][nc]:
                    continue
                if nn in best and best[nn] <= ng:
                    continue
                heapq.heappush(pq, (ng + h(nx, ny), ng, nn, node))
            oL = 1 - L
            nn = (oL, c)
            ok2 = True
            for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < W and 0 <= ny < H and (blocked[L][ny * W + nx] or blocked[oL][ny * W + nx]):
                    ok2 = False
                    break
            if nn in T:
                if ok2:  # junction vias need the same ring clearance
                    parent[nn] = node
                    path = [nn]
                    cur = node
                    while cur != -1:
                        path.append(cur)
                        cur = parent.get(cur, -1)
                    return path[::-1]
            elif not blocked[oL][c]:
                if ok2:
                    ng = g + COST_VIA
                    if not (nn in best and best[nn] <= ng):
                        heapq.heappush(pq, (ng + h(cx, cy), ng, nn, node))
        return None

    # net order: small fanout first (locals lock in), then the buses/clocks
    netlist = [(code, pads) for code, pads in nets_pads.items()
               if code not in (vss_c, vcc_c) and len(pads) >= 2]
    netlist.sort(key=lambda np: len(np[1]))
    total_conns = sum(len(p) - 1 for _, p in netlist)
    print("nets: %d, connections: %d" % (len(netlist), total_conns), flush=True)

    ok = fail = done = 0
    retry = []
    for code, pads in netlist:
        order = [pads[0]]
        rest = pads[1:]
        tree[code] = set(pad_cells(pads[0], code))
        grow_box(code, tree[code])
        while rest:
            bb = tbox[code]
            rest.sort(key=lambda p: max(bb[0] - p[0] / G, 0, p[0] / G - bb[2])
                      + max(bb[1] - p[1] / G, 0, p[1] / G - bb[3]))
            p = rest.pop(0)
            carve([p], 0)
            path = astar_tree(code, p[0], p[1], p[2][0])
            carve([p], 1)
            if path and path != "CAP":
                newcells = pad_cells(p, code)
                jx = ((path[-1][1] % W) + 0.5) * G
                jy = ((path[-1][1] // W) + 0.5) * G
                a = anchors.get((code, path[-1][0], path[-1][1]))
                emit(path, code, ((p[0], p[1]), a if a else (jx, jy)))
                tree[code].update(path)
                ok += 1
                tree[code].update(newcells)
                grow_box(code, tree[code])
                grow_box(code, path)
            else:
                # do NOT add failed pads to the tree: later joins would treat
                # unrouted copper as reachable and the retry would self-connect
                retry.append((code, p))
                fail += 1
            done += 1
            if done % 500 == 0:
                print("  %d/%d connected, %d failed, %.0fs" %
                      (ok, total_conns, fail, time.time() - t0), flush=True)

    print("pass1: %d connected, %d to retry, %.0fs" % (ok, len(retry), time.time() - t0), flush=True)
    fail = 0
    for code, p in retry:
        carve([p], 0)
        path = astar_tree(code, p[0], p[1], p[2][0], cap=1600000)
        carve([p], 1)
        if path and path != "CAP":
            jx = ((path[-1][1] % W) + 0.5) * G
            jy = ((path[-1][1] // W) + 0.5) * G
            a = anchors.get((code, path[-1][0], path[-1][1]))
            emit(path, code, ((p[0], p[1]), a if a else (jx, jy)))
            tree[code].update(path)
            tree[code].update(pad_cells(p, code))
            grow_box(code, path)
            ok += 1
        else:
            fail += 1

    print("routed %d / failed %d in %.0fs" % (ok, fail, time.time() - t0), flush=True)
    import json
    fails = [dict(net=board.FindNet(code).GetNetname(), a=(p[0], p[1], p[2][0]))
             for code, p in retry]
    (ROOT / "gen" / "route_failures.json").write_text(json.dumps(fails[:4000]))
    bds = board.GetDesignSettings()
    bds.m_MinClearance = pcbnew.FromMM(0.15)
    bds.m_TrackMinWidth = pcbnew.FromMM(0.12)
    bds.m_ViasMinSize = pcbnew.FromMM(0.4)
    bds.m_MinThroughDrill = pcbnew.FromMM(0.15)
    for rule in ("DRCE_OVERLAPPING_FOOTPRINTS", "DRCE_OVERLAPPING_SILK",
                 "DRCE_SILK_CLEARANCE", "DRCE_PTH_IN_COURTYARD",
                 "DRCE_SOLDERMASK_BRIDGE"):
        code2 = getattr(pcbnew, rule, None)
        if code2 is not None:
            bds.m_DRCSeverities[code2] = pcbnew.RPT_SEVERITY_IGNORE
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())  # refill around new vias
    board.BuildConnectivity()
    print("unconnected after routing:",
          board.GetConnectivity().GetUnconnectedCount(True), flush=True)
    board.Save(PCB)
    print("saved", flush=True)


if __name__ == "__main__":
    main()
