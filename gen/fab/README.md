# discrete6502 — JLCPCB fabrication package

Generated 2026-07-25 from `gen/discrete6502.kicad_pcb` (git 93360f0+).

## Files
- `discrete6502_gerbers.zip` — 6 copper layers, silk, mask, paste, edge cuts, Excellon drill
- `discrete6502_bom.csv` — 9 line items, 5,328 SMD placements/board
- `discrete6502_cpl.csv` — placement file (4,106 top / 1,222 bottom)

## Order settings
- 6 layers, 291 x 322 mm, 1.6 mm FR-4, HASL or ENIG (ENIG recommended: croc-clip
  bond pads wear), min trace/space used: 0.127 mm, min via: 0.45/0.2 mm
- Standard PCBA, double-sided assembly, qty 5 boards
- The Pico module site and 56 ballast-cap footprints are intentionally unpopulated
  (excluded from BOM/CPL); THT bond-pad ring is unassembled by design

## Order-time checklist
1. **FET stock (the big one):** BOM uses 2N7002W SOT-323, LCSC `C139444`
   (Diodes 2N7002W-7-F). 5 assembled boards need ~20,300 pcs (+attrition).
   Live LCSC stock was only ~4.4k at package time — use JLCPCB Global
   Sourcing / pre-order stock, or switch to another in-stock 2N7002W
   SOT-323 (budget alt: Shikues `C5334591`). Any 2N7002W-compatible works;
   design was SPICE-validated on generic 2N7002 parameters.
2. Confirm stock for the 0402 passives (10k x 1,023/board is the other bulk item).
3. In the JLCPCB part-placement preview, check polarized parts: LEDs (D1-D55)
   and 1N4148WS diodes (D56-D67) — fix rotations in their UI if mismatched.
4. Silk overlaps the FET field in places (region titles) — intentional, ink
   clips over pads; no action.
5. Real quote will differ from estimate mainly on the 6-layer large-format
   PCB line (est. $500-750/5) — sanity-check before paying.
