#!/usr/bin/env python3
"""Generate the discrete6502 discrete netlist from the visual6502 data.

Input:  data/visual6502/{transdefs,segdefs,nodenames}.js
Output: gen/netlist.json        canonical transformed netlist
        gen/discrete6502.net   KiCad s-expression netlist (import into pcbnew)
        stats on stdout

Transforms (decisions of 2026-07-18, see cards/):
  - drop always-off transistors (gate = vss) and no-op transistors (c1 = c2)
  - merge exact parallel duplicates (same gate + channel pair)
  - pull-down / vcc-side transistors -> single 2N7002 (source on the low side)
  - pass transistors (channel touches neither rail) -> back-to-back 2N7002 pair,
    drains outward, common source 'mid' node, both gates on the original gate net
  - each '+'-flagged node -> 10k pull-up resistor to vcc
  - LED taps on registers/counters (A,X,Y,S,P flags,PCL,PCH): gate-tap 2N7002
    sinking LED + resistor from vcc (no DC load on the dynamic node)
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "visual6502"
GEN = ROOT / "gen"

# The part is really JSCJ **BSS138W** (verified on LCSC: SOT-323, 50 V, 220 mA,
# Ciss 27 pF, Vgs(th) 1.5 V -- the figures every sim here assumes). "BSS138K" is
# a naming error made at order time; the prose docs are corrected, but this
# string is DELIBERATELY left alone because it becomes the BOM's Comment field,
# and changing it would alter gen/fab/discrete6502_bom.csv whose sha256 is
# pinned in gen/fab/RELEASE.md and already uploaded to JLCPCB. JLC matches on
# the LCSC code, so the comment text has no effect on what gets fitted.
FET_VALUE, FET_LCSC = "BSS138K", "C504052"
FET_FOOTPRINT = "Package_TO_SOT_SMD:SOT-323_SC-70"
PULLUP_VALUE, PULLUP_LCSC = "10k", "C25744"

# ---------------------------------------------------------------------------
# REV B: series resistors on the VCC-side FETs.
#
# Ratioed NMOS needs the pull-down several times stronger than its load. The
# 1,018 depletion loads became 10k resistors, so their ratio is right. The
# enhancement-mode VCC-side FETs did NOT get that treatment and kept the same
# BSS138W as their pull-down -- a 1:1 ratio where the die had a deliberately
# weak load. Measured consequence (sim/driver_contention.sp): 262 mA and 0.90 W
# per contended net at 5 V, and a "low" sitting at 1.0-1.9 V against a 1.1-1.5 V
# receiver threshold. See "Driver contention" in project-plan.md.
#
# Applied only where a pull-down exists on the same net: 22 of the 164 VCC-side
# nets have none, so contention there is impossible and a resistor would be dead
# weight. 142 sites get one.
#
# OFF BY DEFAULT. Rev A is fabricated and gen/netlist.json is what the golden
# board and the released fab package were built from; changing it silently
# would break check_parity and the RELEASE.md fingerprints. Enable with
#     DISCRETE6502_REV_B=1 python3 tools/gen_netlist.py
# which is also how a rev B board would be generated.
REV_B = os.environ.get("DISCRETE6502_REV_B") == "1"

# A blanket 10k would be wrong: cclk carries 482 gates (13 nF) and cp1 198
# (5.4 nF), where 10k would give a 286 us rise against a 25 us half-cycle and
# destroy the clock. So size per net from its own gate load, keeping the RC
# rise inside SERIES_R_RISE_BUDGET, and snap to values ALREADY IN THE BOM so
# rev B needs no new part numbers.
CISS_F = 27e-12               # BSS138W input capacitance per driven gate
SERIES_R_RISE_BUDGET = 5e-6   # 20% of a 25 us half-cycle at the 20 kHz ceiling
SERIES_R_CHOICES = (          # largest first; picked if it meets the budget
    (10000.0, "10k", "C25744"),
    (1000.0, "1k", "C11702"),
    (100.0, "100R", "C25076"),
)


def series_r_for(gate_count):
    """Largest in-BOM resistor whose RC rise still fits the budget."""
    cap = gate_count * CISS_F
    limit = SERIES_R_RISE_BUDGET / (2.2 * cap) if cap else float("inf")
    for ohms, value, lcsc in SERIES_R_CHOICES:
        if ohms <= limit:
            return value, lcsc
    return SERIES_R_CHOICES[-1][1], SERIES_R_CHOICES[-1][2]

R_FOOTPRINT = "Resistor_SMD:R_0402_1005Metric"
LED_R_VALUE, LED_R_LCSC = "2.2k", "C25879"
LED_VALUE, LED_LCSC = "LED_RED", "C2286"
LED_FOOTPRINT = "LED_SMD:LED_0603_1608Metric"

# external 6502 bus interface (must all resolve to nets)
EXTERNAL = (
    ["ab%d" % i for i in range(16)] + ["db%d" % i for i in range(8)]
    + ["clk0", "clk1out", "clk2out", "res", "rdy", "irq", "nmi", "rw", "sync", "so", "vss", "vcc"]
)
# LED-monitored registers/counters (bit-node name patterns)
LED_GROUPS = {
    "A": ["a%d" % i for i in range(8)],
    "X": ["x%d" % i for i in range(8)],
    "Y": ["y%d" % i for i in range(8)],
    "S": ["s%d" % i for i in range(8)],
    "PCL": ["pcl%d" % i for i in range(8)],
    "PCH": ["pch%d" % i for i in range(8)],
    # 6502 P register flags (bit 5 has no storage)
    "P": ["p0", "p1", "p2", "p3", "p4", "p6", "p7"],
}


def parse_inputs():
    trans_txt = (DATA / "transdefs.js").read_text()
    trans = []
    for m in re.findall(
        r"\[\s*'(t\d+)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*\[([^\]]*)\]",
        trans_txt,
    ):
        bb = [int(v) for v in m[4].split(",")]
        pos = ((bb[0] + bb[1]) / 2, (bb[2] + bb[3]) / 2)  # die coords
        trans.append((m[0], int(m[1]), int(m[2]), int(m[3]), pos))
    seg_txt = (DATA / "segdefs.js").read_text()
    pullup_nodes = {int(m[1]) for m in re.finditer(r"\[\s*(\d+)\s*,\s*'\+'", seg_txt)}
    names_txt = (DATA / "nodenames.js").read_text()
    name_to_node = {
        k: int(v) for k, v in re.findall(r"([A-Za-z0-9_]+)\s*:\s*(\d+),", names_txt)
    }
    return trans, pullup_nodes, name_to_node


def main():
    trans, pullup_nodes, name_to_node = parse_inputs()
    vss, vcc = name_to_node["vss"], name_to_node["vcc"]
    node_to_name = {}
    for name, node in sorted(name_to_node.items(), key=lambda kv: (len(kv[0]), kv[0])):
        node_to_name.setdefault(node, name)

    def net(node):
        return node_to_name.get(node, "n%d" % node)

    stats = defaultdict(int)
    stats["parsed"] = len(trans)

    # drop no-ops and always-off, merge duplicates
    seen = set()
    kept = []
    node_pos = defaultdict(list)  # node -> die positions of touching transistors
    for tid, g, c1, c2, pos in trans:
        if c1 == c2:
            stats["dropped_noop_c1_eq_c2"] += 1
            continue
        if g == vss:
            stats["dropped_always_off_gate_vss"] += 1
            continue
        key = (g, frozenset((c1, c2)))
        if key in seen:
            stats["merged_parallel_dup"] += 1
            continue
        seen.add(key)
        kept.append((tid, g, c1, c2, pos))
        for n in (g, c1, c2):
            node_pos[n].append(pos)

    components = []  # dicts: ref,type,value,lcsc,footprint,pins{padnum:netname},role,origin

    qn = rn = dn = cn = 0

    def add_fet(role, origin, gate_net, drain_net, source_net, pos=None):
        nonlocal qn
        qn += 1
        components.append(
            dict(ref="Q%d" % qn, type="fet", value=FET_VALUE, lcsc=FET_LCSC,
                 footprint=FET_FOOTPRINT, role=role, origin=origin, pos=pos,
                 pins={"1": gate_net, "2": source_net, "3": drain_net}))

    def add_r(role, origin, value, lcsc, net_a, net_b, pos=None):
        nonlocal rn
        rn += 1
        components.append(
            dict(ref="R%d" % rn, type="resistor", value=value, lcsc=lcsc,
                 footprint=R_FOOTPRINT, role=role, origin=origin, pos=pos,
                 pins={"1": net_a, "2": net_b}))

    def add_c(role, origin, value, lcsc, footprint, net_a, net_b, pos=None, dnp=False):
        nonlocal cn
        cn += 1
        components.append(
            dict(ref="C%d" % cn, type="capacitor", value=value, lcsc=lcsc,
                 footprint=footprint, role=role, origin=origin, pos=pos, dnp=dnp,
                 pins={"1": net_a, "2": net_b}))

    def centroid(node):
        pts = node_pos.get(node)
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    # How many gates does each net drive? Needed to size the rev B series
    # resistors, and cheap to compute from the kept transistor list.
    gate_load = defaultdict(int)
    has_pulldown = set()
    for tid, g, c1, c2, pos in kept:
        gate_load[net(g)] += 1
        if vss in (c1, c2):
            other = c2 if c1 == vss else c1
            has_pulldown.add(net(other))

    for tid, g, c1, c2, pos in kept:
        gnet = net(g)
        if vss in (c1, c2):
            other = c2 if c1 == vss else c1
            add_fet("pulldown", tid, gnet, net(other), net(vss), pos)
            stats["fet_pulldown"] += 1
        elif vcc in (c1, c2):
            other = c2 if c1 == vcc else c1
            if REV_B and net(other) in has_pulldown:
                # VCC --[R]-- mid --(FET)-- other, restoring the load ratio.
                # Only where a pull-down exists to fight: 22 of the 164 VCC-side
                # nets have none, so they can never contend and a resistor there
                # would be 22 pointless parts and 22 more nets to route.
                mid = "%s_vs" % tid
                value, lcsc = series_r_for(gate_load.get(net(other), 0))
                add_r("vcc_series", tid, value, lcsc, net(vcc), mid, pos)
                add_fet("vcc_side", tid, gnet, mid, net(other), pos)
                stats["vcc_series_resistors"] += 1
            else:
                if REV_B:
                    stats["vcc_side_no_pulldown_skipped"] += 1
                add_fet("vcc_side", tid, gnet, net(vcc), net(other), pos)
            stats["fet_vcc_side"] += 1
        else:
            mid = "%s_mid" % tid
            add_fet("pass_a", tid, gnet, net(c1), mid, pos)
            add_fet("pass_b", tid, gnet, net(c2), mid, pos)
            stats["pass_pairs"] += 1

    for node in sorted(pullup_nodes):
        if node in (vss, vcc):
            continue
        add_r("pullup", "node%d" % node, PULLUP_VALUE, PULLUP_LCSC,
              net(vcc), net(node), centroid(node))
        stats["pullup_resistors"] += 1

    missing_led_nodes = []
    for group, names in LED_GROUPS.items():
        for name in names:
            if name not in name_to_node:
                missing_led_nodes.append(name)
                continue
            dn += 1
            cathode = "led_%s_k" % name  # driver drain -- LED cathode
            anode = "led_%s_a" % name    # resistor -- LED anode
            bitpos = centroid(name_to_node[name])
            components.append(
                dict(ref="D%d" % dn, type="led", value=LED_VALUE, lcsc=LED_LCSC,
                     footprint=LED_FOOTPRINT, role="led_%s" % group, origin=name,
                     pos=bitpos, pins={"1": cathode, "2": anode}))
            add_r("led_limit", name, LED_R_VALUE, LED_R_LCSC,
                  net(name_to_node["vcc"]), anode, bitpos)
            add_fet("led_driver", name, name, cathode, net(vss), bitpos)
            stats["leds"] += 1

    # ---- board periphery ----
    vccn, vssn = net(vcc), net(vss)
    for i in range(96):  # distributed decoupling
        add_c("decoupling", "dist%d" % i, "100nF", "C1525",
              "Capacitor_SMD:C_0402_1005Metric", vccn, vssn)
    for i in range(4):    # bulk at power entry
        add_c("bulk", "bulk%d" % i, "10uF", "C15850",
              "Capacitor_SMD:C_0805_2012Metric", vccn, vssn)

    # DNP ballast caps on internal buses (bring-up insurance vs. edge injection)
    for prefix in ("sb", "idb", "adl", "adh", "db", "ab"):
        width = 16 if prefix == "ab" else 8
        for i in range(width):
            name = "%s%d" % (prefix, i)
            if name in name_to_node:
                add_c("ballast_dnp", name, "100pF-DNP", "",
                      "Capacitor_SMD:C_0402_1005Metric", net(name_to_node[name]),
                      vssn, centroid(name_to_node[name]), dnp=True)
                stats["ballast_dnp"] += 1

    # input protection: connector-side <name>_ext --100R--> <name>, clamped to rails
    PROTECT_R_LCSC = "C25076"
    for name in ("res", "irq", "nmi", "rdy", "so", "clk0"):
        add_r("input_protect", name, "100R", PROTECT_R_LCSC, "%s_ext" % name, name)
        for suffix, k, a in (("up", vccn, name), ("dn", name, vssn)):
            dn += 1
            components.append(
                dict(ref="D%d" % dn, type="diode", value="1N4148WS", lcsc="C2128",
                     footprint="Diode_SMD:D_SOD-323", role="clamp_%s" % suffix,
                     origin=name, pos=None, pins={"1": k, "2": a}))
        stats["protected_inputs"] += 1

    # bond pad ring: one 4x4mm THT pad per 6502 signal at the *actual die
    # bond-pad position* (farthest vertex of the node's segdefs polygons from
    # die center) — croc-clip-able from the back, visible metal on the front.
    seg_txt = (DATA / "segdefs.js").read_text()
    node_verts = defaultdict(list)
    wanted_nodes = {name_to_node[n] for n in EXTERNAL}
    for m in re.finditer(r"\[\s*(\d+)\s*,\s*'[+-]'\s*,\s*\d+\s*,([0-9.,\s]+)\]", seg_txt):
        node = int(m.group(1))
        if node not in wanted_nodes:
            continue
        vals = [float(v) for v in m.group(2).split(",") if v.strip()]
        node_verts[node].extend(zip(vals[0::2], vals[1::2]))

    all_pos = [p for ps in node_pos.values() for p in ps]
    dcx = sum(p[0] for p in all_pos) / len(all_pos)
    dcy = sum(p[1] for p in all_pos) / len(all_pos)

    def bond_pos(node):
        verts = node_verts.get(node)
        if not verts:
            return None
        return max(verts, key=lambda v: (v[0] - dcx) ** 2 + (v[1] - dcy) ** 2)

    tp = 0
    PROTECTED = ("res", "irq", "nmi", "rdy", "so", "clk0")
    for name in EXTERNAL:
        node = name_to_node[name]
        tp += 1
        netname = "%s_ext" % name if name in PROTECTED else name
        components.append(
            dict(ref="TP%d" % tp, type="testpoint", value=name.upper(),
                 lcsc="", footprint="TestPoint:TestPoint_THTPad_4.0x4.0mm_Drill2.0mm",
                 role="edge_pad", origin=name,
                 pos=bond_pos(node) or centroid(node),
                 pins={"1": netname}))
        stats["edge_pads"] += 1

    # pull-ups so the CPU runs standalone with nothing connected
    for name in ("res", "irq", "nmi", "rdy", "so"):
        add_r("input_pullup", name, PULLUP_VALUE, PULLUP_LCSC,
              net(vcc), "%s_ext" % name)
        stats["input_pullups"] += 1

    # U1: unpopulated Raspberry Pi Pico W site on the underside (aftermarket
    # interface). 26 signals = exactly the Pico's GPIO count, each through a
    # DNP 1k series resistor (5V bus vs 3.3V RP2040 — populate with care or
    # use level shifters). Remaining signals stay on the bond-pad ring.
    GPIO_SIGNALS = (["db%d" % i for i in range(8)]           # GP0-7
                    + ["ab%d" % i for i in range(14)]        # GP8-21
                    + ["clk0_ext", "res_ext", "rw", "sync"])  # GP22,26,27,28
    GPIO_PINS = [1, 2, 4, 5, 6, 7, 9, 10,                    # GP0-7
                 11, 12, 14, 15, 16, 17, 19, 20, 21, 22, 24, 25, 26, 27,  # GP8-21
                 29, 31, 32, 34]                             # GP22,26,27,28
    upins = {}
    for pin, sig in zip(GPIO_PINS, GPIO_SIGNALS):
        piconet = "pico_p%d" % pin
        upins[str(pin)] = piconet
        rn += 1
        components.append(
            dict(ref="R%d" % rn, type="resistor", value="1k", lcsc="C11702",
                 footprint=R_FOOTPRINT, role="pico_series", origin=sig,
                 pos=None, dnp=False, pins={"1": sig, "2": piconet}))
    for pin in (3, 8, 13, 18, 23, 28, 33, 38):  # GND
        upins[str(pin)] = vssn
    upins["39"] = vccn  # VSYS (1.8-5.5V input)
    for pin in (30, 35, 36, 37, 40):  # RUN, ADC_VREF, 3V3_OUT, 3V3_EN, VBUS
        upins[str(pin)] = "nc%d" % pin
    components.append(
        dict(ref="U1", type="module", value="Pico2_W_site", lcsc="",
             footprint="Module:RaspberryPi_Pico_W_SMD",
             role="pico_site", origin="pico", pos=None, dnp=True, pins=upins))

    # ---- iterative cleanup: drop FETs whose drain or source net is floating
    # (degree-1, non-external) — spare/dummy die structures do nothing here ----
    while True:
        nets = defaultdict(list)
        for c in components:
            for pad, netname in c["pins"].items():
                nets[netname].append((c["ref"], pad))
        doomed = set()
        for c in components:
            if c["type"] == "resistor" and c.get("role") == "vcc_series":
                # REV B: a series resistor whose FET has just been dropped for a
                # floating channel would be left dangling on its own mid node.
                # Let it die in the same fixed point (one real case: t1322).
                if len(nets[c["pins"]["2"]]) == 1:
                    doomed.add(c["ref"])
                continue
            if c["type"] != "fet":
                continue
            for pad in ("2", "3"):  # source, drain
                netname = c["pins"][pad]
                if len(nets[netname]) == 1 and netname not in EXTERNAL:
                    doomed.add(c["ref"])
        if not doomed:
            break
        stats["dropped_floating_channel"] += len(doomed)
        components = [c for c in components if c["ref"] not in doomed]

    # ---- sanity checks ----
    nets = defaultdict(list)
    for c in components:
        for pad, netname in c["pins"].items():
            nets[netname].append((c["ref"], pad))
    singletons = [n for n, pins in nets.items()
                  if len(pins) < 2 and not n.startswith(("ab", "db", "nc"))]
    missing_external = [n for n in EXTERNAL if n not in nets]

    print("=== gen_netlist stats ===")
    for k in sorted(stats):
        print("%-28s %d" % (k, stats[k]))
    print("%-28s %d" % ("components_total", len(components)))
    print("%-28s %d" % ("nets_total", len(nets)))
    print("%-28s %s" % ("missing_external_nets", missing_external or "none"))
    print("%-28s %s" % ("missing_led_nodes", missing_led_nodes or "none"))
    print("%-28s %d %s" % ("singleton_nets", len(singletons), singletons[:8]))

    GEN.mkdir(exist_ok=True)
    (GEN / "netlist.json").write_text(json.dumps(
        dict(meta=dict(source="visual6502", stats=dict(stats),
                       fet=dict(value=FET_VALUE, lcsc=FET_LCSC)),
             components=components,
             nets={n: pins for n, pins in nets.items()}), indent=1))

    # ---- KiCad netlist ----
    def sx(s):
        return '"%s"' % s

    out = ["(export (version \"E\")", " (components"]
    for c in components:
        out.append(
            '  (comp (ref %s) (value %s) (footprint %s)\n'
            '   (fields (field (name "LCSC") %s) (field (name "role") %s))\n'
            '   (property (name "origin") (value %s)))'
            % (sx(c["ref"]), sx(c["value"]), sx(c["footprint"]),
               sx(c["lcsc"]), sx(c["role"]), sx(str(c["origin"]))))
    out.append(" )\n (nets")
    for code, (netname, pins) in enumerate(sorted(nets.items()), 1):
        nodes = " ".join(
            "(node (ref %s) (pin %s))" % (sx(ref), sx(pad)) for ref, pad in pins)
        out.append("  (net (code %d) (name %s) %s)" % (code, sx(netname), nodes))
    out.append(" )\n)")
    (GEN / "discrete6502.net").write_text("\n".join(out))
    print("wrote gen/netlist.json and gen/discrete6502.net")
    return 0 if not missing_external else 1


if __name__ == "__main__":
    sys.exit(main())
