#!/usr/bin/env python3
"""Reverse validation: rebuild the netlist from the copper itself.

Every other gate in this project reads forwards. `check_parity.py` asks "does
each pad carry the net the netlist assigns it?" and `check_gaps.py` groups
copper *by KiCad's net codes* and asks "is each intended net internally
connected?". Both therefore trust KiCad's connectivity bookkeeping, and
`check_gaps.py` never looks at zones at all -- the GND and VCC planes, which
carry every power connection on the board, are covered only by KiCad's own
unconnected count.

This tool throws all of that away. It reads the board, discards every net
label, and unions copper purely geometrically -- pads, tracks, vias and zone
fill polygons, with exact shape collision -- to find the conductors that
physically exist. Then it reports:

  1. LVS.  Each intended net should map to exactly one extracted conductor
     (else it is OPEN) and each conductor to exactly one intended net (else
     those nets are SHORTED). This is a complete statement in both directions
     and is independent of KiCad's connectivity engine.
  2. A netlist in switchsim's form, written to gen/extracted_netlist.json, so
     the copper can be made to execute 6502 instructions (`tools/switchsim.py`
     grows a third loader for it).

What is still assumed rather than proven, because copper cannot show it:
  * pad number -> device terminal (pad 1 of a SOT-323 is the gate). That comes
    from the footprint library, which the generator also used.
  * component values. 10k and 100k are the same copper. Switch-level
    simulation does not need them -- a pull-up is boolean -- so this costs
    nothing here, but it means this proves TOPOLOGY, not values.
  * the names of the ~60 nodes the simulation harness drives and reads. Those
    are anchored from gen/netlist.json by (ref, pad); the other ~2,600 nets are
    never consulted.

Run with KiCad's bundled python. Takes a few minutes.
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOARD = ROOT / "gen" / "board_routed_golden.kicad_pcb"
BOARD = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_BOARD)
# Only the golden board may write the canonical artifact -- pointing this at
# some other board (a damaged copy, an experiment) must never silently
# overwrite the netlist switchsim will then simulate as if it were the design.
OUT = (ROOT / "gen" / "extracted_netlist.json" if Path(BOARD) == DEFAULT_BOARD
       else ROOT / "gen" / ("extracted_%s.json" % Path(BOARD).stem))

CELL = 1_000_000        # spatial hash cell, 1 mm in nm
STEP = CELL // 2        # track rasterisation step

# names the switchsim harness drives or reads; anchored by (ref, pad)
WANT = (["vss", "vcc", "clk0", "rw", "sync", "res", "rdy", "irq", "nmi", "so"]
        + ["ab%d" % i for i in range(16)] + ["db%d" % i for i in range(8)]
        + ["a%d" % i for i in range(8)] + ["x%d" % i for i in range(8)]
        + ["y%d" % i for i in range(8)] + ["s%d" % i for i in range(8)]
        + ["pcl%d" % i for i in range(8)] + ["pch%d" % i for i in range(8)])


# ---------------------------------------------------------------- union-find

class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main():
    t0 = time.time()
    board = pcbnew.LoadBoard(BOARD)
    cu_layers = list(board.GetEnabledLayers().CuStack())
    print("board: %s\n%d copper layers %s" % (BOARD, len(cu_layers), cu_layers))

    # ---- 1. collect every piece of copper, with NO reference to its net ----
    kinds, objs, layersets, keys = [], [], [], []

    def add(kind, obj, layers, key=None):
        kinds.append(kind)
        objs.append(obj)
        layersets.append(layers)
        keys.append(key)
        return len(kinds) - 1

    for fp in board.Footprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            lay = [l for l in cu_layers if pad.IsOnLayer(l)]
            if lay:
                add("pad", pad, lay, (ref, pad.GetNumber()))
    for t in board.Tracks():
        if t.GetClass() == "PCB_VIA":
            # KiCad's copper layer IDs are NOT in stack order (B_Cu is 2, the
            # inner layers are 4..10), so a via's span has to be sliced out of
            # the board's own stack, never out of the numeric range.
            top, bot = t.TopLayer(), t.BottomLayer()
            try:
                a, b = cu_layers.index(top), cu_layers.index(bot)
            except ValueError:
                a, b = 0, len(cu_layers) - 1
            add("via", t, cu_layers[min(a, b):max(a, b) + 1])
        else:
            add("track", t, [t.GetLayer()])
    n = len(kinds)
    print("copper items: %d (%.1fs)" % (n, time.time() - t0))

    shape_cache = {}

    def shape(i, layer):
        s = shape_cache.get((i, layer))
        if s is None:
            s = objs[i].GetEffectiveShape(layer)
            shape_cache[(i, layer)] = s
        return s

    # ---- 2. spatial hash ----
    grid = defaultdict(list)

    def put(i, x, y):
        grid[(x // CELL, y // CELL)].append(i)

    for i in range(n):
        o = objs[i]
        if kinds[i] == "track":
            s, e = o.GetStart(), o.GetEnd()
            dx, dy = e.x - s.x, e.y - s.y
            steps = max(1, int(max(abs(dx), abs(dy)) // STEP))
            for k in range(steps + 1):
                put(i, s.x + dx * k // steps, s.y + dy * k // steps)
        else:
            bb = o.GetBoundingBox()
            x0, y0, x1, y1 = bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()
            cx, cy = x0 // CELL, y0 // CELL
            while cx <= x1 // CELL:
                cy = y0 // CELL
                while cy <= y1 // CELL:
                    grid[(cx, cy)].append(i)
                    cy += 1
                cx += 1
    print("grid cells: %d (%.1fs)" % (len(grid), time.time() - t0))

    # ---- 3. union touching copper, exact shape collision, per shared layer ----
    uf = UF(n + 64)                       # tail entries reserved for zones
    tested = set()
    pairs = hits = 0
    for cell, members in grid.items():
        if len(members) < 2:
            continue
        for ai in range(len(members)):
            i = members[ai]
            for bi in range(ai + 1, len(members)):
                j = members[bi]
                if i == j:
                    continue
                key = (i, j) if i < j else (j, i)
                if key in tested:
                    continue
                tested.add(key)
                shared = [l for l in layersets[i] if l in layersets[j]]
                if not shared:
                    continue
                pairs += 1
                if uf.find(i) == uf.find(j):
                    continue
                for l in shared:
                    if shape(i, l).Collide(shape(j, l), 0):
                        uf.union(i, j)
                        hits += 1
                        break
    print("pair tests: %d, touching: %d (%.1fs)" % (pairs, hits, time.time() - t0))

    # ---- 4. zones. A filled zone is a conductor too, and is exactly what
    #         connects the planes to every power pad and stitching via. ----
    # board.Zones() hands back NEW wrappers on every call, so the zone list is
    # taken once and indexed by position -- keying anything on id(z) matches
    # only by accidental address reuse (it silently dropped a whole plane).
    zones = list(board.Zones())
    zone_node = {}
    zone_names = {}
    zi = n
    for k, z in enumerate(zones):
        for l in z.GetLayerSet().Seq():
            polys = z.GetFilledPolysList(l)
            if not polys.OutlineCount():
                continue
            zone_node[(k, l)] = zi
            zone_names[zi] = (z.GetNetname(), l, polys.OutlineCount())
            zi += 1
    print("zone conductors: %d %s" % (len(zone_node), list(zone_names.values())))

    zhits = 0
    for k, z in enumerate(zones):
        for l in z.GetLayerSet().Seq():
            key = (k, l)
            if key not in zone_node:
                continue
            zn = zone_node[key]
            polys = z.GetFilledPolysList(l)
            bb = polys.BBox()
            for i in range(n):
                if l not in layersets[i]:
                    continue
                ib = objs[i].GetBoundingBox()
                if (ib.GetRight() < bb.GetLeft() or ib.GetLeft() > bb.GetRight()
                        or ib.GetBottom() < bb.GetTop() or ib.GetTop() > bb.GetBottom()):
                    continue
                # exact: does the item's copper actually overlap the fill?
                # a foreign-net via sits in a clearance hole and will not.
                if polys.Collide(shape(i, l), 0):
                    uf.union(zn, i)
                    zhits += 1
    print("zone attachments: %d (%.1fs)" % (zhits, time.time() - t0))

    # ---- 5. pads -> conductors ----
    node_of = {}
    for i in range(n):
        if kinds[i] == "pad":
            node_of[keys[i]] = uf.find(i)
    roots = {uf.find(i) for i in range(n)}
    print("conductors with copper: %d, pads mapped: %d" % (len(roots), len(node_of)))

    # ---- 6. LVS, both directions ----
    nl = json.loads((ROOT / "gen" / "netlist.json").read_text())
    comps = {c["ref"]: c for c in nl["components"]}
    intended = {}
    for ref, c in comps.items():
        for pnum, net in c["pins"].items():
            if net:
                intended[(ref, pnum)] = net

    net_to_nodes = defaultdict(set)
    node_to_nets = defaultdict(set)
    missing = []
    for k, net in intended.items():
        nd = node_of.get(k)
        if nd is None:
            missing.append(k)
            continue
        net_to_nodes[net].add(nd)
        node_to_nets[nd].add(net)

    opens = {k: v for k, v in net_to_nodes.items() if len(v) > 1}
    shorts = {k: v for k, v in node_to_nets.items() if len(v) > 1}
    print("\n--- LVS (copper vs intent) ---")
    print("intended nets: %d, pads on them: %d" % (len(net_to_nodes), len(intended)))
    print("pads not found on the board: %d" % len(missing))
    print("OPEN  (net split across conductors): %d" % len(opens))
    for k in list(opens)[:10]:
        print("   %s -> %d conductors" % (k, len(opens[k])))
    print("SHORT (conductor carrying several nets): %d" % len(shorts))
    for k in list(shorts)[:10]:
        print("   conductor %d -> %s" % (k, sorted(shorts[k])[:6]))

    # ---- 7. identify the rails from copper, not from labels ----
    # every pull-up in the design hangs off VCC, so the conductor touched by
    # ~1,000 resistor pads is VCC; the other plane conductor is VSS.
    res_pads = defaultdict(int)
    for ref, c in comps.items():
        if c["type"] != "resistor":
            continue
        for pnum in c["pins"]:
            nd = node_of.get((ref, pnum))
            if nd is not None:
                res_pads[nd] += 1
    vcc_node = max(res_pads, key=res_pads.get)
    zone_roots = {uf.find(v): zone_names[v] for v in zone_names}
    vss_candidates = [r for r in zone_roots if r != uf.find(vcc_node)]
    vss_node = vss_candidates[0] if vss_candidates else None
    print("\nrails derived from copper: VCC = conductor %d (%d resistor pads), "
          "VSS = conductor %d" % (vcc_node, res_pads[vcc_node], vss_node))
    print("   (labels on those zones say: %s)"
          % {zone_roots[r][0] for r in zone_roots})

    # ---- 8. emit a switchsim netlist built from the conductors ----
    fets, pullups = [], set()
    for ref, c in comps.items():
        if c["type"] == "fet":
            g = node_of.get((ref, "1"))
            a = node_of.get((ref, "3"))
            b = node_of.get((ref, "2"))
            if None in (g, a, b):
                continue
            fets.append((g, a, b))
        elif c["type"] == "resistor" and len(c["pins"]) == 2:
            ends = [node_of.get((ref, p)) for p in ("1", "2")]
            if vcc_node in ends and None not in ends:
                other = ends[0] if ends[1] == vcc_node else ends[1]
                if other != vcc_node:
                    pullups.add(other)

    names = {}
    for k, net in intended.items():
        if net in WANT and net not in names and k in node_of:
            names[net] = node_of[k]
    names["vcc"] = vcc_node
    if vss_node is not None:
        names["vss"] = vss_node
    missing_names = [w for w in WANT if w not in names]

    print("\nextracted: %d FETs, %d pull-up conductors, %d anchored names"
          % (len(fets), len(pullups), len(names)))
    if missing_names:
        print("names not anchored: %s" % missing_names[:12])

    OUT.write_text(json.dumps({
        "source_board": BOARD,
        "fets": fets,
        "pullups": sorted(pullups),
        "names": names,
        "conductors": len(roots),
        "lvs": {"opens": len(opens), "shorts": len(shorts), "missing_pads": len(missing)},
    }))
    print("wrote %s (%.1fs)" % (OUT, time.time() - t0))

    bad = len(opens) + len(shorts) + len(missing)
    print("\nEXTRACTION %s" % ("CLEAN" if bad == 0 else "PROBLEMS: %d" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
