# discrete6502 — fabrication release **rev A**, 2026-07-26

The design is complete, verified and ready to order. This file pins down exactly
what "rev A" is, so a later package can be told apart from this one.

## Fingerprints (sha256, first 16 hex)

| File | Digest |
|---|---|
| `discrete6502_gerbers.zip` | `cceb7f6769b4cb0e` |
| `discrete6502_bom.csv` | `ae47ae31798d16af` |
| `discrete6502_cpl.csv` | `b8b959193a7322b4` |

Source board: `gen/discrete6502.kicad_pcb` (golden copy `gen/board_routed_golden.kicad_pcb`),
git `c5c06f0`. The zip has been byte-compared against a fresh plot of that board —
15 of 15 files identical apart from creation timestamps.

## Board

| | |
|---|---|
| Outline | 290.7 × 322.0 mm (≈ 9.4 dm²) — the quote shows 300.7 mm because JLC adds two 5 mm assembly rails |
| Stack | 6 layers, 1.6 mm FR-4 TG135. F.Cu / In1=GND / In2 / In3 / In4=VCC / B.Cu |
| Routing | F, In2, In3, B alternating H/V/H/V; 0.127 mm trace and clearance |
| Copper | 87,187 track segments, 103.1 m total; planes stop 0.50 mm from the outline |
| Vias | 14,454, all drilled **0.30 mm** (JLC's free class): 13,028 @ 0.55 mm pad (0.125 mm ring), 534 @ 0.52 mm (0.110 mm), 892 @ 0.45 mm (0.075 mm) |
| Finish | ENIG — the bond-pad ring is meant for repeated crocodile-clip contact |
| Components | 5,425 footprints, 2,624 nets, **5,328 factory placements** (4,106 top / 1,222 bottom) |
| Not fitted | 56 DNP ballast caps (C101–C156) + the Pico 2 W site — by design |

## Verification, all re-run against this exact board

| Gate | Result |
|---|---|
| `tools/switchsim.py` — switch-level equivalence vs the visual6502 netlist | **PASS**, traces identical, test program correct |
| `tools/check_parity.py` — board vs netlist | 5,421 components, **0 errors** |
| `tools/check_gaps.py` — independent union-find over copper | **0 broken** nets |
| `kicad-cli pcb drc` | **2 errors** (both internal to the Pico library footprint — its own paste pads vs its own keepout, benign and DNP), **0 unconnected** |
| DRC warnings | 199 `hole_to_hole`, all **same-net** via pairs at a 0.22 mm hole gap — above JLCPCB's 0.20 mm minimum, and same-net holes merging is electrically harmless |

## Order settings that matter

- **Min via hole size: keep the default `0.3mm/(0.4/0.45mm)`.** The board was
  re-worked for it; do not pay for the 0.2 mm class.
- **Via covering: Epoxy Filled & Capped** — free on 6+ layers, and required
  here: 3,817 vias sit inside SMD pad copper and an open barrel in a pad wicks
  solder out of the joint at reflow.
- **PCBA type: Standard, both sides** — forced, not a preference: JLC's
  *Economic* assembly does not offer double-sided, and 1,222 of the 5,328
  placements are on the back.
- **Confirm Parts Placement: Yes**, and send the rotation note from
  `ordering.html` step 6 — LED and diode polarity is the one thing worth
  checking in their preview.
- Full step-by-step: open `ordering.html`.

## What changed since the first package (2026-07-25)

1. **FET → BSS138W, LCSC C504052** (2N7002W had no JLC stock; BSS138 was the
   M2-designated, SPICE-validated fallback).
2. **Pico series resistors populated** in the factory assembly.
3. **Silkscreen re-placed** so no text crosses pad copper — the fab subtracts pad
   openings from silk, and the first gerber review showed titles printing
   half-eaten. Band titles now use the longest wording that fits a pad-free
   block at a uniform height.
4. **Vias re-worked for the free 0.3 mm drill class** — pads grown to keep the
   annular ring (above), saving ≈ €25.
