#!/usr/bin/env python3
"""Which nodes hold their state as charge, and which of them holds it worst.

Dynamic NMOS stores a bit as charge on a wire's own capacitance. That gives the
clock a LOWER frequency bound as well as the upper one already measured in
`sim/fanout_speed.sp`: refresh the node too late and the bit has leaked away.

A node is dynamic here if it has no pull-up resistor (a pull-up holds it
statically) and it drives at least one gate (otherwise nothing reads it). Its
retention time is roughly

    t = C * dV / I_leak
    C      ~ gates_driven * Ciss          (27 pF for BSS138W)
    I_leak ~ channels_touching * I_DSS    (off pass/pull-down FETs)
             + gates_driven * I_GSS       (gate leakage)

Both C and I grow with fanout, so they partly cancel and the worst case is a
LOW-fanout node touched by several FET channels -- not the big obvious nets.
This finds it by name instead of guessing.

Leakage figures are per-part and can only be bounded here; the datasheet max
and the typical value are three orders of magnitude apart, which is exactly
why this prints a table over a leakage range rather than a single number.
Run: python3 tools/dynamic_nodes.py
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CISS = 27e-12       # BSS138W input capacitance, datasheet
CTRACE = 5e-12      # rough allowance for the copper itself
DV = 1.0            # volts of droop tolerated before the next stage mis-reads
IGSS = 1e-10        # gate leakage, typical (spec max is +-100 nA)
# drain-source leakage per off FET: typical .. datasheet max
IDSS_CASES = [("typical 1 nA", 1e-9), ("10 nA", 1e-8),
              ("100 nA", 1e-7), ("datasheet max 500 nA", 5e-7)]


def main():
    d = json.loads((ROOT / "gen" / "netlist.json").read_text())

    gates = defaultdict(int)     # net -> FET gates it drives  (capacitive load)
    channels = defaultdict(int)  # net -> FET channel terminals on it (leak paths)
    pullup = set()
    for c in d["components"]:
        p = c["pins"]
        if c["type"] == "fet":
            gates[p["1"]] += 1
            channels[p["2"]] += 1
            channels[p["3"]] += 1
        elif c["type"] == "resistor" and c.get("role") == "pullup":
            pullup.add(p["2"])

    rails = {"vcc", "vss"}
    dynamic = []
    for net, ng in gates.items():
        if net in rails or net in pullup or ng == 0:
            continue
        nc = channels.get(net, 0)
        if nc == 0:
            continue  # nothing can drive or leak it; not a storage node
        cap = ng * CISS + CTRACE
        dynamic.append((net, ng, nc, cap))

    print("nets: %d, with pull-ups: %d, dynamic storage nodes: %d"
          % (len(d["nets"]), len(pullup), len(dynamic)))

    print("\nretention of the WORST node, by assumed per-FET leakage")
    print("%-22s %-12s %-12s %s" % ("I_DSS assumed", "worst node", "retention",
                                    "=> clock floor"))
    for label, idss in IDSS_CASES:
        worst = min(dynamic, key=lambda r: r[3] / (r[2] * idss + r[1] * IGSS))
        net, ng, nc, cap = worst
        ileak = nc * idss + ng * IGSS
        t = cap * DV / ileak
        # a bit must survive a whole clock period to be refreshed
        print("%-22s %-12s %-12s %s"
              % (label, net, fmt_t(t), fmt_f(1.0 / t)))

    print("\nthe 10 nodes least able to hold charge (at 1 nA/FET):")
    idss = 1e-9
    ranked = sorted(dynamic, key=lambda r: r[3] / (r[2] * idss + r[1] * IGSS))
    print("%-16s %6s %9s %10s %10s" % ("node", "gates", "channels", "C", "retention"))
    for net, ng, nc, cap in ranked[:10]:
        t = cap * DV / (nc * idss + ng * IGSS)
        print("%-16s %6d %9d %9.0fpF %10s" % (net, ng, nc, cap * 1e12, fmt_t(t)))

    # sanity: the biggest nodes are the safest, and should look it
    big = max(dynamic, key=lambda r: r[1])
    t = big[3] * DV / (big[2] * idss + big[1] * IGSS)
    print("\nfor contrast, the highest-fanout dynamic node: %s "
          "(%d gates, %d channels, %.0f pF) holds for %s"
          % (big[0], big[1], big[2], big[3] * 1e12, fmt_t(t)))

    # The number that actually decides whether the board works: the floor must
    # stay below the measured ceiling, or there is no operating window at all.
    print("\n--- operating window ---")
    net, ng, nc, cap = min(dynamic, key=lambda r: r[3] / (r[2] * 1e-9 + r[1] * IGSS))
    for rail, ceiling in (("5 V", 20e3), ("3.3 V", 10e3)):
        # t_hold = 1/ceiling  =>  I_max = C*dV*ceiling
        imax = cap * DV * ceiling
        per_fet = (imax - ng * IGSS) / nc
        # leakage roughly doubles every 10 C; how much rise from 1 nA typical?
        headroom = 10.0 * (log2(per_fet / 1e-9)) if per_fet > 1e-9 else 0.0
        print("%-6s ceiling %5.0f kHz (fanout-limited)  =>  worst node %s must "
              "leak < %s per FET" % (rail, ceiling / 1000, net, fmt_i(per_fet)))
        print("       that is %.0fx the 1 nA typical figure, i.e. about %.0f C "
              "of temperature rise before the window closes" %
              (per_fet / 1e-9, headroom))


def log2(x):
    import math
    return math.log(x, 2)


def fmt_i(i):
    if i >= 1e-6:
        return "%.1f uA" % (i * 1e6)
    if i >= 1e-9:
        return "%.0f nA" % (i * 1e9)
    return "%.1f pA" % (i * 1e12)


def fmt_t(t):
    for scale, unit in ((1.0, "s"), (1e-3, "ms"), (1e-6, "us")):
        if t >= scale:
            return "%.1f %s" % (t / scale, unit)
    return "%.1f ns" % (t * 1e9)


def fmt_f(f):
    if f >= 1000:
        return "%.1f kHz" % (f / 1000)
    if f >= 1:
        return "%.1f Hz" % f
    return "%.3f Hz" % f


if __name__ == "__main__":
    main()
