# Handoff — the stack-pointer defect, and the 23-subtest self-test

**Written for a fresh agent, 2026-08-30.** Assumes `CLAUDE.md` and `project-plan.md` and
nothing else.

**Scope, and what this does NOT cover.** This is the thread that ran from `FAILED at $02F3`
on 2026-08-26 to a repaired CPU passing 23 datapath subtests on 2026-08-28. The *concurrent*
bench-power thread — the supply collapse, the `clk0` pull-down, the unresolved
undriven-vs-driven contradiction — is a **different agent's log: `docs/session-2026-08-30.md`.
Read that one for the state of the bench.** Where the two touch, §6 below says so explicitly.

Full detail with every measurement: `docs/stack-decrement-defect.md` (742 lines).

---

## 1. The headline

**Board #1's CPU works.** It passes a 23-subtest datapath self-test covering registers and every
transfer between them, the ALU with carry and borrow, shifts, the stack in both directions with S
tracking correctly, flag save/restore, zero-page and absolute-indexed addressing, and JSR/RTS.

That is far past the 2026-08-25 NOP free-run, which proved only fetch, decode and the PC. This
proves it **computes**.

**The fault that caused `FAILED at $02F3` was one leaking transistor out of 4,051.**

---

## 2. Q2577 — the defect, the chain, the repair

**Q2577** (pull-down, gate `s0`, source `vss`, drain `n983`, x 75.05 y 183.40, top face) had a
**20 kΩ gate-to-drain leak against 177 kΩ on its matched twin Q3793**.

`n983` carries a 10 kΩ pull-up (`R585`). `s0` is a **pure dynamic node with no pull-down of its
own**. So the leak tied S bit 0 to something permanently high:

```
Q2577 gate-drain leak (20k)
  -> s0 held high, and nothing on the board can pull it down
  -> S bit 0 can never fall
  -> PHA cannot decrement S
  -> RTS pulls flag bytes instead of a return address
  -> PC lands in the zero-filled void, $00 = BRK
  -> int_trap at $02F3  ==  "FAILED at $02F3, listing line 367"
```

It also explains a reading that looked strange at the time: `s0` measured **30 kΩ to *both*
rails** where `s1` read 150 kΩ to both — symmetric, because through Q2577 it inherited `n983`'s
pull-up to VCC *and* Q2577's own source to VSS. A rail short would have been asymmetric.

**Repair:** transplanted the FET from **Q4050**, the P2-flag LED driver — a cosmetic tap the CPU
does not use. Same part (BSS138K / C504052), same package, same rotation, same pin roles.
**No donor board was needed.**

**Cost: two dark LEDs.** **S0** (Q4024 was removed on a wrong call, see §7, and shed a pin) and
**P2** (Q4050 harvested).

**Provenance: a random fab defect**, on a net the rework never touched, matching the recorded
yield estimate of 0.5–2 per board across ~14,700 joints. It was present from the start; the
driver contention and the address-bus faults were simply louder.

---

## 3. The self-test — `tools/quick_selftest.py`

23 subtests, 266 bytes, ~286 CPU cycles.

**The verdict is the ADDRESS the CPU settles at**, which is the one thing a 32-cycle trace window
can always show — the wifi panel cannot read memory back:

| address | meaning |
|---|---|
| `$0480` | all 23 passed |
| `$0400 + 3*(N-1)` | subtest N failed; the tool prints its name |
| `$0600` | `int_trap` — BRK or a spurious interrupt |

```
python3 tools/quick_selftest.py --host discrete6502.local     # runs it, ~6 HTTP calls
python3 tools/quick_selftest.py --hex                         # just print the Intel hex
```

**It was validated before it was trusted.** The same image runs on the reference visual6502
netlist under `switchsim` and passes all 23 there. **That caught two bugs in the test program
itself** — the interrupt trap was being written into the middle of the code, and the `abs,X`
subtest wrote on top of the fail-loop table. Either would have looked like a hardware fault.
**Re-validate the same way after any edit to it.**

**One number to fix in `pico-controller/selftest/main.c`:** `RUN_CYCLES` is **300**, and the
program first reaches the pass loop at **cycle 286** (measured on the reference netlist). 14
cycles of margin, ~4 iterations of the 3-cycle JMP loop for the trace to settle on. **Raise it to
400.** Also, the comment above it is stale in a way that changes its meaning: it says *"300 cycles
at 20 kHz is 15 ms"* and *"a PASS here is conclusive"* because 20 kHz is the ceiling. With the
asymmetric 40/400 µs phases the real rate is **2.27 kHz** and 300 cycles is **132 ms**. The
speed-margin claim was true of an earlier symmetric version and is not true now.

---

## 4. What is fixed on board #1, and what is not

| | state | evidence |
|---|---|---|
| Stack pointer | **works** | `PHA` x3 lands `$01FF $01FE $01FD`; `PHA $AA` / `PLA` returns `$AA` with S restored |
| `cclk`-to-VCC short | **cleared** | 32 Ω → 9 kΩ, matching `cp1`'s 9 kΩ. It was the smoke, and an IPA wash removed it — so it was surface contamination, not silicon |
| Freezing at `$3FFF` | **gone** | six 45-second trials, no freeze. Before the wash: 20.1 s → 4.1 s → 0.5 s as it warmed |
| All 14 address bits | **toggle** | full `$0000`–`$3FFF` sweep, ab0–ab13 all near 50% |
| 23 datapath subtests | **PASS** | settled at `$0480` |
| `adh0-7`, `adl0-7` rework | **done** | current 0.5 A clocked against a 0.548 A passive floor |
| **`idb0-7`, `sb0-7` rework** | **NOT done** | §5 — this is the standing hardware fault |
| Bench supply | **the blocker** | see `docs/session-2026-08-30.md` |

Address-bus faults fixed along the way, for the record: **ab7** (`adl7`/Q3841) after that site's
rework was redone; **ab6** (`adl6`/Q2458) whose resistor came adrift during the wash and was
resoldered; **ab2** by reflowing the Pico's GP10 joint.

---

## 5. The sixteen un-reworked precharge sites — the real remaining fix

`cclk` gates **32** VCC-side precharge FETs. Sixteen have the 10 kΩ series rework; sixteen do not:

```
adh0-7  adl0-7   reworked   ~0.5 mA each
idb0-7  sb0-7    NOT        up to 262 mA each
```

Every time the clock goes high, all 32 conduct. The unreworked sixteen can draw **amps in 40 µs
bursts**, which is what a supply cannot follow. `docs/clk0-pulldown.md` §5 names this as the
standing fault, and it is consistent with the contention measurements (`sb0`: 15.8 % duty under
real code, 24.2 % under NOP).

**Mapped two ways:**
- `docs/precharge-rework-idb-sb.jpg` — generator `tools/mark_precharge_rework.py`
- navigator groups **`precharge-idb`** and **`precharge-sb`**, verified 2026-08-30 to resolve to
  exactly the same sixteen parts by an independent derivation. Deployed to
  https://ai.memention.net/d6502navigator/

```
sb0  Q1804  71.35,191.80    idb0 Q270  211.95,191.80
sb1  Q1995  75.05,205.80    idb1 Q3813 215.65,203.00
sb2  Q3991  41.75,214.20    idb2 Q2020 211.95,214.20
sb3  Q1269  75.05,228.20    idb3 Q1095 208.25,231.00
sb4  Q48    75.05,239.40    idb4 Q3994 211.95,239.40
sb5  Q3826  41.75,233.80    idb5 Q2606 211.95,250.60
sb6  Q495   75.05,264.60    idb6 Q2986 211.95,261.80
sb7  Q1764  71.35,278.60    idb7 Q1830 208.25,278.60
```

**THE HAZARD, and it is what smoked board #1:** on every one of these sixteen, **pin 1 is `cclk`
itself, 1.89 mm from the pin 3 being lifted**. A bridge shorts the CPU's clock to VCC — the
machine stops, the site burns, and `cclk`-to-VCC reads ~32 Ω where healthy is kilohms. **Measure
`cclk` to VCC after each site** (Q3659 or Q1038 pin 1 to TP36; `docs/probe-cclk-cp1.jpg`). The
original rework instructions say pin 3 is safe to lift because its neighbours are 1.78 mm away —
true mechanically, but it misses what pin 1 *is* on these parts.

**And lie the resistor flat, anchoring both ends.** Q2458's stood on a lifted pin and came adrift.

---

## 6. Where my data bears on the other agent's unresolved contradiction

`docs/session-2026-08-30.md` §3 records: **undriven, `clk0` sits at 0.77 V and the board draws
0.24 A; driving that same pin to ground kills the module in 1 ms**, and no explanation survived.

Two things from this thread that bear on it:

**(a) Current does scale with clock duty, which supports the `clk0`-high-is-expensive model.**
`wifi` clocks **50 µs symmetric — 50 % duty**; `selftest` clocks **40/400 µs — 9 % duty**. Flashed
back-to-back on the same board today: `selftest` survived long enough to print
`"link up, running 23 subtests now"` before dying; **`wifi` did not survive to enumerate at all.**
Five times the average current, dies sooner. That is consistent with the two-inversion trace in
`docs/clk0-pulldown.md` §1, which I verified independently from `gen/netlist.json`:
`clk0` high → `cclk` high → **all 32 precharge FETs on**.

**(b) A hypothesis worth testing, because it would dissolve the contradiction.** The observation
is stated as *"driving clk0 low kills it"*, but what actually happened is *`bus_init()` ran*.
`bus_init` does not only park `clk0` — it configures the data bus and drives it. **The proposed
experiment in their §4 — clip TP25 by hand with the `usbonly` build, which touches no pin — is
exactly the right way to separate those**, and it is the highest-value thing on either list.
If a hand clip to VSS draws 0.24 A while `bus_init` kills it, the culprit is something else
`bus_init` does, not `clk0`'s level.

**One addition to `docs/clk0-pulldown.md` §1** if it is revised: `n1129` has a **second**
pull-down, **`Q2944`, gated by `cp1`**. This does not weaken the pull-down proposal — it
strengthens it. The LOW branch is *actively driven* by `Q3504`, whereas the HIGH branch depends on
`Q432` conducting **and** `Q2944` not. The pull-down puts the board in the deterministic branch.
The rest of §1 I verified node by node and it is correct.

---

## 7. Method lessons — these cost the most time

**An in-circuit two-point reading measures the part AND everything around it.** On a net that is
already faulty, *every* part sitting on it reads wrong. I named three culprits from single
in-circuit readings and all three were wrong:

| called | why it was wrong |
|---|---|
| `alub0` / Q1313-Q1314 | DEX decrements correctly, so the ALU operand was fine |
| `sb0` / Q1804 | DEX again — bit 0 does pass a zero over the SB bus |
| **Q4024** (S0 LED driver) | read 70 kΩ gate-drain against a healthy OL **and was removed on that basis**. Its gate *is* `s0`, so the meter was seeing the Q2577 fault straight through it. Removing it changed nothing and cost the part |

**What worked:** compare each suspect against its **matched twin on an adjacent bit**, and trust
only the part whose low reading **cannot be explained by the fault itself**. Q2577 was the only
one whose pin 3 (`n983`) is independent of `s0`.

**On an intermittent board, no single run is evidence.** Between 2026-08-26 and 2026-08-28 the
same board showed S decrementing by 2, by 0, and correctly by 1. The diagnosis only became stable
once the address bus held steady across a power cycle and every test carried a **negative
control** — e.g. `LDX #$3C ; STX $0300` (never touches S) returning `$3C` while
`LDX #$3C ; TXS ; TSX ; STX` returned `$3D`.

**Validate a test program before trusting its verdict.** Running the self-test on the reference
netlist caught two bugs in it that would have read as hardware faults.

**Two operational rules, both learned by breaking something:**
- **Never write Pico flash while the CPU is running.** `op=autorun`/`clocksave`/`store` stall the
  core including lwIP. Issuing one mid-run wedged the web server during the write, and the
  settings record — which holds the wifi credentials — had to be erased and reprovisioned.
- **Never poll a long run over wifi.** The lwIP stack wedges under repeated short-lived requests —
  observed at **one poll per minute**. The CPU is unaffected (core 1) and keeps executing; only
  the observation channel dies, which is why the verdict is printed to USB serial. Start long
  runs and read the banner at the end.

**`discrete6502.local` resolves over mDNS** — never hunt for the IP after a power cycle.

---

## 8. Tools written in this thread

| tool | what it does |
|---|---|
| `tools/quick_selftest.py` | the 23-subtest image; `--hex` prints it, otherwise runs it over the panel |
| `tools/board_probe.py` | stack tests (`push`, `push1`, `sxfer`, `dex`), `--sweep` across clock rates, and `hold-push`/`hold-dex`/`hold-idle` loops for thermal work |
| `tools/mark_precharge_rework.py` | the idb/sb map |
| `tools/mark_stack_sites.py`, `mark_probe_points.py`, `mark_s0_probe.py`, `mark_q2577_swap.py` | probe maps, all derived from the fabricated board |

Committed as `12bebec`. `docs/s0-led-driver-check.jpg` was **deleted** rather than kept — it named
Q4024 as the culprit, and a map that accuses an innocent part is worse than no map.

---

## 9. Next steps, in order

1. **Settle the `clk0` contradiction with clips** — `docs/session-2026-08-30.md` §4. Needs no
   Pico, no firmware, no risk, and it gates everything else.
2. **~500 µF low-ESR across TP36/TP35.** The peaks are ~80 µC; 10 µF gives 8 V of droop, ~270 µF
   gives 0.3 V. The 400 µs low phase recharges it ten times over.
3. **The sixteen `idb`/`sb` precharge sites** (§5). This removes the peaks rather than absorbing
   them, and afterwards the supply stops mattering.
4. **`python3 tools/quick_selftest.py`** — seconds, and it should still pass.
5. **The decimal test** — `46,089,513` cycles, **77 minutes at 10 kHz** (not the 2h33m the
   firmware reports; that figure assumes 5 kHz). Start it, do **not** poll it, read
   `VERDICT :` from the USB serial banner.
6. **Then Klaus Dormann's functional suite**, which remains the acceptance gate.

**One decision worth taking early:** board #1 has had three reflows at one site, hot air, a sink
wash, a smoked component, a torn pad and two transplants. There are **three untouched assembled
boards** and one bare. Screening a spare needs no Pico — Step 1 (VCC-VSS resistance, range-
dependent diode reading, which also confirms ~1,000 back-side pull-ups are populated) and Step 2
(current at 5 V, ramped) catch anything gross. A second working board would end the "is it the
board or the bench?" question that has cost several days.
