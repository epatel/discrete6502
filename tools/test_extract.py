#!/usr/bin/env python3
"""Does the reverse gate actually have teeth?

`tools/extract_netlist.py` rebuilds the netlist from copper and reports 0 opens
and 0 shorts on the golden board. On its own that proves nothing: a checker
that always says CLEAN would print exactly the same thing. This deliberately
damages copies of the board and requires the checker to notice.

Three cases:
  clean   an untouched copy            -> must report 0 opens, 0 shorts
  cut     one track segment removed    -> must report an OPEN
  bridge  two nets joined by a track   -> must report a SHORT

Damaged boards are built in a temp directory and the extractor's per-board
artifacts are cleaned up afterwards, so nothing here touches the golden board
or the canonical gen/extracted_netlist.json.

Takes a few minutes -- three full extractions. Run with KiCad's bundled python:
  <kicad-python> tools/test_extract.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "gen" / "board_routed_golden.kicad_pcb"
EXTRACT = ROOT / "tools" / "extract_netlist.py"


def make_cut(src, dst):
    """Remove one track segment from a signal net.

    The victim must be a LONG segment. Deleting a short one often changes
    nothing: the router emits chains of short collinear segments, and once the
    middle one is gone its neighbours can still overlap across the gap, leaving
    the net connected. Picking the longest track guarantees a gap wider than
    any track can bridge -- and keeps the test deterministic.
    """
    b = pcbnew.LoadBoard(str(src))
    cands = [t for t in b.Tracks()
             if t.GetClass() == "PCB_TRACK" and t.GetNetname() not in ("vss", "vcc", "")]
    victim = max(cands, key=lambda t: ((t.GetStart() - t.GetEnd()).EuclideanNorm(),
                                       t.GetNetname()))
    net = victim.GetNetname()
    length = (victim.GetStart() - victim.GetEnd()).EuclideanNorm() / 1e6
    b.Remove(victim)
    b.Save(str(dst))
    return "%s (%.2f mm)" % (net, length)


def make_bridge(src, dst):
    """Join two different nets with a track that should not exist."""
    b = pcbnew.LoadBoard(str(src))
    F = pcbnew.F_Cu
    pads = sorted((p for f in b.Footprints() for p in f.Pads()
                   if p.IsOnLayer(F) and p.GetNetname() not in ("vss", "vcc", "")),
                  key=lambda p: (p.GetPosition().x, p.GetPosition().y))
    for a, c in zip(pads, pads[1:]):
        if (a.GetNetCode() != c.GetNetCode()
                and (a.GetPosition() - c.GetPosition()).EuclideanNorm() < 3e6):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(a.GetPosition())
            t.SetEnd(c.GetPosition())
            t.SetWidth(127000)
            t.SetLayer(F)
            t.SetNetCode(a.GetNetCode())
            b.Add(t)
            b.Save(str(dst))
            return "%s + %s" % (a.GetNetname(), c.GetNetname())
    raise RuntimeError("no adjacent different-net pad pair found to bridge")


def extract(board):
    """Run the real extractor and return its LVS verdict."""
    r = subprocess.run([sys.executable, str(EXTRACT), str(board)],
                       capture_output=True, text=True)
    out = ROOT / "gen" / ("extracted_%s.json" % Path(board).stem)
    if not out.exists():
        print(r.stdout[-2000:])
        raise RuntimeError("extractor produced no artifact for %s" % board)
    lvs = json.loads(out.read_text())["lvs"]
    out.unlink()
    return lvs


def surgery_subprocess(kind, src, dst):
    """Each board edit runs in a FRESH process.

    Loading a second board into a process that has already loaded and saved one
    hands back a bare SwigPyObject instead of a BOARD -- the same KiCad SWIG
    fragility that forces add_silk.py to split its destructive pass out. Do not
    'simplify' this back into one process.
    """
    r = subprocess.run([sys.executable, __file__, "--surgery", kind, str(src), str(dst)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("surgery %s failed:\n%s" % (kind, r.stdout + r.stderr))
    return r.stdout.strip().splitlines()[-1]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--surgery":
        kind, src, dst = sys.argv[2], sys.argv[3], sys.argv[4]
        print(make_cut(src, dst) if kind == "cut" else make_bridge(src, dst))
        return 0

    if not GOLDEN.exists():
        print("golden board missing: %s" % GOLDEN)
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="extract_test_"))
    failures = []
    try:
        clean = tmp / "board_clean.kicad_pcb"
        shutil.copy(GOLDEN, clean)
        cut = tmp / "board_cut.kicad_pcb"
        cut_net = surgery_subprocess("cut", GOLDEN, cut)
        bridge = tmp / "board_bridge.kicad_pcb"
        bridged = surgery_subprocess("bridge", GOLDEN, bridge)
        print("damaged copies built: cut %s, bridge %s\n" % (cut_net, bridged))

        cases = [
            ("clean", clean, lambda l: l["opens"] == 0 and l["shorts"] == 0,
             "0 opens and 0 shorts"),
            ("cut", cut, lambda l: l["opens"] >= 1, "at least one OPEN"),
            ("bridge", bridge, lambda l: l["shorts"] >= 1, "at least one SHORT"),
        ]
        for name, board, ok, want in cases:
            print("--- %s: extracting ..." % name)
            lvs = extract(board)
            good = ok(lvs)
            print("    %s -> opens=%d shorts=%d missing=%d  (want %s)  %s"
                  % (name, lvs["opens"], lvs["shorts"], lvs["missing_pads"],
                     want, "PASS" if good else "FAIL"))
            if not good:
                failures.append(name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nGATE-HAS-TEETH: %s"
          % ("PASS" if not failures else "FAIL (%s)" % ", ".join(failures)))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
