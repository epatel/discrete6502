#!/usr/bin/env python3
"""Model the Step 1 VCC-VSS measurement, and interpret the readings taken on the
real boards.

Step 1 of the bring-up asks for the resistance between a VCC bond pad and a VSS
bond pad on an unpowered board. The guide's original gate ("must read high") is
wrong: there is no resistive path between the rails at all, so the meter is
reading a *junction*, and what it displays depends on the range selected. This
tool derives that from the netlist and checks it against the measured numbers.

    python3 tools/step1_model.py

Nothing here touches the board or the fab package; it is analysis only.
"""
import collections
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NETLIST = ROOT / "gen" / "netlist.json"

# onsemi 2N7002 body diode, sim/2N7002_onsemi.lib DbodyMOD. The fitted part is
# JSCJ BSS138W; same class of device, and only the log of IS matters here.
IS = 5.05e-14
N = 1.0
VT = 0.025852          # kT/q at ~300 K
R_PULLUP = 10000.0

# Measured 2026-08-12 on board #1, Biltema 2000018521 handheld DMM, manual range.
# "forward" = red probe on VSS (the direction the body diodes conduct).
# "reverse" = red probe on VCC (which is also the normal operating polarity).
MEASURED = [
    ("200",  195.0,   None),   # reverse read OL (over range)
    ("2000", 314.0,   595.0),
    ("20k",  3770.0,  8210.0),
]


def load_branches():
    """Nets reachable from VSS through a body diode and on to VCC through a pull-up.

    Every pull-down FET has its source on VSS and its drain on a node; the body
    diode is anode-on-source, so it conducts VSS -> drain. If that drain carries
    a 10k pull-up, the pair forms a VSS -> VCC branch. Returns {n_diodes: n_nets}.
    """
    d = json.loads(NETLIST.read_text())
    comps = d["components"]

    pulled_up = {
        n
        for c in comps
        if c.get("role") == "pullup"
        for n in set(c["pins"].values()) - {"vcc"}
    }
    per_net = collections.Counter()
    for c in comps:
        if c["type"] != "fet":
            continue
        p = c["pins"]
        if p.get("2") == "vss" and p.get("3") in pulled_up:
            per_net[p["3"]] += 1
    return collections.Counter(per_net.values()), len(per_net), sum(per_net.values())


def no_resistive_path():
    """True if VCC and VSS are not joined by resistors alone."""
    d = json.loads(NETLIST.read_text())
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c in d["components"]:
        if c["type"] == "resistor":
            nets = list(c["pins"].values())
            for n in nets[1:]:
                a, b = find(nets[0]), find(n)
                if a != b:
                    parent[a] = b
    return find("vcc") != find("vss")


def current_at(volts, groups):
    """Total VSS->VCC current at a given terminal voltage."""
    total = 0.0
    for ndio, nnets in groups.items():
        lo, hi = 0.0, volts
        for _ in range(80):                      # solve vd + i*R = volts
            vd = (lo + hi) / 2
            i = ndio * IS * (math.exp(min(vd / (N * VT), 700)) - 1)
            if vd + i * R_PULLUP < volts:
                lo = vd
            else:
                hi = vd
        vd = (lo + hi) / 2
        total += nnets * ndio * IS * (math.exp(min(vd / (N * VT), 700)) - 1)
    return total


def volts_at(current, groups):
    lo, hi = 0.0, 3.0
    for _ in range(80):
        v = (lo + hi) / 2
        if current_at(v, groups) < current:
            lo = v
        else:
            hi = v
    return (lo + hi) / 2


def implied_current(displayed_ohms, groups):
    """The test current a range must be sourcing to display this many ohms."""
    lo, hi = 1e-7, 5e-2
    for _ in range(120):
        i = math.sqrt(lo * hi)
        if volts_at(i, groups) / i > displayed_ohms:
            lo = i
        else:
            hi = i
    return math.sqrt(lo * hi)


def main():
    groups, n_nets, n_diodes = load_branches()

    print("Topology, from gen/netlist.json")
    print(f"  resistor-only path between VCC and VSS ... {'NONE' if no_resistive_path() else 'EXISTS'}")
    print(f"  VSS->VCC branches (body diode + 10k) .... {n_nets} nets, {n_diodes} body diodes")
    print(f"  pull-ups in parallel ................... {R_PULLUP / n_nets:.2f} ohm behind the diodes")
    print(f"  nets by body-diode count ............... {dict(sorted(groups.items()))}")

    print("\nPredicted display, forward direction (red on VSS)")
    print(f"  {'test current':>14} | {'volts across board':>18} | {'meter shows':>12}")
    for ma in (0.1, 0.5, 1.0, 2.0, 5.0):
        v = volts_at(ma * 1e-3, groups)
        print(f"  {ma:11.1f} mA | {v:15.3f} V | {v / (ma * 1e-3):9.0f} ohm")

    print("\nMeasured, board #1, 2026-08-12 — forward calibrates the meter")
    print(f"  {'range':>6} | {'forward':>9} | {'implied Itest':>13} | {'volts':>7} | {'reverse':>9} | {'volts':>7}")
    rev_points = []
    for rng, fwd, rev in MEASURED:
        i = implied_current(fwd, groups)
        v = volts_at(i, groups)
        if rev is None:
            print(f"  {rng:>6} | {fwd:8.0f}R | {i * 1e3:10.3f} mA | {v:5.3f} V | {'OL':>9} | {'—':>7}")
        else:
            vr = i * rev
            rev_points.append((vr, i))
            print(f"  {rng:>6} | {fwd:8.0f}R | {i * 1e3:10.3f} mA | {v:5.3f} V | {rev:8.0f}R | {vr:5.3f} V")

    print("\nReverse direction (red on VCC) — is it a junction or a fault?")
    if len(rev_points) >= 2:
        (v1, i1), (v2, i2) = sorted(rev_points)
        decades = math.log10(i2 / i1)
        slope = (v2 - v1) / decades
        ideal = math.log(10) * N * VT
        print(f"  {v1:.3f} V -> {i1 * 1e6:7.1f} uA")
        print(f"  {v2:.3f} V -> {i2 * 1e6:7.1f} uA")
        print(f"  slope ................ {slope * 1e3:5.1f} mV/decade")
        print(f"  ideal junction slope . {ideal * 1e3:5.1f} mV/decade  (n = {slope / ideal:.2f})")
        print("  => exponential, not ohmic. A resistive fault has no slope.")

    print("\nCaveat: the meter's per-range test currents are inferred from the forward")
    print("readings, not measured. The conclusions that do not depend on them are that")
    print("the display changes with range at all, and the 200-range polarity asymmetry.")


if __name__ == "__main__":
    main()
