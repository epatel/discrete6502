# jlcpcb-constraints

JLCPCB fabrication/assembly limits that bound the board design (snapshot of https://jlcpcb.com/capabilities/pcb-capabilities, fetched 2026-07-18 — re-verify before ordering).

Fabrication (rigid FR-4):

- Layers: 1–32; standard thicknesses 0.4/0.6/0.8/1.0/1.2/1.6/2.0 mm.
- Min trace/space at 1 oz copper: 0.10/0.10 mm (4/4 mil) for 1–2 layers; 0.09/0.09 mm (3.5/3.5 mil) multilayer. At 2 oz: 0.16/0.16 mm (2-layer), 0.15/0.15 mm (multilayer).
- Vias: hole 0.15–6.3 mm (multilayer); via-to-via spacing min 0.2 mm; pad-to-hole min 0.45 mm.
- Max board size: 670 × 600 mm (2-layer), 656 × 586 mm (6+ layers) — far larger than anything this project needs, so board size is bounded by cost and assembly, not fab.
- Min BGA pad 0.2 mm; 0.2–0.25 mm BGA pads require ENIG finish (relevant only if fine-pitch parts sneak in; discrete transistors won't hit this).

Assembly implications for this project:

- ~4,000+ SMT placements per board: per-joint/per-part assembly fees dominate cost — prefer parts in the **economic** assembly class and minimize unique part numbers (extended parts add a per-reel fee).
- Choose a transistor package that is cheap, in deep JLCPCB stock, and economic-class (e.g., SOT-23 or smaller like SOT-323/SOT-723; smaller packages shrink the board but check economic-class eligibility and stock depth before committing).
- Double-sided assembly is offered but costs more; single-sided placement is preferable if the size target allows.
- Verify stock quantity before ordering: one board consumes thousands of the same MOSFET; multiply by board quantity.
