#!/usr/bin/env python3
"""Measure how much of the time each VCC-side FET is fighting its pull-down.

WHY THIS EXISTS. `switchsim.py` proves topology and is structurally incapable of
seeing a ratio error: `_value()` returns low the moment vss is in the conduction
group, i.e. it *assumes* the pull-down wins. That assumption is what let the
1:1-ratio defect pass five green gates (cards/verification.md). Contention is
still visible in the same model, just not through the value: a net is contended
when its VCC-side FET is on AND its group reaches vss at the same instant. That
is what this measures.

It also answers a question the thermal record left open. On 2026-08-24 a FLIR
image of board #1 found no localised hot spot and the driver-contention model
was retracted as a result. On 2026-08-25 the same board, running a real program
through the Pico, showed discrete 80 C spots on the adh3..adh7 precharge
drivers. Both observations can be true if the duty cycle depends on what the CPU
is executing -- so this runs TWO workloads and compares:

  real   switchsim's own test program (stack, JSR, ADC, branches)
  nop    an all-$EA memory, which is the NOP free-run the 2026-08-24
         measurement was actually made under

Usage:  python3 tools/contention_duty.py [--halves 400] [--top 25]

CAVEAT, ADDED 2026-08-26 -- READ BEFORE TRUSTING A NUMBER FROM THIS TOOL.
Duty here is ADDRESS-dependent, and a short run pins the address. `adh` IS the
high byte of the address during a fetch, so a bit that happens to be high is not
being pulled low and reads 0% -- not because it never contends, but because it
did not contend at that address. A 300-half-cycle run holds PCH at one value the
whole time. Run with the reset vector at $EA (the default NOP image) and
adh1/3/5/6/7 read 0.3%; run it at $0000 and all eight read 48%, because $EA has
those bits set and $00 does not. Hardware settled it on 2026-08-26: under a real
NOP free-run every adh site runs hot, and adh6/adh7 visibly cycle at 3.3 s and
6.6 s -- exactly the rate those PCH bits toggle. Treat a low figure as "quiet at
this address", never as "quiet".
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import switchsim  # noqa: E402


def build_indexed():
    """switchsim.load_transformed() rebuilt so we keep the component->fet index
    map. The fet list is appended in component order, so the mapping is exact
    rather than reconstructed by matching nets (which would be ambiguous where
    parallel devices share a channel pair)."""
    d = json.loads((ROOT / "gen" / "netlist.json").read_text())
    netid = {}

    def nid(name):
        if name not in netid:
            netid[name] = len(netid)
        return netid[name]

    fets, pullups, sites = [], set(), []
    for c in d["components"]:
        if c["type"] == "fet":
            idx = len(fets)
            fets.append((nid(c["pins"]["1"]), nid(c["pins"]["3"]), nid(c["pins"]["2"])))
            if c.get("role") == "vcc_side":
                # The channel net is whichever of pins 2/3 is not a rail: the two
                # roles use opposite conventions, so asking "which pin is the
                # rail" is the only safe way to read it.
                a, b = c["pins"]["2"], c["pins"]["3"]
                net = b if a in ("vss", "vcc") else a
                sites.append({"ref": c["ref"], "net": net, "gate": c["pins"]["1"],
                              "fet": idx})
        elif c["type"] == "resistor" and c["role"] in ("pullup", "vcc_series"):
            pullups.add(nid(c["pins"]["2"]))

    names = {name: nid(name) for name in d["nets"]}
    sim = switchsim.Sim(fets, pullups, names)

    # Only nets with a pull-down can contend at all; the other 22 cannot be hot.
    pulldn = defaultdict(int)
    for c in d["components"]:
        if c.get("role") == "pulldown":
            a, b = c["pins"]["2"], c["pins"]["3"]
            pulldn[b if a in ("vss", "vcc") else a] += 1
    for s in sites:
        s["pulldowns"] = pulldn[s["net"]]
    # Do NOT filter on pulldowns. A net with no FET sitting directly between it
    # and vss can still be pulled low THROUGH A PASS-GATE CHAIN -- adl4..adl7 are
    # exactly that, and they measured ~80 C on board #1 while an earlier version
    # of this script had excluded them as unable to contend. The detector below
    # follows conduction groups, so it handles those paths correctly; it was only
    # this filter that was wrong. (The FETs that filter *did* find on adl4..adl7
    # are gated BY those nets, i.e. loads they drive -- the same "gated by X, not
    # on X" error recorded against cclk on 2026-08-01.)
    return sim, sites, names


def measure(halves, workload):
    sim, sites, names = build_indexed()
    mem = switchsim.make_mem() if workload == "real" else [0xEA] * 65536
    sim.init()
    vss = sim.vss
    for s in sites:
        s["hits"] = 0
        s["nid"] = names[s["net"]]
    n = 0
    for _ in range(halves):
        sim.cycle(mem)
        n += 1
        for s in sites:
            # Contended: the VCC-side device is conducting, and this net's
            # conduction group reaches vss at the same time.
            if sim.on[s["fet"]] and vss in sim._group(s["nid"]):
                s["hits"] += 1
    for s in sites:
        s["duty"] = s["hits"] / n
    return sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--halves", type=int, default=400)
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    runs = {}
    for wl in ("real", "nop"):
        print("simulating %-4s (%d half-cycles) ..." % (wl, args.halves), flush=True)
        runs[wl] = {s["ref"]: s for s in measure(args.halves, wl)}

    real, nop = runs["real"], runs["nop"]
    rows = sorted(real.values(), key=lambda s: -s["duty"])

    print("\n%-7s %-9s %-9s %8s %8s   %s" %
          ("ref", "net", "gate", "real", "nop", "verdict"))
    print("-" * 66)
    for s in rows[:args.top]:
        r, nd = s["duty"], nop[s["ref"]]["duty"]
        if r > 0.2 and nd < 0.05:
            v = "quiet at THIS address -- see the caveat, not 'never contends'"
        elif r > 0.2 and nd > 0.2:
            v = "always contended"
        elif r < 0.05 and nd < 0.05:
            v = "quiet"
        else:
            v = ""
        print("%-7s %-9s %-9s %7.1f%% %7.1f%%   %s" % (s["ref"], s["net"], s["gate"],
                                                       100 * r, 100 * nd, v))

    def summarise(label, pred):
        sel = [s for s in real.values() if pred(s)]
        if not sel:
            return
        mr = sum(s["duty"] for s in sel) / len(sel)
        mn = sum(nop[s["ref"]]["duty"] for s in sel) / len(sel)
        print("  %-28s n=%-4d real %5.1f%%   nop %5.1f%%" %
              (label, len(sel), 100 * mr, 100 * mn))

    print("\nby group (mean duty):")
    summarise("adh* (address high)", lambda s: s["net"].startswith("adh"))
    summarise("adl* (address low)", lambda s: s["net"].startswith("adl"))
    summarise("ab* (address bus out)", lambda s: s["net"].startswith("ab"))
    summarise("the 8 reworked dor nets",
              lambda s: s["net"] in ("n1325", "n798", "n520", "n42",
                                     "n1076", "n373", "n7", "n298"))
    summarise("everything that can contend", lambda s: True)

    tot_r = sum(s["duty"] for s in real.values())
    tot_n = sum(nop[s["ref"]]["duty"] for s in real.values())
    print("\nmean number of nets contended at once:  real %.1f   nop %.1f" % (tot_r, tot_n))
    print("at 262 mA per contended net that is:    real %.2f A  nop %.2f A"
          % (tot_r * 0.262, tot_n * 0.262))


if __name__ == "__main__":
    main()
