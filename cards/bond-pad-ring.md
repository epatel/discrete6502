# bond-pad ring order

The 36-pad edge ring: how its positions are derived, the **known rev A defect** (4 pads out of die
order), and the fix to apply at any respin. Read before touching the ring block in
`tools/gen_pcb.py` (lines ~184-232) or before telling anyone to probe a pad by counting positions.

## What the ring is

36 pads = the 6502's full external signal set: 40 DIP pins − 3 NC (5, 35, 36) − the duplicated VSS
(pins 1 and 21). `EXTERNAL` in `tools/gen_netlist.py` lists them; each becomes a `TP<n>` testpoint
with `role="edge_pad"`, `origin=<signal>`, and `pos` = its die bond-pad coordinate.

`cclk` is **not** on the ring and must not be added — it is the internal clock node (visual6502
node 943, 284 polygons spanning x 342-8804, y 710-9791), not a pin. In JSSim a `cclk` metal shape
at the top-right die edge (x 7623-7893, y 9431-9791, layer 0, 270 × 360) reads as a pad and is
not one: real pads are ~400 × 400 (`clk0` area 158,238, `A7` 193,544, `R/W` 243,002) against this
shape's 76,156. It is clock distribution running along the top edge through the R/W driver.

Orientation matches JSSim, so side-by-side comparison with the sim is valid and is how the defect
below was spotted: JSSim draws `screen_y = grChipSize − die_y` (`wires.js drawSeg`), and
`gen_pcb.py:178` maps `board_y ∝ (maxy − die_y)`. Same handedness, no mirror.

## The rev A defect: 4 pads are in the wrong slot

**Fabricated boards carry this.** It is cosmetic, not electrical — verified against copper, all 36
pads sit on the net their silk names (`A6`'s pad is on net `ab6`), and the DIP numbers on the silk
are right too. Only the *slot* is wrong, so anyone locating a pad by counting positions off a die
photo is misled; anyone reading the silk is fine.

| Edge | As fabricated | Die / pinout order |
|---|---|---|
| L | SYNC, **A6**, A0, A1, A2, A3, A4, A5 | SYNC, A0…A5, **A6** |
| B | A7…A11, **VSS**, A12…A15, VCC | **VSS**, A7…A15, VCC |
| R | D0, D1, **R/W**, **D7**, D2…D6 | **R/W**, D0, D1, D2…D6, **D7** |
| T | NMI, IRQ, Φ1, RDY, RES, Φ2, S.O., Φ0 | identical — no error |

Displacements, from an exact re-simulation of `rim_slot` that reproduces every placed pad to
0.01 mm:

| Pad | projected (die-true) | placed | shift |
|---|---|---|---|
| A5 | 277.76 | 298.26 | +20.50 |
| **A6** | 294.46 | **178.46** | **−116.00** |
| D6 | 293.76 | 308.26 | +14.50 |
| **D7** | 309.85 | **194.85** | **−115.00** |
| **R/W** | 7.61 | **63.11** | **+55.50** |
| **VSS** | 11.20 (x) | **130.20** | **+119.00** |

## Why — two independent causes

Geometry (`gen_pcb.py:186-189`), all derived, not literal: `pad_mm` = 11.7, `rim_in` = 7.05,
`spacing` = `pad_mm + 8.0` = **19.7**, `corner` = `rim_in + 6.0` = **13.05**. Legal rim span is
therefore 13.05…308.95 on L/R and 13.05…277.65 on T/B.

**1. The die is denser than the pad pitch, and `rim_slot` is greedy.** It allocates in *component
order* (TP1…TP36 = ab0…ab15, db0…7, then the rest), nudging in ±0.5 mm steps to the first spot
≥ 19.7 mm from everything already placed. The address run projects to a 16.0 mm average pitch
(ab0 at 198.43 to ab6 at 294.46 = 96.03 mm over 6 gaps) against the 19.7 mm required, so each pad
shoves the next one further out. By A5 the accumulated push is +20.5 mm; A6 then needs ≥ 317.96,
past the 308.95 corner limit, so the outward search wraps around and takes the first free gap it
finds — which is *above* A0. D7 fails identically at the bottom-right corner.

**2. Two pads project into the corner exclusion outright.** `R/W` wants y 7.61 and `VSS` wants
x 11.20, both below `corner` = 13.05. They are relocated no matter what the allocator does; being
late in component order (TP32, TP35) they then land in whatever gap survives.

## The fix (respin only)

Replace the greedy nudge with an **order-preserving allocation per edge**. Order preservation
becomes structural instead of a lucky consequence of iteration order.

1. Group the pads by edge (the existing `min(d, key=d.get)` test), then **sort each group by die
   coordinate** — not by component order.
2. Feasibility check, and fail loudly if it does not hold: `(n − 1) × spacing ≤ span`. It holds
   comfortably on every edge, which is why this is fixable without changing `spacing` — L needs
   137.9 mm of 295.9, B needs 197.0 of 264.6, R needs 157.6 of 295.9.
3. Compute lower bounds by a forward sweep (`L[i] = max(corner, L[i−1] + spacing)`) and upper
   bounds by a backward sweep (`U[i] = min(hi − corner, U[i+1] − spacing)`); assert `L[i] ≤ U[i]`
   for all i (this is step 2 restated per-pad, and it is the assertion that must never be silent).
4. Place each pad at `clamp(want[i], L[i], U[i])`, then one final forward tightening pass to
   enforce the separation exactly.

That keeps every pad as close to its die-true position as the constraints allow while making
reordering impossible. (Exact minimum-displacement is PAVA/isotonic regression; the two-sweep
clamp is within a fraction of a millimetre here and far easier to keep correct.)

**Cost:** `gen_pcb.py` only, but it moves pad positions, so it forces the whole pipeline from
`gen_pcb.py` onward — placement, power, routing, finishing, silk, fab outputs. Rev B/C territory,
not a patch. Do not apply it to rev A: `gen/board_routed_golden.kicad_pcb` is what was fabricated
and its fingerprints are pinned in `gen/fab/RELEASE.md`.

**Verification after the fix:** re-run the order check — project each edge pad through `die2board`,
group by edge, and assert the placed order equals the die-coordinate order on all four edges. Cheap
enough to be a permanent gate; it would have caught this before fab.
