# rev B: what a respin must change

Everything known to be wrong with rev A that only a new board can fix, with the evidence for each
and the order to do it in. Read before running `DISCRETE6502_REV_B=1` or touching
`series_r_for` in `tools/gen_netlist.py`. **Section 0 holds the binding rules for any respin**
(pad positions, power pads) and is a user directive. **Item 1 is already applied**; the rest is not.

**Nothing here is urgent.** Rev A works: board #1 executes programs, and every defect below either
has a hand rework or is cosmetic. This is the list to apply *if* a board is ever fabricated again.

---

## 0. Rules for rev B [user directive, 2026-08-31]

**Rev B has not been generated or fabricated, so rev B is the next board and everything planned
lands in it.** Do not defer anything here to a later revision — there is no rev C on the roadmap,
and an item pushed past rev B is an item that will not be built. Each rule carries a machine-checked gate, because this
card exists to record that *five green gates missed the ratio defect* and that the pad-order defect
below would have been caught by a five-line assertion. A rule without a gate is a comment.

### R1 — Bond pads sit at their die-true positions, in die order, on all four edges

Rev A ships with **A6, VSS, D7 and R/W in the wrong slot** (item 3 below), which pushes A0–A5 one
slot off the die. Nothing is miswired, but the ring is the part of the board that is supposed to
*be* the die, and a ring you cannot read by position has lost the thing it was for.

- Allocate **per edge, sorted by die coordinate** — never in component order. Forward/backward bound
  sweep then clamp, worked out in full in `cards/bond-pad-ring.md`.
- **Gate:** project every edge pad through `die2board`, group by edge, assert the placed order equals
  the die-coordinate order on all four edges. Assert the feasibility condition
  `(n − 1) × spacing ≤ span` *before* placing, and fail loudly — never silently relocate.
- Displacement from die-true is minimised but not zero: `R/W` projects to y 7.61, inside the
  `corner` = 13.05 exclusion, so it clamps to 13.05. That is acceptable **because order is
  preserved**; reordering is not.
- Until a respin exists, the rev A rule stands unchanged: **locate a pad by its silk label, never by
  counting.**

### R2 — VCC and VSS are power, not signals: take them off the ring's order constraint

They are the two pads nobody probes and the two that carry amps. Treat them separately:

- **Primary connection: large solderable pads on B.Cu**, one per rail, sized for a hand-soldered
  wire or a bolted ring terminal — the bench needs **5 V at ≥ 3 A on a real connector, not croc
  clips**, which has blocked the acceptance run since 2026-08-28.
- **Ampacity lives in the via array, not the plane.** In1 (GND) and In4 (VCC) are full pours ~290 mm
  wide; at 1 oz that is ≈ 1.1 squares end to end, **≈ 0.6 mΩ** — a single feed point per rail is
  electrically fine and a second one buys nothing. What must be sized is the drop from pad into
  plane: budget **≥ 20 × 0.3 mm vias per pad** (~1 A each, conservatively) for 3 A with wide margin.
- **Optional and cheap:** keep a *ring* pad for each rail as a voltage-reference probe point, placed
  in whatever slot survives after the 34 signal pads are allocated. It is a reference, not a feed —
  do not deliver current through it.
- **Gate:** assert both power pads exist on B.Cu, that each has ≥ 20 vias landing in its plane, and
  that neither appears in the die-order check of R1.

**R2 is what makes R1 achievable.** The ring is 36 pads (40 DIP pins − 3 NC − the duplicated VSS);
dropping VCC and VSS leaves **34 signals**, and both come off **edge B**, the most crowded edge —
which needs `(11 − 1) × 19.7 = 197.0 mm` of its 264.6 mm span today and only **157.6 mm** with 9
pads. That is **39.4 mm of new slack on precisely the edge where the allocator was running out**.
Better still, `VSS` projects to x 11.20, *inside* the 13.05 corner exclusion — so it can never be
placed die-true at all. Removing it deletes an unsatisfiable constraint rather than working around
one.

### R5 — A whole-board current budget, computed and gated, with every parked state enumerated

**Rev A was never asked how many amps it draws.** Five gates checked topology, `contention_duty.py`
later checked strength *per site*, and none of them ever produced a number for the board. The bill
for that omission is most of 2026-08-24 → 08-31: a folded 2.4 A charger, a tripped 3 A adapter, a
week of brownouts read as firmware bugs, sixteen transistors cooked while the board sat unattended,
and five successive models falsified at the bench. **This gate is not optional for rev B.**

Write `tools/power_budget.py`. It must emit **absolute currents, not verdicts**, for three classes
of state, and fail against a budget stated up front:

**(a) Parked / quiescent states — enumerated exhaustively. This is where rev A was lost.** The board
spends almost all of its life parked, and rev A's *default* parked state turned out to be the worst
one available to it: `clk0` above threshold ⇒ `cclk` high ⇒ **all 32 `cclk`-gated precharge FETs
conducting continuously at 100% duty**, which is worse than clocking (~50%). Every combination that
a bench or a power-up can produce must appear in the table, with a current: `clk0` high / low /
undriven, `res` asserted / released, data bus driven / floating, Pico fitted / absent. **A state
with no row is a state nobody checked**, which is exactly how rev A shipped.

**(b) Running states, swept over addresses.** Item 4's lesson applies unchanged: duty is
address-dependent, and a short run pins the address and reports 0% for every bit that happens to sit
high. Sweep, or the gate certifies sites that contend heavily in real use.

**(c) Per-part dissipation against package rating.** A board total hides both failures rev A
actually had: the two 100 Ω sites at **320% of an 0402's rating** (item 2), and the sixteen
precharge sites that were individually cooking inside an otherwise unremarkable total. Fail any part
above **60%** of rating in any state from (a) or (b).

Everything needed is already in `gen/netlist.json`, so this is arithmetic over the netlist plus the
existing switch-level model — not a new simulator:

| contributor | count | per-device | notes |
|---|---|---|---|
| pull-up resistors, 10 kΩ | 1,018 | 0.5 mA | **509 mA** if all pulled low at once — the passive ceiling, and it matches the 0.548 A floor measured on board #1 |
| VCC-side FETs | 164 | **262 mA** unprotected, 0.5 mA with the rev B series resistor | the ratio defect |
| `cclk`-gated precharge FETs | 32 | 262 mA | all on together whenever `cclk` is high; 16 were reworked by hand on board #1, 16 were not |
| LED gate taps | 55 | ~1.4 mA | ~77 mA total |

**Calibration requirement, and it is the part that makes this a gate rather than a spreadsheet: it
must run on rev A and reproduce rev A's measured failure.** Specifically it must show the parked
`clk0`-high state drawing amps, and the two 100 Ω sites over rating. **A gate that cannot reproduce
the fault it was written for is not a gate** — that is the same error as `switchsim._value()`
assuming the pull-down wins, committed one level up. Run it against rev A first, check it against
the bench numbers (0.24 A quiet, 0.5 A clocked, 1.5–2.5 A parked hot), and only then trust its rev B
answer.

**Budget for rev B, to be argued before the run rather than after:** no parked state above the
509 mA passive ceiling plus margin, and no state at all that a 3 A bench supply cannot hold with
headroom. If rev B cannot meet that, it is better to know it from a script than from a thermal
camera.

### R3 — Any change to pad position, pitch or footprint forces the whole pipeline


`gen_pcb.py` onward: placement, power, routing, finishing, silk, fab outputs, new `RELEASE.md`
fingerprints. Both R1 and R2 move pads, so a respin re-runs everything regardless — which is the
argument for applying every accumulated fix in one go rather than trickling them. Re-pass all four
board gates (`check_parity.py`, `check_gaps.py`, `extract_netlist.py`, `kicad-cli pcb drc`) and keep
`switchsim.py` green on both revs.

### R4 — Never apply any of this to rev A

`gen/board_routed_golden.kicad_pcb` is what was fabricated and its fingerprints are pinned in
`gen/fab/RELEASE.md`. Rev B writes its own files (`gen/netlist_revb.json`,
`gen/discrete6502_revb.net`), and anything further must do the same.

---

## 1. ~~The site filter is wrong~~ — FIXED: a resistor on all 164, not 142

**This is the one that changes rev B's output, and it was found by a thermal camera.**

Rev B adds a series resistor to each enhancement-mode VCC-side FET, restoring the load ratio that
the netlist transform lost. Until 2026-08-25 it emitted **142** of the 164, skipping the ones with
no pull-down on the grounds that they "can never contend". The test was:

```python
has_pulldown = set()
for tid, g, c1, c2, pos in kept:
    if vss in (c1, c2):                    # <-- vss DIRECTLY on a channel pin
        has_pulldown.add(net(c2 if c1 == vss else c1))
```

It only counts a transistor with `vss` on one of its own channel pins. **A net pulled low through a
pass-gate chain does not match, and contends exactly the same way.**

Measured, not argued (`tools/contention_duty.py`, 300 half-cycles, two workloads):

| | count |
|---|---|
| VCC-side nets | 164 |
| …with a **direct** pull-down (what the filter tests) | 142 |
| …with **no other FET channel at all** (genuinely cannot contend) | **0** |
| …**measured contending** in at least one workload | 40 |
| …of those 40, **missed by the filter** | **21** |

So the "22 that can never contend" are not a real category — every one of the 164 has some path to
vss, and 21 of the 22 skipped are *measured* contending. The skipped set includes **`adl6` and
`adl7` at 45.7% duty, the two busiest sites on the whole board**, above every `adh` and every `dor`.

**FIXED 2026-08-25.** The filter is gone; `tools/gen_netlist.py` emits a series resistor on all
164. The original reason for skipping — 22 fewer parts and 22 fewer nets to route on a board that
was hard to route — does not survive the measurement, and a resistor on a net that never contends is
harmless (the ratio is correct either way). Verified on generation:

```
vcc_series_resistors         164      (was 142)
components_total            5585      (rev A 5421, +164)
singleton_nets                 0
```

164 mid nodes, each joining exactly one `vcc_series` resistor and one `vcc_side` FET, **0
malformed**, and **0 vcc_side FETs left wired straight to VCC**. `switchsim.py` is green on rev B —
traces identical for half-cycles 20..219, `PROGRAM CHECK: PASS` — and rev A's `gen/netlist.json` is
byte-identical (sha256 `20001712d1…`).

**Rev B now writes its own files**, `gen/netlist_revb.json` and `gen/discrete6502_revb.net`. It used
to share the path with rev A, so a rev B run silently overwrote the netlist the fabricated board is
checked against, and the only thing restoring it was remembering to re-run without the flag. Both
are gitignored: regenerable, and not what any board was built from. To simulate rev B:
`DISCRETE6502_REV_B=1 python3 tools/switchsim.py`.

> **A rev B respin generated today would leave the hottest transistors on the board unfixed.**
> This same flawed test also excluded `adl4`–`adl7` from the first contention measurement, until the
> FLIR put them back. It has now caused the same error twice, in two different tools.

**Related, same root cause:** `tools/contention_duty.py` originally carried the identical filter and
it has been removed there. Do not reintroduce it anywhere. The general rule for this codebase, third
time of writing: **ask which pin is the rail, and follow conduction paths — never assume a net's
pull-down is a single transistor, and never count FETs *gated by* a net when you mean FETs *on* it.**

---

## 2. The two 100R sites need an 0805, not an 0402

`series_r_for()` sizes each resistor from its net's gate load so the RC rise stays inside 5 µs. Two
nets are big enough to land on **100 Ω**: `cclk` (482 gates, 13 nF) and `cp1` (198 gates, 5.4 nF).

Contended, a 100 Ω resistor dissipates **200 mW in an 0402 rated 0.0625 W — 320% of rating**
(10k: 2.5 mW / 4%; 1k: 24 mW / 39%). At normal running this is harmless: ~1 µs per edge at 20 kHz is
~4% duty and ~8 mW mean. It bites in exactly one situation — **a stopped clock with `cclk` parked
contended**, which is precisely what the retention test creates deliberately.

**Fix:** 0805 (0.125 W) at those two sites, or keep clock stalls sub-millisecond. Recorded in
`project-plan.md` 2026-08-01; unchanged by anything measured since.

---

## 3. The bond-pad ring is out of die order

4 of the 36 pads sit in the wrong slot: **A6, VSS, D7, R/W**, which pushes A0–A5 one slot down from
where the die puts them. Nothing is miswired or mislabelled — every pad carries the net its silk
names — so this is cosmetic, but it means **you locate a pad by its label, never by counting**.

Cause and the order-preserving fix (allocate per edge in die-coordinate order with a
forward/backward bound sweep) are fully worked out with feasibility numbers in
`cards/bond-pad-ring.md`. It was deliberately not applied to rev A because it moves pad positions
and so forces the whole pipeline from `gen_pcb.py` onward.

**A respin is exactly when to apply it**, since the pipeline is being re-run anyway. Add the cheap
permanent gate the card suggests: assert the placed order equals the die-coordinate order on all
four edges. This is now **rule R1** in section 0, and **R2** (VCC/VSS off the ring) is what gives the
allocator the 39.4 mm of slack on edge B that makes it comfortable rather than marginal.

---

## 4. Add a strength gate, because five green gates missed this

The ratio defect passed **switch-level equivalence, board-vs-netlist parity, independent copper
connectivity, DRC, and reverse extraction from copper**. All five check *topology*. None checks
*strength*. `switchsim._value()` returns low the moment `vss` joins the conduction group — it
*assumes* the pull-down wins, which is the very thing that was wrong.

`tools/contention_duty.py` is the missing gate in embryo: it measures, in the same model, how often
each VCC-side device conducts while its net reaches vss. **Promote it to a gate for rev B:** fail if
any VCC-side FET without a series resistor shows non-zero duty under either workload. On rev B that
should be *no sites at all*, which makes it a clean pass/fail rather than a threshold to argue about.

**Sweep the address, do not trust one run.** Duty here is *address*-dependent: `adh` is the high
byte of the address during a fetch, so a short simulation pins the address and reports 0% for every
bit that merely happens to be high. A 150-cycle run at PCH = `$EA` reports `adh1/3/5/6/7` quiet; the
same run at PCH = `$00` reports all eight at 48%. Any gate built on this must exercise a range of
addresses, or it will certify sites that contend heavily in real use — which is exactly the error
this card was written to record, committed a second time in the measurement rather than the
generator.

---

## 5. What rev B does NOT need to change

Recorded so a respin does not "fix" things that measured fine:

- **Charge retention / the clock floor.** Measured **1.9–2.3 nA per FET** on board #1, against a
  53 nA budget — floor 456–871 Hz against a 20 kHz ceiling, a 23–44× window with ~45 °C of headroom.
  The design's most-doubted assumption is comfortably true.
- **On-board clock regeneration and the pass-gate bootstrap.** Both confirmed on hardware by the PC
  ripple result. No change wanted.
- **Decoupling on the board itself.** 96 × 100 nF + 4 × 10 µF = 49.6 µF. Rail ripple is audible
  (MLCC singing at the clock rate), but the evidence points at the **supply path**, not the board —
  fix that with a bulk electrolytic at the bond pads and shorter leads before spending board area.
- **The 3.3 V marginality.** Real, but *pre-existing and not caused by rev B*: at 3.3 V with
  worst-case Vth, rev A's `db1` stops at 1.306 V and never reaches the 1.5 V threshold it drives,
  while rev B reaches 1.579 V. Rev B improves it. See `cards/verification.md`.
- **LEDs.** Bus and IR taps were considered and closed 2026-08-09 — they would duplicate what the
  Pico already captures, and 7-segment decode would need ~1,200 FETs of *our* logic rather than the
  die's. Not reopened for rev B.

---

## 6. Order of work, and what it costs

A respin re-runs **the entire pipeline from `gen_pcb.py` onward** — placement, power, routing,
finishing, silk, fab outputs — because both the resistor count and the pad positions change. Budget
that, not an afternoon.

1. ~~Fix `has_pulldown`~~ — **done 2026-08-25**, see item 1.
2. Bump the two clock sites to 0805 (item 2).
3. Apply the bond-pad order fix and its assertion (item 3 / **R1**), with VCC and VSS removed from
   the ring first (**R2**) — that order matters, since dropping the two power pads is what frees
   edge B.
3b. Add the B.Cu power pads and their via arrays (**R2**), and their gate.
4. Re-run `switchsim.py` — must stay green on both revs.
5. Promote `contention_duty.py` to a gate (item 4) and require **zero** unprotected contending sites.
5b. **Run `tools/power_budget.py` (R5) against rev A first to calibrate it, then against rev B**
   — parked states, swept running states, and per-part dissipation. No board goes to fab without a
   current number for every parked state.
6. Re-run `sim/revb_driver.sp` on a driver from the *newly included* set (an `adl`, not a `dor`) —
   the existing deck validates the topology that was already covered.
7. Full board pipeline, then the four board gates: `check_parity.py`, `check_gaps.py`,
   `extract_netlist.py`, `kicad-cli pcb drc`.
8. New fab package, new `RELEASE.md` fingerprints.

**Component delta:** rev A 5,364 → rev B ~5,585 (+164 resistors, −1 FET the floating-channel pass
drops). All values already in the BOM, so no new part numbers except the two 0805s. The R2 power
pads add copper, not parts.

---

## 7. Open

### Package and pitch — decide before the pipeline runs, because rev B is the only chance

Raised 2026-08-31: a smaller FET package. The die→board transform maps onto a fixed **71 × 105 cell
raster** and `PITCH` only sets the cell size, so **shrinking the pitch costs nothing in fidelity** —
every transistor lands in exactly the cell it occupies today. What shrinks with it is the routing
channel (1.00 mm in x) and the service channel (1.05 mm in y). Footprint pad extents measured from
the KiCad libraries; the model reproduces rev A's 290.7 × 322.0 mm and 11.7 mm bond pad exactly:

| package | footprint | pitch | board | area | vs rev A | x-channel |
|---|---|---|---|---|---|---|
| **SOT-323 (rev A)** | 2.70 × 1.75 | 3.70 × 2.80 | 290.7 × 322.0 | 9.36 dm² | — | 1.00 mm |
| SOT-523 | 1.80 × 1.40 | 2.80 × 2.45 | 226.8 × 285.2 | 6.47 dm² | −31% | 1.00 mm |
| SOT-723 | 1.60 × 1.20 | 2.60 × 2.25 | 212.6 × 264.2 | 5.62 dm² | **−40%** | 1.00 mm |
| DFN1212 | ~1.40 × 1.40 | 2.40 × 2.45 | 198.4 × 285.2 | 5.66 dm² | −40% | 1.00 mm |
| **SOT-723, split** | 1.60 × 1.20 | **3.10 × 2.25** | 248.1 × 264.2 | 6.56 dm² | −30% | **1.50 mm** |

**You cannot spend the same millimetre twice.** Minimum pitch takes 40% off the area and leaves
rev A's channels — so still 6 layers. Keeping the 3.7 mm pitch spends the whole gain on a ~2.1 mm
channel instead. **The money says spend it on channels:** area-driven line items (PCB large-size
€22.84 + ENIG €24.24 + board €54.46 + PCBA large-size €50.47) are ≈ €30/board, so −30% area is worth
≈ €9/board, against **€40–70/board** for the sixth layer. The split row gets most of both.

**Do not pick DFN1212.** It ties SOT-723 on area and gives up pin access — and the method that
located every fault on board #1 (Q2577) is an **in-circuit gate-to-drain reading compared against
the matched twin on an adjacent bit**, which needs probeable pins. Gate nets are dynamic and carry
no passive, so there is no other way onto them. With 0.5–2 defects/board expected and two hand
transplants already performed, that is not a tradeable asset.

**Three things that do not scale, and one may be the real bound:**
- **Bond pads shrink with the die** (11.7 → 8.2 mm at full shrink) and ring `spacing` with them,
  which tightens R1 rather than relaxing it. Re-run R1's feasibility assertion at the candidate
  pitch before committing.
- **The Pico 2 W antenna keepout is a fixed ~42 × 18 mm** all-layer exclusion currently tucked in the
  die's gap. The gap scales; the keepout does not. Fallback is moving it to the margin band.
- **Via spacing has zero headroom.** Rev A already ships 199 `hole_to_hole` warnings at 0.22 mm
  against JLC's 0.20 mm floor, and power stitching uses per-cell via sites on the 1.4 mm `SLOT_P`
  raster. A 30% pitch cut removes 30% of the slots per row. **Expect this, not the footprint, to
  bound the shrink.**

**Cheap next step, no parts needed:** make `PITCH` and the FET footprint parameters of
`gen_pcb.py`, then run `gen_pcb.py` + `route_power.py` at a candidate pitch and see whether power
stitching still completes. That answers the binding question for the cost of a run.

**Also unresolved:** whether JLC stocks a suitable N-channel FET in SOT-523 or SOT-723 at ~20k depth
in the cheap part class, and at what price. A smaller package does **not** reliably mean a cheaper
part — the die does not shrink with the outline, and SOT-323 is the mainstream deep-stock outline.
Parts are €101.05/board of the ≈ €243 landed, ~€0.018–0.022 per FET, so a €0.005 swing is ~€20/board
and it can go either way. Look this up before committing.


- **Does fixing all 164 route?** 164 extra nets on a board that needed 6 layers for 8,421
  connections. Unknown until tried; the router is warm-startable so it is a run, not a redesign.
- **Is the hand rework enough to skip rev B entirely?** After 8 + 16 = 24 sites reworked by hand,
  board #1 will have the measured contenders covered. If the current comes down and the functional
  test passes, a respin may never be worth it — which is the likeliest outcome and should be said
  plainly rather than assumed away.
