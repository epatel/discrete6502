#!/usr/bin/env python3
"""Switch-level equivalence check: original visual6502 netlist vs. the
transformed discrete netlist in gen/netlist.json.

Both are simulated with the visual6502/perfect6502 algorithm (conduction-group
BFS, value resolution vss > vcc > pullup > pulldown > charge majority) and run
the same 6502 test program behind the same memory harness. Traces of the bus,
control signals, and registers are compared every half clock cycle.

Exit 0 = equivalent + program executed correctly on both.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "visual6502"

INPUT_HI = {"rdy", "irq", "nmi", "so"}  # held high; so held low is also fine but visual6502 uses hi


class Sim:
    def __init__(self, fets, pullup_nets, names):
        """fets: list of (gate, a, b) net ids. pullup_nets: set of net ids.
        names: name -> net id (must include vss, vcc)."""
        self.names = names
        self.vss, self.vcc = names["vss"], names["vcc"]
        self.fets = fets
        self.gate_of = defaultdict(list)     # gate net -> fet indexes
        self.channel_of = defaultdict(list)  # net -> fet indexes touching it
        for i, (g, a, b) in enumerate(fets):
            self.gate_of[g].append(i)
            self.channel_of[a].append(i)
            self.channel_of[b].append(i)
        nets = set(names.values()) | pullup_nets
        for g, a, b in fets:
            nets |= {g, a, b}
        self.nets = nets
        self.state = {n: False for n in nets}
        self.pullup = {n: (n in pullup_nets) for n in nets}
        self.pulldown = {n: False for n in nets}
        self.on = [False] * len(fets)
        self.state[self.vcc] = True

    def _group(self, seed):
        group, todo = set(), [seed]
        while todo:
            n = todo.pop()
            if n in group:
                continue
            group.add(n)
            if n in (self.vss, self.vcc):
                continue
            for i in self.channel_of[n]:
                if self.on[i]:
                    _, a, b = self.fets[i]
                    todo.append(b if a == n else a)
        return group

    def _value(self, group):
        if self.vss in group:
            return False
        if self.vcc in group:
            return True
        hi = lo = 0
        saw_pullup = saw_pulldown = False
        for n in group:
            saw_pullup |= self.pullup[n]
            saw_pulldown |= self.pulldown[n]
            if self.state[n]:
                hi += 1
            else:
                lo += 1
        if saw_pulldown:
            return False
        if saw_pullup:
            return True
        # floating group: charged high if any member held charge (perfect6502)
        return hi > 0

    def recalc(self, seeds):
        seeds = [n for n in seeds if n not in (self.vss, self.vcc)]
        for _ in range(200):
            if not seeds:
                return
            nxt = set()
            for seed in set(seeds):
                group = self._group(seed)
                val = self._value(group)
                for n in group:
                    if n in (self.vss, self.vcc) or self.state[n] == val:
                        continue
                    self.state[n] = val
                    for i in self.gate_of[n]:
                        if self.on[i] != val:
                            self.on[i] = val
                            _, a, b = self.fets[i]
                            nxt.add(a)
                            nxt.add(b)
            seeds = nxt
        raise RuntimeError("recalc did not settle")

    # --- external pin helpers ---
    def set_pin(self, name, hi):
        n = self.names[name]
        self.pullup[n], self.pulldown[n] = hi, not hi
        self.recalc([n])

    def float_pins(self, pinnames):
        seeds = []
        for name in pinnames:
            n = self.names[name]
            self.pullup[n] = self.pulldown[n] = False
            seeds.append(n)
        self.recalc(seeds)

    def read(self, name):
        return self.state[self.names[name]]

    def read_bits(self, prefix, count):
        v = 0
        for i in range(count):
            if self.read("%s%d" % (prefix, i)):
                v |= 1 << i
        return v

    def init(self):
        for name in INPUT_HI:
            n = self.names[name]
            self.pullup[n], self.pulldown[n] = True, False
        self.set_pin("res", False)
        self.set_pin("clk0", True)
        self.recalc(list(self.nets))
        for _ in range(16):  # clock through reset
            self.half_step()
        self.set_pin("res", True)

    def half_step(self):
        clk = self.read("clk0")
        self.set_pin("clk0", not clk)

    def cycle(self, mem):
        """One half step + memory handling (visual6502 harness order):
        after driving clk low, service reads; after driving clk high,
        capture writes. Returns trace tuple."""
        if self.read("clk0"):
            self.set_pin("clk0", False)
            if self.read("rw"):
                data = mem[self.read_bits("ab", 16)]
                for i in range(8):
                    self.set_pin("db%d" % i, bool(data & (1 << i)))
        else:
            self.set_pin("clk0", True)
            if not self.read("rw"):
                self.float_pins(["db%d" % i for i in range(8)])
                mem[self.read_bits("ab", 16)] = self.read_bits("db", 8)
        return (self.read("clk0"), self.read("rw"), self.read_bits("ab", 16),
                self.read_bits("db", 8),
                self.read("sync"), self.read_bits("a", 8),
                self.read_bits("x", 8), self.read_bits("pcl", 8),
                self.read_bits("pch", 8))


def load_original():
    txt = (DATA / "transdefs.js").read_text()
    fets = []
    seen = set()
    for m in re.findall(r"\[\s*'(t\d+)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", txt):
        g, a, b = int(m[1]), int(m[2]), int(m[3])
        if a == b:
            continue
        key = (g, frozenset((a, b)))
        if key in seen:
            continue
        seen.add(key)
        fets.append((g, a, b))
    seg = (DATA / "segdefs.js").read_text()
    pullups = {int(m[1]) for m in re.finditer(r"\[\s*(\d+)\s*,\s*'\+'", seg)}
    names = {k: int(v) for k, v in
             re.findall(r"([A-Za-z0-9_]+)\s*:\s*(\d+),", (DATA / "nodenames.js").read_text())}
    return Sim(fets, pullups, names)


def load_transformed():
    d = json.loads((ROOT / "gen" / "netlist.json").read_text())
    netid = {}

    def nid(name):
        if name not in netid:
            netid[name] = len(netid)
        return netid[name]

    fets, pullups = [], set()
    for c in d["components"]:
        if c["type"] == "fet":
            fets.append((nid(c["pins"]["1"]), nid(c["pins"]["3"]), nid(c["pins"]["2"])))
        elif c["type"] == "resistor" and c["role"] == "pullup":
            pullups.add(nid(c["pins"]["2"]))
    names = {}
    for name in list(d["nets"]):
        names[name] = nid(name)
    return Sim(fets, pullups, names)


def load_extracted():
    """The netlist read back out of the copper by tools/extract_netlist.py.

    Node ids here are conductor ids from the geometric union-find, not net
    names -- nothing in this path came from KiCad's net bookkeeping except the
    ~80 anchored pin names the harness has to drive and read.
    """
    d = json.loads((ROOT / "gen" / "extracted_netlist.json").read_text())
    return Sim([tuple(f) for f in d["fets"]], set(d["pullups"]), d["names"])


TEST_PROGRAM = {
    0x0000: [0xA2, 0xFF,        # LDX #$FF
             0x9A,              # TXS
             0xA9, 0x0F,        # LDA #$0F
             0x38,              # SEC
             0x69, 0x10,        # ADC #$10  -> A=$20
             0x20, 0x20, 0x00,  # JSR $0020
             0x8D, 0x01, 0x02,  # STA $0201
             0x8E, 0x02, 0x02,  # STX $0202
             0x4C, 0x11, 0x00], # JMP $0011 (spin)
    0x0020: [0xA2, 0x03,        # LDX #$03
             0xCA,              # DEX
             0xD0, 0xFD,        # BNE $0022
             0x48,              # PHA
             0xA9, 0x77,        # LDA #$77
             0x68,              # PLA       -> A=$20 again
             0x60],             # RTS
    0xFFFC: [0x00, 0x00],       # reset vector -> $0000
}


def make_mem():
    mem = [0xEA] * 65536
    for base, bytes_ in TEST_PROGRAM.items():
        for i, v in enumerate(bytes_):
            mem[base + i] = v
    return mem


def run(sim, halves):
    mem = make_mem()
    sim.init()
    trace = [sim.cycle(mem) for _ in range(halves)]
    return trace, mem


def compare(label, orig, cand, halves):
    """Traces must agree once reset has flushed the arbitrary initial charge."""
    mismatches = [i for i, (a, b) in enumerate(zip(orig, cand)) if a != b]
    settle = 0
    if mismatches:
        settle = mismatches[-1] + 1
        print("%s: post-init disagreement in half-cycles %d..%d (%d of them)"
              % (label, mismatches[0], mismatches[-1], len(mismatches)))
    if settle > 40:
        i = mismatches[-1]
        print("%s: MISMATCH persists past settling window (last at %d):" % (label, i))
        print("  orig: %s\n  %s: %s" % (orig[i], label, cand[i]))
        return False
    print("%s: traces identical for half-cycles %d..%d" % (label, settle, halves - 1))
    return True


def program_ok(label, mem, tr):
    clk, rw, ab, db, sync, a, x, pcl, pch = tr[-1]
    print("%s: A=%02x X=%02x PC=%02x%02x mem[0201]=%02x mem[0202]=%02x"
          % (label, a, x, pch, pcl, mem[0x0201], mem[0x0202]))
    return (a == 0x20 and x == 0x00 and mem[0x0201] == 0x20
            and mem[0x0202] == 0x00 and pch == 0x00 and pcl in (0x11, 0x12, 0x13))


def main():
    halves = 220
    print("simulating original netlist ...")
    orig, mem_o = run(load_original(), halves)
    print("simulating transformed netlist ...")
    xform, mem_x = run(load_transformed(), halves)

    runs = [("original", orig, mem_o), ("transformed", xform, mem_x)]
    ok = compare("transformed", orig, xform, halves)

    # The reverse gate: the netlist read back out of the copper. Optional, so a
    # plain equivalence run still works without having done an extraction.
    if (ROOT / "gen" / "extracted_netlist.json").exists():
        print("simulating netlist EXTRACTED FROM COPPER ...")
        extr, mem_e = run(load_extracted(), halves)
        runs.append(("extracted", extr, mem_e))
        ok = compare("extracted", orig, extr, halves) and ok
    else:
        print("(no gen/extracted_netlist.json - run tools/extract_netlist.py"
              " for the copper-level gate)")

    if not ok:
        return 1
    for label, tr, mem in runs:
        if not program_ok(label, mem, tr):
            ok = False
    print("PROGRAM CHECK:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
