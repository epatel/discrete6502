#!/usr/bin/env python3
"""Run tiny diagnostic programs on the discrete6502 over the wifi panel's HTTP API.

Why this exists: the wifi firmware exposes the whole bring-up loop over HTTP
(POST /load takes Intel hex, /cmd drives the CPU, /trace returns the last 32 bus
cycles), so a defect can be isolated with no USB terminal and no soldering. The
32-cycle mirror is far too short to catch a failure inside real code, so each
test here is a purpose-built program short enough that the whole run fits.

Found with it on 2026-08-26: board #1's stack pointer decrements by 2 instead of
1 while pulls increment correctly -- see docs/stack-decrement-defect.md.

Usage:
    python3 tools/board_probe.py --host 192.168.68.65 push
    python3 tools/board_probe.py dex
    python3 tools/board_probe.py all --sweep

Two rules this encodes so they cannot be got wrong by hand:
  * /load is refused with 409 unless the CPU is stopped first.
  * reset and run must be ONE operation (CMD_RESETRUN). Resetting and then
    starting a run as a second request begins from decayed state: the clock
    parks between requests and the worst dynamic node holds charge ~1.1 ms.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_HOST = "192.168.68.65"

# ---------------------------------------------------------------- Intel hex


def ihex_record(addr, data, rtype=0):
    b = bytes([len(data), addr >> 8, addr & 0xFF, rtype]) + bytes(data)
    return ":" + b.hex().upper() + "%02X" % ((-sum(b)) & 0xFF)


def build_hex(blocks, nmi, res, irq):
    """blocks: {addr: bytes}. Vectors mirror to $3FFA..$3FFF in the 16 KB window."""
    lines = [ihex_record(a, d) for a, d in sorted(blocks.items())]
    vec = bytes([nmi & 0xFF, nmi >> 8, res & 0xFF, res >> 8, irq & 0xFF, irq >> 8])
    lines.append(ihex_record(0x3FFA, vec))
    lines.append(":00000001FF")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- transport


class Board:
    def __init__(self, host, timeout=8.0, verbose=False):
        self.base = host if host.startswith("http") else "http://" + host
        self.timeout = timeout
        self.verbose = verbose

    def _get(self, path):
        url = self.base + path
        if self.verbose:
            print("  GET", url, file=sys.stderr)
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def cmd(self, op, v=None):
        q = {"op": op}
        if v is not None:
            q["v"] = str(v)
        return self._get("/cmd?" + urllib.parse.urlencode(q))

    def status(self):
        return self._get("/status")

    def trace(self, n=32):
        return self._get("/trace?n=%d" % n)["t"]

    def load(self, hex_text):
        url = self.base + "/load"
        if self.verbose:
            print("  POST", url, file=sys.stderr)
        req = urllib.request.Request(url, data=hex_text.encode(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    # ---- composite operations

    def load_program(self, blocks, nmi, res, irq):
        self.cmd("stop")
        self.cmd("ft", 0)  # watcher off: the cycle budget stays deterministic
        rep = self.load(build_hex(blocks, nmi, res, irq))
        if not rep.get("ok") or rep.get("bad"):
            raise RuntimeError("load failed: %r" % rep)
        if rep.get("vec") != res:
            raise RuntimeError(
                "reset vector is $%04X, expected $%04X" % (rep.get("vec", 0), res))
        return rep

    def reset_run(self, cycles, half_us):
        self.cmd("clock", half_us)
        self.cmd("resetrun", cycles)
        # A run of N cycles takes N * 2 * half_us; poll rather than guess.
        budget = cycles * 2 * half_us / 1e6 + 1.0
        deadline = time.time() + budget
        while time.time() < deadline:
            if not self.status().get("run"):
                return
            time.sleep(0.05)
        raise RuntimeError("CPU still running after %.1fs" % budget)


# ---------------------------------------------------------------- decoding

def decode(entries):
    """[cycle, addr, data, flags] -> dicts. flags bit0 = read, bit1 = sync."""
    return [{"cycle": c, "addr": a, "data": d,
             "read": bool(f & 1), "sync": bool(f & 2)} for c, a, d, f in entries]


def show(rows, note=None):
    print("  cycle   addr   data  r/w   sync")
    for r in rows:
        print("  %6d  $%04X   %02X   %-5s %s"
              % (r["cycle"], r["addr"], r["data"],
                 "read" if r["read"] else "WRITE", "SYNC" if r["sync"] else ""))
    if note:
        print("  " + note)


def writes_to(rows, lo, hi):
    return [r for r in rows if not r["read"] and lo <= r["addr"] <= hi]


# ---------------------------------------------------------------- the tests
#
# Every image traps interrupts at $0210 (a self-loop clear of the code), so a
# stray NMI/IRQ is visible as a distinct address rather than silently absorbed.

TRAP = 0x0210
TRAP_BLOCK = {TRAP: bytes([0x4C, TRAP & 0xFF, TRAP >> 8])}


def _prog(code, org=0x0200):
    b = dict(TRAP_BLOCK)
    b[org] = bytes(code)
    return b


def test_push(board, args, s_init=0xFF):
    """PHA x3 from a known S. Does each push decrement S by 1?"""
    code = [0xA2, s_init, 0x9A,           # LDX #s_init ; TXS
            0xA9, 0xAA,                   # LDA #$AA
            0x48, 0x48, 0x48,             # PHA PHA PHA
            0x4C, 0x08, 0x02]             # JMP $0208
    board.load_program(_prog(code), TRAP, 0x0200, TRAP)
    board.reset_run(args.cycles, args.clock)
    rows = decode(board.trace())
    if args.show:
        show(rows)
    w = writes_to(rows, 0x0100, 0x01FF)
    got = [r["addr"] for r in w]
    exp = [0x0100 | ((s_init - i) & 0xFF) for i in range(3)]
    print("    pushes at  " + " ".join("$%04X" % a for a in got))
    print("    expected   " + " ".join("$%04X" % a for a in exp))
    if len(got) < 3:
        return None, "only %d stack writes seen -- widen --cycles" % len(got)
    deltas = [got[i] - got[i + 1] for i in range(len(got) - 1)]
    if got[:3] == exp:
        return True, "S decrements by 1 per push -- healthy"
    return False, "S deltas %s (want [1, 1]) -- stack pointer decrements by %s" % (
        deltas, deltas[0])


def test_push_even(board, args):
    """Same, from an even S. Separates 'always -2' from 'S bit 0 stuck'."""
    return test_push(board, args, s_init=0xFE)


def test_dex(board, args):
    """DEX then INX, results stored where the bus can see them.

    DEX uses the same ALU decrement path as a push (X -> SB -> alua, B = $FF via
    nDB/ADD). If alub0 cannot go high, DEX must also step by 2 while INX stays
    correct -- which separates a shared ALU-operand fault from a stack-specific
    one. See docs/stack-decrement-defect.md.
    """
    code = [0xA2, 0xFF,                   # LDX #$FF
            0xCA,                         # DEX
            0x8E, 0x00, 0x03,             # STX $0300
            0xE8,                         # INX
            0x8E, 0x01, 0x03,             # STX $0301
            0x4C, 0x0A, 0x02]             # JMP $020A
    board.load_program(_prog(code), TRAP, 0x0200, TRAP)
    board.reset_run(args.cycles, args.clock)
    rows = decode(board.trace())
    if args.show:
        show(rows)
    w = {r["addr"]: r["data"] for r in writes_to(rows, 0x0300, 0x0301)}
    dex, inx = w.get(0x0300), w.get(0x0301)
    print("    after DEX  X = %s (healthy $FE)" % ("$%02X" % dex if dex is not None else "?"))
    print("    after INX  X = %s (healthy $FF)" % ("$%02X" % inx if inx is not None else "?"))
    if dex is None or inx is None:
        return None, "did not see both stores -- widen --cycles"
    if (dex, inx) == (0xFE, 0xFF):
        return True, "DEX/INX correct -- the decrement fault is stack-specific, not the ALU operand"
    if (dex, inx) == (0xFD, 0xFE):
        return False, "DEX also steps by 2 while INX is correct -- alub0 confirmed (Q1313/Q1314)"
    return False, "unexpected pair ($%02X, $%02X)" % (dex, inx)


def test_sxfer(board, args):
    """TXS then TSX with no push at all. Is the S <-> SB path clean by itself?"""
    code = [0xA2, 0xFF,                   # LDX #$FF
            0x9A,                         # TXS
            0xBA,                         # TSX
            0x8E, 0x00, 0x03,             # STX $0300
            0x4C, 0x07, 0x02]             # JMP $0207
    board.load_program(_prog(code), TRAP, 0x0200, TRAP)
    board.reset_run(args.cycles, args.clock)
    rows = decode(board.trace())
    if args.show:
        show(rows)
    w = {r["addr"]: r["data"] for r in writes_to(rows, 0x0300, 0x0300)}
    v = w.get(0x0300)
    print("    S round-tripped as %s (healthy $FF)"
          % ("$%02X" % v if v is not None else "?"))
    if v is None:
        return None, "did not see the store -- widen --cycles"
    if v == 0xFF:
        return True, "S <-> SB transfer is clean with no decrement involved"
    return False, "S corrupted by a bare transfer -- the fault is in S <-> SB, not the decrement"


def test_push1(board, args):
    """Exactly ONE push, then read S back. Does a single push step by 1 or 2?"""
    code = [0xA9, 0xAA,                   # LDA #$AA
            0xA2, 0xFF, 0x9A,             # LDX #$FF ; TXS
            0x48,                         # PHA
            0xBA,                         # TSX
            0x8E, 0x00, 0x03,             # STX $0300
            0x4C, 0x0A, 0x02]             # JMP $020A
    board.load_program(_prog(code), TRAP, 0x0200, TRAP)
    board.reset_run(args.cycles, args.clock)
    rows = decode(board.trace())
    if args.show:
        show(rows)
    w = {r["addr"]: r["data"] for r in writes_to(rows, 0x0300, 0x0300)}
    v = w.get(0x0300)
    print("    S after one PHA = %s (healthy $FE)"
          % ("$%02X" % v if v is not None else "?"))
    if v is None:
        return None, "did not see the store -- widen --cycles"
    if v == 0xFE:
        return True, "a single push decrements by 1 -- the doubling needs consecutive pushes"
    if v == 0xFD:
        return False, "a single push decrements by 2 -- every push doubles"
    return False, "unexpected S = $%02X" % v


TESTS = {
    "push": ("stack pointer: PHA x3 from S=$FF", test_push),
    "push-even": ("stack pointer: PHA x3 from S=$FE", test_push_even),
    "dex": ("ALU decrement operand: DEX / INX", test_dex),
    "sxfer": ("S <-> SB path: TXS / TSX round trip", test_sxfer),
    "push1": ("stack pointer: exactly one PHA", test_push1),
}


# ---- hold programs: tight loops for thermal / scope work, no verdict ----
#
# These free-run forever so an instrument has something repetitive to look at.
# `push` hammers the stack-decrement control lines (dpc4_SSB / dpc6_SBS);
# `dex` hammers the matching pair that DEX uses (dpc2_XSB / dpc3_SBX) and is
# the control, because DEX is known good on this board. Same clock, similar
# loop length -- 6 cycles vs 5 -- so a thermal difference between the two is
# about which lines are being exercised, not about how hard the CPU is working.

HOLDS = {
    "push": ("PHA in a tight loop -- exercises the S decrement",
             [0xA9, 0xAA,               # LDA #$AA
              0xA2, 0xFF, 0x9A,         # LDX #$FF ; TXS
              0x48,                     # PHA          <- loop
              0x4C, 0x05, 0x02]),       # JMP $0205
    "dex":  ("DEX in a tight loop -- the known-good control pair",
             [0xA2, 0xFF,               # LDX #$FF
              0xCA,                     # DEX          <- loop
              0x4C, 0x02, 0x02]),       # JMP $0202
    "idle": ("NOP-equivalent spin -- neither pair exercised",
             [0x4C, 0x00, 0x02]),       # JMP $0200
}


def do_hold(board, which, args):
    label, code = HOLDS[which]
    print("loading hold program '%s': %s" % (which, label))
    board.load_program(_prog(code), TRAP, 0x0200, TRAP)
    board.cmd("clock", args.clock)
    board.cmd("resetrun", 0)          # budget 0 = free-run until stopped
    time.sleep(1.0)
    st = board.status()
    print("  running=%s  cyc=%s  %.1f kHz" % (st["run"], st["cyc"], 1e3 / (2 * args.clock)))
    if not st["run"]:
        print("  WARNING: not running")
        return 1
    print("  free-running. stop with:  python3 tools/board_probe.py --host %s stop"
          % args.host)
    return 0


# ---------------------------------------------------------------- driver

def run_one(board, name, args):
    label, fn = TESTS[name]
    print("\n== %s (%s) ==" % (name, label))
    print("   clock %d us half-period (%.1f kHz), %d cycles"
          % (args.clock, 1e3 / (2 * args.clock), args.cycles))
    try:
        ok, note = fn(board, args)
    except (urllib.error.URLError, OSError) as e:
        print("    UNREACHABLE: %s" % e)
        return None
    except RuntimeError as e:
        print("    ERROR: %s" % e)
        return None
    verdict = {True: "PASS", False: "FAIL", None: "INCONCLUSIVE"}[ok]
    print("    -> %s: %s" % (verdict, note))
    return ok


def main():
    ap = argparse.ArgumentParser(
        description="Run diagnostic programs on the discrete6502 over its wifi panel.")
    ap.add_argument("test", nargs="?", default="all",
                    choices=sorted(TESTS) + ["all", "status", "restore", "stop",
                                             "hold-push", "hold-dex", "hold-idle"])
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--clock", type=int, default=100,
                    help="clock half-period in us (100 = 5 kHz, the recommended point)")
    ap.add_argument("--cycles", type=int, default=40)
    ap.add_argument("--sweep", action="store_true",
                    help="repeat each test at 250/100/50/30 us to test frequency dependence")
    ap.add_argument("--show", action="store_true", help="print the decoded trace")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    board = Board(args.host, verbose=args.verbose)

    try:
        st = board.status()
    except (urllib.error.URLError, OSError) as e:
        print("cannot reach the board at %s: %s" % (args.host, e))
        print("check the panel is up and the IP is right (it is shown on the panel).")
        return 2

    print("board %s  ip=%s  clock=%s us  running=%s  autorun=%s"
          % (args.host, st.get("ip"), st.get("half"), st.get("run"), st.get("ar")))

    if args.test == "status":
        print(json.dumps(st, indent=2))
        return 0

    if args.test == "stop":
        board.cmd("stop")
        print("stopped.")
        return 0

    if args.test.startswith("hold-"):
        return do_hold(board, args.test[5:], args)

    if args.test == "restore":
        board.cmd("stop")
        # /cmd?op=img needs a k= parameter, so bypass cmd()'s single-value form.
        r = board._get("/cmd?op=img&k=d")
        print("reloaded the decimal test image:", r)
        return 0

    names = sorted(TESTS) if args.test == "all" else [args.test]
    clocks = [250, 100, 50, 30] if args.sweep else [args.clock]

    results = {}
    for half in clocks:
        args.clock = half
        for n in names:
            results[(n, half)] = run_one(board, n, args)

    print("\n== summary ==")
    for (n, half), ok in results.items():
        print("  %-10s %3d us (%5.1f kHz)  %s"
              % (n, half, 1e3 / (2 * half),
                 {True: "PASS", False: "FAIL", None: "INCONCLUSIVE"}[ok]))
    if args.sweep:
        per = {}
        for (n, _), ok in results.items():
            per.setdefault(n, set()).add(ok)
        for n, s in per.items():
            if s == {False}:
                print("  %s: identical failure at every clock -- deterministic logic "
                      "fault, not retention or settling" % n)

    print("\nthe board now holds a probe image, not the acceptance test.")
    print("restore it with:  python3 tools/board_probe.py --host %s restore" % args.host)
    return 0 if all(v is True for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
