# rev B: what a respin must change

Everything known to be wrong with rev A that only a new board can fix, with the evidence for each
and the order to do it in. Read before running `DISCRETE6502_REV_B=1` or touching
`series_r_for` in `tools/gen_netlist.py`. **Item 1 is already applied**; the rest is not.

**Nothing here is urgent.** Rev A works: board #1 executes programs, and every defect below either
has a hand rework or is cosmetic. This is the list to apply *if* a board is ever fabricated again.

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
four edges.

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
  die's. Rev C territory at most.

---

## 6. Order of work, and what it costs

A respin re-runs **the entire pipeline from `gen_pcb.py` onward** — placement, power, routing,
finishing, silk, fab outputs — because both the resistor count and the pad positions change. Budget
that, not an afternoon.

1. ~~Fix `has_pulldown`~~ — **done 2026-08-25**, see item 1.
2. Bump the two clock sites to 0805 (item 2).
3. Apply the bond-pad order fix and its assertion (item 3).
4. Re-run `switchsim.py` — must stay green on both revs.
5. Promote `contention_duty.py` to a gate (item 4) and require **zero** unprotected contending sites.
6. Re-run `sim/revb_driver.sp` on a driver from the *newly included* set (an `adl`, not a `dor`) —
   the existing deck validates the topology that was already covered.
7. Full board pipeline, then the four board gates: `check_parity.py`, `check_gaps.py`,
   `extract_netlist.py`, `kicad-cli pcb drc`.
8. New fab package, new `RELEASE.md` fingerprints.

**Component delta:** rev A 5,364 → rev B ~5,585 (+164 resistors, −1 FET the floating-channel pass
drops). All values already in the BOM, so no new part numbers except the two 0805s.

---

## 7. Open

- **Does fixing all 164 route?** 164 extra nets on a board that needed 6 layers for 8,421
  connections. Unknown until tried; the router is warm-startable so it is a run, not a redesign.
- **Is the hand rework enough to skip rev B entirely?** After 8 + 16 = 24 sites reworked by hand,
  board #1 will have the measured contenders covered. If the current comes down and the functional
  test passes, a respin may never be worth it — which is the likeliest outcome and should be said
  plainly rather than assumed away.
