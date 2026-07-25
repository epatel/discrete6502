# discrete6502 — JLCPCB fabrication package

Generated 2026-07-25 from `gen/discrete6502.kicad_pcb` (git 93360f0+).

## Files
- `discrete6502_gerbers.zip` — 6 copper layers, silk, mask, paste, edge cuts, Excellon drill
- `discrete6502_bom.csv` — 9 distinct parts in 22 rows (Designator cells chunked to
  <=2000 chars; JLC rejects anything over 2048), 5,328 SMD placements/board
- `discrete6502_cpl.csv` — placement file (4,106 top / 1,222 bottom)

## Order settings
- 6 layers, 290.7 x 322 mm (~9.4 dm2), 1.6 mm FR-4, HASL or ENIG (ENIG recommended: croc-clip
  bond pads wear), min trace/space used: 0.127 mm, min via: 0.45/0.2 mm
- Standard PCBA, double-sided assembly, qty 5 boards
- The Pico module site and 56 ballast-cap footprints are intentionally unpopulated
  (excluded from BOM/CPL); THT bond-pad ring is unassembled by design

## Order-time checklist
1. **FET = LCSC `C504052`** (JSCJ BSS138K, SOT-323) — chosen 2026-07-25 for
   stock; BSS138 was the project's pre-approved fallback FET and is fully
   SPICE-validated (Vth 0.8-1.5V even helps the 3.3V bring-up). 5 assembled
   boards need ~20,300 pcs (+attrition) — confirm quantity at order.
   Fallbacks if it dries up: any 2N7002W/BSS138W in SOT-323 with
   Vgs(th) <= 2.5V and Ciss <= 60pF (never SOT-23, never AO3400-class).
2. Confirm stock for the 0402 passives (10k x 1,023/board is the other bulk item).
3. In the JLCPCB part-placement preview, check polarized parts: LEDs (D1-D55)
   and 1N4148WS diodes (D56-D67) — fix rotations in their UI if mismatched.
4. Silk overlaps the FET field in places (region titles) — intentional, ink
   clips over pads; no action.
5. Real quote obtained 2026-07-25 (5 boards, ENIG, both sides):
   PCB EUR 131.44 + PCBA EUR 716.38 + UPS Express Saver EUR 64.54,
   plus ~25% Swedish import VAT => ~EUR 1,140 landed, ~EUR 230 per
   assembled CPU. The earlier $500-750 PCB estimate was pessimistic.
6. PCB and PCBA show as two linked line items under one order header --
   they are not duplicates; deleting one un-pairs the order with no undo.
