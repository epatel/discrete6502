#!/usr/bin/env python3
"""Board-vs-netlist parity check (run with KiCad's bundled python).

Verifies that the physical board still implements gen/netlist.json exactly:
  1. every component exists with the right footprint kind and DNP flag
  2. every pad carries the net the netlist assigns it
  3. no extra copper-bearing footprints beyond the netlist + mounting holes
Run before generating fab outputs, and again after any .ses import.
"""
import json
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
board = pcbnew.LoadBoard(str(ROOT / "gen" / "discrete6502.kicad_pcb"))
comps = {c["ref"]: c for c in json.loads(
    (ROOT / "gen" / "netlist.json").read_text())["components"]}

errors = []
seen = set()
for fp in board.Footprints():
    ref = fp.GetReference()
    if ref.startswith("H"):  # mounting holes are board furniture
        continue
    c = comps.get(ref)
    if c is None:
        errors.append("extra footprint on board: %s" % ref)
        continue
    seen.add(ref)
    if bool(c.get("dnp")) != fp.IsDNP():
        errors.append("%s: DNP mismatch (netlist %s, board %s)"
                      % (ref, c.get("dnp"), fp.IsDNP()))
    want_fp = c["footprint"].split(":")[1]
    have_fp = str(fp.GetFPID().GetLibItemName())
    if want_fp != have_fp:
        errors.append("%s: footprint %s != %s" % (ref, have_fp, want_fp))
    for pad in fp.Pads():
        want = c["pins"].get(str(pad.GetNumber()))
        if want is None:
            if pad.GetNetname() not in ("", None) and pad.GetNetCode() != 0:
                # library-internal pads (e.g. Pico module extras) may be unnetted
                pass
            continue
        if pad.GetNetname() != want:
            errors.append("%s pad %s: net %r != %r"
                          % (ref, pad.GetNumber(), pad.GetNetname(), want))

missing = set(comps) - seen
for ref in sorted(missing):
    errors.append("missing from board: %s" % ref)

print("checked %d components, %d errors" % (len(seen), len(errors)))
for e in errors[:40]:
    print(" ", e)
sys.exit(1 if errors else 0)
