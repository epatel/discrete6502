# driver contention — the ratio bug, and its two retractions

Split out of `project-plan.md` on 2026-08-30, verbatim and unedited. **Read it whenever the
board's current draw, a hot site, rev B, or a series-resistor rework is in question.**

Read it also as a worked example of a claim being wrong twice in opposite directions: the model
was right, then falsified by a thermal image, then restored when a measurement showed the image
had been taken under the one workload that hides the effect. The status banner at the top of the
section carries that chain in order — follow it before quoting any number from below it.

Current standing (2026-08-29, in the plan's handoff, not here): 32 FETs are `cclk`-gated precharge
devices, 16 have the 10 k rework and 16 do not, and the un-reworked half is the named cause of the
supply trip.

## Driver contention: the power budget is wrong by 6x, and it is a ratio bug (2026-08-01)

> **⚠ STATUS, 2026-08-25: LARGELY RESTORED. This section was retracted on 2026-08-24 and the
> retraction has itself been retracted — read the 2026-08-25 handoff entry first.** The mechanism
> and the level problem always stood. The *power* figures were retracted because a FLIR image
> found no hot spot; on 2026-08-25 the same board running a real program through the Pico shows
> **discrete ~80 °C spots**, draws **2.3 A**, and draws the **same current at 500 Hz as at
> 10 kHz** — which is the signature of static contention and not of the distributed
> near-threshold conduction the retraction proposed. `tools/contention_duty.py` reconciles both
> images: the sites that were hot on 2026-08-25 contend 35% of the time under real code and 0.3%
> under the NOP free-run the 2026-08-24 image was taken in. What does NOT come back: the specific
> claim that the eight `dor` drivers are the worst offenders under all workloads (the address
> path is), and the 2.1 A total (measured 2.3 A, from a different site set).
>
> **Superseded detail retained below for the reasoning.** Thermal imaging of the real board found **no hot spot anywhere** (peak ~30 °C against
> 25 °C ambient), which a 0.9 W SOT-323 could not hide. The **mechanism and the level problem below
> stand** — the ratio error is real and a contended node at 1.0–1.9 V against a 1.1–1.5 V threshold
> is a genuine correctness bug. The **power figures do not**: the board draws 1.4 A unclocked and
> 0.7–1.2 A clocked, not 2.1 A, and the excess is distributed across thousands of near-threshold
> FETs (~210 µA each) rather than concentrated in a few fully-contending pairs.
>
> **⚠ THE DISTRIBUTED READING IS ITSELF NOW SCOPED, 2026-08-26.** With the Pico fitted and the clock
> *stopped*, board #1 draws **0.30 A** — the passive budget, as designed. The 1.4 A that motivated
> the distributed explanation was measured with **no Pico on the board**, so `clk0` (which has no
> pull-up), the data bus and reset were all **floating**. That condition really does drift the
> dynamic nodes and bias thousands of FETs near threshold. It is not the condition the board runs
> in. Executing, it draws **1.70 A**, and the 1.40 A above passive is contention at roughly 180 mA
> per contended net — the same quantity `sim/driver_contention.sp` puts at 262 mA worst case.
> Consequently rev B
> is a fix for *levels*, not for current, and no further hand rework is warranted.

Found by asking whether the MOnSter has a clock floor, reading its designer's answer, and then
re-deriving our own exposure instead of assuming the designs were equivalent.

**The mechanism.** Ratioed NMOS needs the pull-down several times stronger than its load. The
transform preserved topology but **not device ratios**: the 1,018 depletion loads became 10k
resistors (ratio 10k against 6 ohm — fine), but the **164 enhancement-mode VCC-side FETs kept the
same BSS138W as their pull-down**, giving a 1:1 ratio where the die had a deliberately weak load.

**Where it bites.** `tools/switchsim.py` on the real netlist shows 8 nets contended 47–93% of the
time (mean 6.7 at once) — all eight **data-bus output drivers**. `RnWstretched` gates their
pull-downs, so during every *read* the pull-down is on while the `dor` bit still holds stale write
data keeping the pull-up on. Reads dominate any program, hence the near-continuous duty.

| Net | Pull-up FET (gate) | Duty | Position (top face) |
|---|---|---|---|
| n1325 | Q3047 (dor0) | 47% | x 219.35, y 189.00 |
| n798 | Q401 (dor1) | 90% | x 219.35, y 200.20 |
| n520 | Q684 (dor2) | 85% | x 219.35, y 214.20 |
| n42 | Q1431 (dor3) | 89% | x 219.35, y 225.40 |
| n1076 | Q242 (dor4) | 84% | x 219.35, y 236.60 |
| n373 | Q205 (dor5) | 93% | x 219.35, y 247.80 |
| n7 | Q3238 (dor6) | 88% | x 215.65, y 261.80 |
| n298 | Q3580 (dor7) | 87% | x 215.65, y 275.80 |

None of the eight has a 10k resistor pull-up — the FET *is* the load. All eight are on the **top
face in one vertical column**, 11–14 mm apart, which is what makes rework practical.

**The numbers** (`sim/driver_contention.sp`, hand models calibrated to the datasheet 6.0 ohm
RDS(on) and cross-checked against the onsemi BSIM3v3 vendor model, which agrees within 20%):

| | 5 V | 3.3 V |
|---|---|---|
| Current per contended net (4.5 V gate) | 262 mA | 224 mA |
| Dissipation in the pull-up FET | **0.90 W** | 0.39 W |
| Extra supply current (6.7 nets) | **1.76 A** | 1.50 A |
| Extra board dissipation | **8.8 W** | 5.0 W |
| **Board total** | **≈2.1 A / ≈10.4 W** | ≈1.8 A / ≈6 W |

Against **220 mA continuous and ~0.3 W in SOT-323**, the current is over at ≥4 V gate drive and
the dissipation is over everywhere in the realistic band.

**Corroboration:** the MOnSter 6502 is published at 5 V, ~2 A, ~10 W — same logic, same style,
20% more parts. Our recorded 0.32 A / 1.6 W was the outlier, and the six-fold gap sat unexamined
in the plan for two weeks. Contention current is what fills it.

**The worse consequence is functional, not thermal.** A contended node does not reach a valid
low: Vout is 1.02 V at 3.5 V gate drive and 1.86 V at 5 V, against a receiving-gate threshold of
1.1–1.5 V. The data-out stage may read HIGH when it should read LOW — i.e. the CPU could write
wrong data. Heat is the symptom; the ratio is the disease.

**Verification blind spot (record this):** `switchsim._value()` returns low whenever `vss` is in
the group — it *assumes* the pull-down wins. The equivalence gate is therefore structurally
incapable of seeing a ratio error, which is why this survived five green gates. Also noted in
`cards/verification.md`.

### Rework options

**A — 10k in series with each of the 8 pull-up FETs. Recommended.**
**Illustrated step-by-step: [epatel.github.io/discrete6502/rework-dor-series-r.html](https://epatel.github.io/discrete6502/rework-dor-series-r.html)**
(source `docs/rework-dor-series-r.html` — a scale before/after diagram, true-scale renders of all
eight sites with their neighbouring designators, the coordinates, the procedure and its
verification steps). Both are generated from `gen/board_routed_golden.kicad_pcb`, so they stay
true to the board rather than to a drawing of it.
 Restores the ratio to exactly
what the other 1,018 nodes already have: **0.5 mA instead of 262 mA**, Vout ~3 mV instead of
1.86 V, and no speed cost because each of these nets drives exactly **one** gate (27 pF; a series
resistor up to ~337 kohm would still meet a 20 us rise, and 10k gives 0.6 us against a 25 us
half-cycle). **Simulated 2026-08-01, not merely argued** — `sim/revb_driver.sp` measures this exact
topology two stages deep to the db1 output pad and confirms all three claims (0.499 mA, 2.9 mV,
271 ns rise against a 25 us budget), with the db1 high level going *up* rather than down. The part is **10k 0402, C25744 — already in the BOM**, so no new sourcing. Method:
lift the pull-up FET's drain pin (the VCC side) and bridge pad-to-pin with the 0402. Eight sites,
top face, one column, well spaced. Function is preserved exactly: the FET still gates the load
with `dor`, it just stops being a 6-ohm load.

  **Method settled by measuring the copper, not by guessing.** The obvious move — cut the track
  between pad 3 and its VCC via, bridge the gap — does not survive inspection: that track is
  0.75 mm centre-to-centre but only **0.25 mm of it is bare** (the rest sits under the 0.93 x
  0.45 mm pad and the 0.55 mm via pad), and the via is epoxy-filled with mask over it, so there is
  no exposed copper on the far side to solder to. **Lift pin 3 instead** — it is the lone pin on
  its side of the SOT-323, 1.78 mm from pins 1 and 2, so neither neighbour is at risk — then stand
  the resistor on pad 3 and solder the lifted leg to its top. All eight sites are geometrically
  identical (0.25 mm track, 0.75 mm run, 0.55 mm via, nearest other component 1.94 mm), so it is
  the same operation eight times. 0603 is easier to handle than the board's 0402 and still fits.

**B — run at 3.3 V.** Halves the current but does not fix it: 0.39 W still exceeds the package,
and the low level is still invalid. A mitigation for first power-up, not a fix.

**C — do nothing, monitor temperature.** 0.8 W in a SOT-323 is roughly a 200 C rise. Expect
failure of the eight pull-ups, and suspect data-out corruption before that. Not viable.

**D — rev B netlist fix. IMPLEMENTED 2026-08-01, off by default.**
`DISCRETE6502_REV_B=1 python3 tools/gen_netlist.py` emits a series resistor for every VCC-side
FET **that has a pull-down to fight** — 142 of the 164 — not just these 8. The other 156 show only transient contention (adh1–7 at about 1.2% duty)
so they are not thermally urgent, but they carry the same ratio error and the same invalid-low
risk during their switching windows.

- **Off by default, and rev A output is byte-identical** (sha256 verified against the fabricated
  `gen/netlist.json`). Rev A is in production and its fingerprints are pinned in
  `gen/fab/RELEASE.md`; changing it silently would break `check_parity` and the release record.
- **A blanket 10k would have been wrong.** `cclk` drives 482 gates (13 nF) and `cp1` 198 (5.4 nF);
  10k there gives a 286 µs rise against a 25 µs half-cycle and destroys the clock. So the value is
  **sized per net from its own gate load**, keeping the RC rise inside 5 µs (20% of a half-cycle
  at the 20 kHz ceiling), and snapped to values **already in the BOM** so rev B needs no new part
  numbers: **158 × 10k, 5 × 1k, 2 × 100R**. The two 100R sites are the heavy clock nets.
- **The equivalence gate is green on rev B** — traces identical for half-cycles 20..219, program
  check PASS. `switchsim.py` learned the new `vcc_series` role: a resistor to VCC *is* a pull-up
  at switch level, so the mid node becomes weak-high and the FET passes that on. This makes the
  model's long-standing assumption — that a pull-down beats a load — **physically true rather
  than merely assumed**, which is precisely the blind spot recorded in `cards/verification.md`.
- **One real bug found while building it:** the generator has a fixed-point pass that drops FETs
  with a floating channel (it silently removes one, t1322, in rev A too — 165 emitted, 164 kept).
  In rev B that left the matching series resistor dangling on its own mid node. The drop rule now
  cascades to `vcc_series` resistors, so the fixed point converges with 0 singleton nets.
- **Scope checked rather than assumed (2026-08-01).** The worry was that some of the 164 might be
  deliberate push-pull *superbuffers*, where a strong pull-up is the point and a series resistor
  would be sabotage. Measured: **none are.** Every one of the 164 nets has exactly **one** pull-up
  FET against its pull-downs — the same 1:1 ratio error, uniformly — so the defect really is that
  wide and the fix is not defensive over-fitting.
- ~~**But 22 of them can never contend**, having no pull-down at all, so rev B now **skips
  those**~~ **— WRONG, corrected 2026-08-25. All 164 have a path to vss; the test only found
  transistors with `vss` directly on a channel pin and missed nets pulled low through a
  pass-gate chain. 21 of the 22 skipped are *measured* contending, including `adl6`/`adl7` at
  45.7%, the two busiest sites on the board. A rev B generated today leaves the hottest
  transistors unfixed. See `cards/rev-b-plan.md`. Original text follows:**
- **But 22 of them can never contend**, having no pull-down at all, so rev B now **skips those**:
  142 sites get a resistor, 23 are skipped (the extra one is t1322, whose FET the floating-channel
  pass drops anyway). That saves 22 parts and, more usefully, 22 nets on a board that was hard to
  route. Equivalence gate still green at 142 sites; rev A still byte-identical.
- Why 142 rather than only the 8 that measurably contend: **duty cycle is program-dependent.** The
  8 are where a counter loop happens to park. Different code exercises different drivers, and any
  contended net is invalid-low for as long as it lasts. The 8 are urgent *thermally*; the 142 are
  wrong *logically*.
- **The green gate is weak evidence here.** `switchsim` resolves any contention as low — the very
  blind spot that hid this bug. It confirms rev B did not break the topology; it cannot confirm
  the levels are now right.
- **SPICE now supplies the levels the gate cannot — rev B validated 2026-08-01**
  (`sim/revb_driver.sp`). A representative driver was taken out of `gen/netlist.json` rather than
  invented: `dor1 → Q401 → n798 → Q192 → db1`, i.e. the worst-measured contender (90% duty) carried
  **two stages deep to an actual chip output**, so the fix is judged by what leaves the CPU. Rev A
  and rev B are simulated side by side, at 5 V and 3.3 V, at typical and datasheet-max Vth.
  **Verdict: rev B works and is not a trade — every figure it touches improves.**

  | | rev A | rev B |
  |---|---|---|
  | Contention current (4.5 V gate) | 262 mA | **0.499 mA** (525x down) |
  | Contended level on n798 | 1.86 V (invalid) | **2.9 mV** (valid) |
  | db1 rise to 1.5 V | 18 ns | 271 ns — **90x inside** the 25 µs budget |
  | db1 fall | 2.8 ns | 2.7 ns (unchanged — R is not in the pull-down path) |
  | db1 high level | 3.81 V | **4.38 V** |
  | Peak supply current, one cycle | 346 mA | **0.92 mA** |

  Three findings that reasoning had not produced, each worth more than the confirmation:
  - **Rev B's high levels come out HIGHER, and the reason is physical.** db1 rising couples back
    into n798 through the next FET's Cgs (21 pF) — the ordinary bootstrap. In rev A the pull-up's
    drain is stiff VCC, so any push above VCC conducts backwards and dumps that charge into the
    supply; in rev B the same path is 10k, so the charge is kept (n798 probed decaying 5.16 → 5.10 V
    over 45 µs). A bonus, not something to depend on — it scales with the next stage's Cgs.
  - **The 3.3 V worst-Vth marginality is pre-existing, not rev B's doing.** The deck carries a
    rev A worst-Vth chain *specifically so the comparison cannot be rigged*, and it is rev A that
    fails: at 3.3 V with Vto = 1.5 V, rev A's db1 stops at **1.306 V and never reaches the 1.5 V
    threshold of the gate it drives**, while rev B reaches 1.579 V. Two source followers in series
    subtract Vth twice. Independent support for the existing position that 3.3 V is the tighter
    operating point, not the safer one.
  - **One real caveat, and it is the only one: the two 100R sites.** Contended, a 100R dissipates
    **200 mW in an 0402 rated 0.0625 W — 320% of rating** (10k: 2.5 mW/4%; 1k: 24 mW/39%). Those two
    are `cclk` and `cp1`. At normal running it is harmless (~1 µs per edge at 20 kHz, ~4% duty,
    ~8 mW mean); it bites in exactly one situation — **a stopped clock with `cclk` parked
    contended, which is what the retention test deliberately creates.** If rev B is ever fabricated:
    0805 (0.125 W) at those two sites, or keep stalls there sub-millisecond.

  The clock was checked separately as the one site where rev B could break the CPU rather than one
  driver: `cclk` (13 nF behind 100R) keeps its high level to within 2 mV (4.141 vs 4.143 V), rises
  in 0.98 µs — **25x inside a half-cycle** — falls identically, and gains a valid low
  (1.86 V → 0.26 V). Pad capacitance was swept 20–500 pF since 50 pF was an estimate; it moves the
  rise 207 ns → 1.41 µs and the level not at all, so the estimate does not need to be right.
  **What this does not prove:** one chain out of 142. It shows the fix is sound and affordable, not
  that every site is safe.
- Component count: 5,563 for rev B against 5,364 for rev A (+142 resistors, −1 dropped FET pair).
  A rev B board would need the full pipeline re-run from `gen_pcb.py` onward, including placement
  and routing, so this is a real respin, not a patch.

**Immediate consequences regardless of choice:** the bench supply must be rated **3 A, not 1 A**;
USB-only demo mode is **not viable at 5 V**; and the first clocked power-up should be at 3.3 V
with a hard current limit, watching for the step from ~0.3 A to ~1.8 A that says contention is
real on copper.


