# Project Plan — discrete6502

## Goal

Recreate the MOnSter 6502 — a working, discrete-transistor replica of the MOS 6502 CPU — as a smaller PCB, designed around JLCPCB's fabrication and assembly capabilities so it can be manufactured and assembled with as little hand-soldering as possible.

## Non-goals

- Not a faster 6502: like the original MOnSter 6502, clock speed will be far below a real 6502 (~tens of kHz is acceptable).
- Not an FPGA/emulated 6502 — the point is real discrete transistors.
- Not (yet) a full computer around the CPU; the CPU board itself is the deliverable.

## Milestones

- [x] **M1 Research** — Understand the original MOnSter 6502 design and the visual6502 netlist; identify what data is reusable (netlist, transistor count, dynamic-logic structures). Status: **done 2026-07-18** — netlist downloaded to `data/visual6502/` and analyzed; findings in `cards/visual6502-netlist.md` and `cards/monster6502-lessons.md`
- [x] **M2 Feasibility & key decisions** — Choose logic implementation (faithful NMOS dynamic logic vs. adapted static logic), transistor/package selection from JLCPCB parts library, target board size. Status: **done 2026-07-18** — dynamic NMOS + pass-FET pairs validated in SPICE (`sim/passpair_latch.sp`); decisions in `cards/pass-pair-validation.md`
- [x] **M3 Toolchain** — Pick EDA tool (e.g., KiCad) and a netlist-to-schematic generation path (thousands of transistors ⇒ must be scripted, not hand-drawn). Status: **done 2026-07-18** — KiCad chosen; `tools/gen_netlist.py` generates `gen/netlist.json` + KiCad netlist; see `cards/netlist-pipeline.md`
- [x] **M4 Schematic & verification** — Generate full schematic/netlist; simulate or logically verify against visual6502 behavior. Status: **done 2026-07-18** — switch-level equivalence proven (`tools/switchsim.py`); analog behavior re-validated with onsemi vendor model (`sim/passpair_vendor.sp`); see `cards/verification.md`
- [x] **M5 Layout** — Place & route within JLCPCB constraints; DRC clean. Status: **routing done 2026-07-25** — 6-layer board, all 8,421 signal connections + 100% power stitching routed, **0 electrical DRC violations, 0 unconnected**, parity + independent connectivity green (`gen/board_routed_golden.kicad_pcb`). **Fab package generated 2026-07-25**: `gen/fab/` (gerbers zip, BOM 9 line items / 5,328 SMD placements, CPL, order README). FET resolved to 2N7002W-7-F LCSC C139444 (stock must be sourced at order — ~20k pcs needed; alt C5334591). Remaining: upload + real quote + order (M6)
- [ ] **M6 Fab & bring-up** — Order assembled boards, power-up, run test programs. Owner: — Status: **ORDER PLACED AND PAID 2026-07-28** (5 PCBs, 4 of them assembled; est. ship 2026-08-06). Order/job numbers are deliberately untracked — `gen/fab/ORDER.local.md`, gitignored. **Both confirmation gates passed and the full order was released to production 2026-07-30** — PCB stackup verified by measurement, SMT placement verified on the DFM image (sections below). Fab package rev A (`gen/fab/RELEASE.md`) is what was uploaded. Bring-up acceptance target: pass **Klaus Dormann's 6502 functional test suite** (see Decisions 2026-07-26); firmware support is in place. Yield expectation recorded before the boards arrive: see "Expected fab yield" below — plan for **0.5–2 defects per board** and treat a perfect first power-up as a coin flip.

## Decisions

_(append-only; timestamp and mark locked decisions)_

- 2026-07-18 **[locked, user directive]** monster6502.com is inspiration only — do not copy it; improve and simplify where possible while keeping the overall concept (a real discrete-transistor 6502).
- 2026-07-18 Proposed (confirm in M2): drop LEDs/display circuitry; replace 4-terminal MOSFET arrays with back-to-back 3-terminal FET pairs for the 783 pass transistors; merge the 271 redundant parallel netlist transistors; single jellybean FET part in JLCPCB economic class.
- 2026-07-18 **[M2, settled]** Logic style: faithful dynamic NMOS from the visual6502 netlist (not static conversion). Pass gates: back-to-back 3-terminal FET pairs — SPICE-validated (`cards/pass-pair-validation.md`). LEDs: dropped.
- 2026-07-18 **[M2, settled]** Parts: 2N7002 (JLCPCB C8545, basic, SOT-23) for all FETs, 10k 0402 pull-ups, 5 V supply, ≥50 kHz target. Fallback FET: BSS138 (C52895). SOT-323 variant is the board-shrink lever.
- 2026-07-18 **[M2, settled]** Board target: ≤200×250 mm, 4 layers, double-sided assembly (~half the MOnSter footprint).
- 2026-07-18 **[user directive]** The board must visually resemble the original 6502 die, like the MOnSter does: die floorplan orientation (decode PLA top, datapath bottom) and bond-pad-style signal pads around the board edge. Implemented: die-position placement + 36-pad silk-labeled edge ring at die bond-pad projections.
- 2026-07-19 **[user directives, layout iteration]** (a) ALL components on top face except passives (front = pure transistor texture; R/C on back); (b) do NOT pack transistors — preserve the die's density/empty space (board grew to ~30cm class to allow it); (c) bond pads die-true in position AND size (11.6mm), croc-clip usable from the back; (d) interface = unpopulated Raspberry Pi **Pico 2 W** site on the underside (SMD variant, aftermarket hand-solder), not a header; (e) iterate layout visually until approved — approved 2026-07-19 ("Good. Lets continue").
- 2026-07-19 **[M5, settled]** FET package switched to SOT-323 (2N7002W, extended part, LCSC to verify) — enabler for the single-face die-texture layout.
- 2026-07-18 **[M5, settled]** Core FETs checkerboarded across both faces (a fully-packed single face has no routing channels — pads overlap in x). Per-cell via-site scheme for all power stitching; decouplers in edge columns; DRC clean.
- 2026-07-18 **[user directive]** LEDs: *some*, not none — on registers and counters (A, X, Y, S, P flags, PCL, PCH ≈ 55 LEDs), each buffered by a single 2N7002 gate-tap driver (3 parts/LED, ~165 parts total). Supersedes the earlier "drop all LEDs" proposal. Optional later additions (script-generated): address/data bus (24), IR (8).

- 2026-07-27 **[correction]** The core FET is **BSS138W**, not "BSS138K" — the earlier entries in this log used a name the part does not have. Verified on LCSC: `C504052` is **JSCJ BSS138W, SOT-323**, 50 V, 220 mA, **Ciss 27 pF**, Vgs(th) 1.5 V, RDS(on) 6 Ω @ 4.5 V, Crss 6 pF. **No engineering consequence** — the LCSC code was always correct, and every figure the sims rely on matches: 27 pF is what `sim/fanout_speed.sp` and `tools/dynamic_nodes.py` assume, and the 3.3 V pass-pair and LED decks already simulate the Vth = 1.5 V worst case. The prose docs and sim comments are corrected; the append-only entries below are left as written. **`tools/gen_netlist.py` still emits the string "BSS138K"** on purpose: it becomes the BOM's Comment field, and changing it would alter `gen/fab/discrete6502_bom.csv`, whose sha256 is pinned in `RELEASE.md` and already uploaded. JLC matches on the LCSC code, so the comment is cosmetic. Also noted at the same check: LCSC stock is **20,740 against 16,234 needed** for 4 assembled boards — adequate but not roomy.

- 2026-08-08 **[M6, settled]** The acceptance suite is **built by script, not by hand**:
  `tools/build_functest.py` against a sibling checkout of Klaus Dormann's repo, emitting
  `gen/functest/<test>.hex` (ready for the tester's `L`) plus `<test>_traps.csv` (the verdict map).
  It sets `ram_top = $40`, folds 64 KB to 16 KB the way the hardware does — failing on a genuine
  aliasing collision rather than letting last-writer-win — patches the reset vector so
  `m 3FFC 00 04` is no longer a manual step, and extracts every self-loop with its source line.
  **Validated two ways before hardware exists:** with stock config the toolchain reproduces
  upstream's committed `bin_files/6502_functional_test.bin` byte for byte, and both generated images
  were then *executed* in an emulator against a mirrored 16 KB memory and **both reach PASS** —
  decimal at `$024F` in **46,089,513 cycles**, functional at `$34D8` in **96,779,996 cycles** with
  `test_case` = `$F0`. Four facts this produced that were previously assumed: (a) **`report = 1` does
  not fit** — the readable-error channel pushes the image to `$466B`, past the `$3FFA` ceiling, which
  is *why* the bus side channels are the only option and not merely a preference; (b) the run is an
  **afternoon, not overnight** — 2 h 41 m at 10 kHz, 1 h 21 m at 20 kHz (the 2026-07-26 entry's
  "overnight" was conservative, though its 10⁷–10⁸ order was right); (c) **`test_case` runs 0..43 then
  `$F0`**, 45 checkpoints, not a smooth count; (d) the decimal test needed real fixing, not just
  configuring — its `end_of_test` emits `db $db`, a 65C02 STP that is an **undefined opcode on NMOS**,
  so it is replaced by two distinct self-loops branching on `ERROR`, and it emits **no interrupt
  vectors** at all, so an `int_trap` and a vector block were added.

- 2026-08-12 **[M6, hardware finding]** **The Step 1 gate was wrong: there is no resistive path
  between VCC and VSS, so the meter reads a junction and the number depends on the range.** Measured
  ≈195 Ω (200 Ω range, red on VSS) on all four boards; the same board reads 314 Ω on 2k and 3.77 kΩ
  on 20k, while the voltage across it stays at 0.36–0.47 V — one diode drop. The path is **1,899 FET
  body diodes across 947 nets**, each conducting VSS → drain and out through that net's 10 kΩ
  pull-up. Consequences: (a) *"must read high"* is replaced by a polarity- and range-aware gate —
  a fault is <1 Ω, or a value that does **not** change with range; (b) **Step 1 is a positive test**,
  since the forward path cannot exist without the pull-ups, so it confirms ~1,000 back-side 0402s
  are populated; (c) reverse conduction exists and is exponential (**55.4 mV/decade vs 59.5 ideal**,
  ~95 µA at 0.8 V), not a leak. Derived by `tools/step1_model.py`; logged in
  `docs/actual-bring-up.html`. A prediction made before measuring (3601 Ω at 0.1 mA) matched the
  20k-range reading within 5%.

- 2026-08-16 **[M6, correction + firmware]** **A spurious IRQ would produce a wrong verdict, not a
  stopped run — the 2026-08-08 entry below is half wrong.** That entry says a floating interrupt is
  survivable because "the functional test traps them at `$380B` (NMI) and `$3819` (IRQ), neither of
  which is a test trap". The vectors are right; the conclusion is not. Checked against upstream's
  source rather than inferred: **`nmi_trap` uses the suite's `trap` macro**, so `$380B` really is a
  `jmp *` and a spurious NMI stops visibly (though its listing text, `jmp * ;failed anyway`, is
  identical to every failure trap — only the address separates them). **`irq_trap` at `$3819` is not
  a trap at all**: it is the BRK-test handler, live code beginning `php / dey / dey / dey`. A
  spurious IRQ is therefore *absorbed*, corrupts Y and SP, and surfaces later as a failure at an
  unrelated address. So tying `irq` high before a long run is what separates a trustworthy result
  from a plausible-looking lie, and is no longer merely tidy. The decimal test is safe either way —
  our added `int_trap` gives both vectors a distinct self-loop. **The firmware now warns at load
  time**, from the image's own vector block rather than from a hard-coded address.
  **Also settled: the test images can be compiled into the firmware, behind
  `-DEMBED_FUNCTEST=ON`, and are OFF by default for a licensing reason** [user decision] — the suite
  is GPLv3 and this repo is CC BY-NC-SA 4.0, which GPLv3 forbids combining with. Separate files in
  `gen/functest/` are mere aggregation; a binary with the images linked in is a combined work. So
  `tools/embed_functest.py` generates `common/functest_images.c` only on request, that file is
  gitignored, a default build links `functest_images_none.c`, and **no binary containing GPLv3
  material is ever produced by this repository**. With the flag on: `T f` / `T d` replace pasting
  37.6 kB of Intel hex by hand, and a self-loop is reported as PASS/FAIL with its listing line
  instead of as a bare address to look up in a CSV. Measured cost **+39 KB flash, 0 bytes RAM**
  (const data stays in XIP; bss unchanged at 32,400 confirms it). `gen/functest/README.md` now
  carries the attribution that was missing entirely.

- 2026-08-25 **[M6, MILESTONE]** **The discrete 6502 executes instructions — proved by finding the
  program counter in a video of the register LEDs.** Board #1, 2250 Hz external clock, data bus tied
  to $EA through 10k, `irq`/`nmi` clipped to VCC, supply rewired. On a NOP free-run the CPU only
  fetches and increments, so PC bit *b* must toggle at `(clock/2) / 2^(b+1)` Hz — a prediction that
  needs no LED to be identified, mapped or named. Measured: **92 LEDs on a predicted PC frequency,
  zero unexplained strong peaks**, matches within 0.15–1.8%. **The proof is four bits identified BY
  NAME**, each matching its own predicted rate and forming a measured factor-of-two ladder (PCL7
  4.407, PCH0 2.170, PCH2 0.542, PCH3 0.271 Hz; measured ratios 2.031, 4.000, 2.000). An earlier
  version of this entry credited *aliased* fast bits instead — **that was wrong and was falsified
  within hours** by naming the LEDs. Aliasing needs *point* sampling and a camera **integrates over
  its exposure**, so a 562 Hz LED averaged over even 1/500 s spans ~1.1 cycles and comes out a
  constant glow; PCL0–PCL5 cannot be recovered from video at all, and the apparent detections were
  drift artifacts (the board moves **76 px** through the clip, measured by phase correlation).
  **Lesson worth keeping: the anonymous test cannot fail in an interesting way** — it asks only
  whether a set of frequencies exists *somewhere* among many LEDs, and with enough LEDs and enough
  drift something always lands. Naming them makes it falsifiable, which is the whole point.
  **Two method errors are recorded because both gave confident false
  negatives on 2026-08-24:** (a) aggregating spectra across all 55 LEDs buries the 16 PC bits under
  the other 39 — count LEDs whose *own* dominant peak matches instead; (b) failing to detrend the
  record's own start/stop envelope, which put a spurious 0.55 Hz peak at 11.9× the noise floor.
  Underlying both, **only the direct low-frequency bits were ever searched for**, and those share a
  spectrum with every slow artifact. Tooling: `tools/pc_ripple.py`. **Scope of the claim:** this
  exercises instruction fetch, the decode PLA, the PC incrementer, the address drivers and on-board
  clock phase regeneration — it does **not** touch the ALU, A/X/Y, the stack, the flags, addressing
  modes or branches. Klaus Dormann's suite remains the acceptance gate. Two open items from earlier
  entries are closed as a side effect: the clock really is regenerated on-board at full swing, and the
  `irq`/`nmi` mitigation works (a spurious interrupt vectors PC to $EAEA and would destroy this exact
  ripple).

- 2026-08-24 **[M6, hardware finding — CORRECTS 2026-08-01]** **There are no contention hot spots on
  the board, and a thermal camera is what proved it.** The 2026-08-01 entry below predicts 3–4 nets
  contending at 262 mA and 0.90 W each, in SOT-323 packages rated ~0.3 W; the "Driver contention"
  section builds a 2.1 A / 10.4 W board budget on it. **Measured on board #1 with a FLIR One: peak
  ~30 °C against 25 °C ambient, and a broad diffuse warm region over the die — no localised spot
  anywhere.** A FET dissipating 0.9 W would run 50–150 °C above ambient even at a generous
  60–150 °C/W on this copper, and the heated copper around it spreads over several mm against a
  ~1.8 mm pixel, so it could not be missed. Concentrated and distributed dissipation differ by ~30×
  in peak temperature here, so the observation discriminates rather than merely failing to confirm.
  **Revised mechanism: the excess is spread across the array** — 0.85 A over 4,051 FETs is ~210 µA
  each, ordinary for a FET biased *near* threshold rather than fully on, which is what dynamic nodes
  sitting at undefined intermediate voltages produce whether unclocked or executing garbage. Three
  things this re-explains: the board's 1.4 A unclocked (against a 0.548 A passive ceiling); why
  clocking moved it to 0.7–1.2 A rather than to 0.35 A; and why the current climbs 1.15 → 1.33 A over
  three seconds and then **plateaus** — a few °C of warming, Vth falling ~2 mV/°C, ~16% more current,
  self-limiting rather than runaway. **What still stands from 2026-08-01:** the ratio error is real
  and its serious half was always the *level*, not the heat — a contended node at 1.0–1.9 V against a
  1.1–1.5 V receiver threshold is a correctness bug, and `sim/revb_driver.sp` still measures rev B
  fixing it. **What does not:** rev B is not a fix for the current draw, the 2.1 A / 10.4 W figure is
  not what the hardware does, and **no hand rework beyond the eight sites already done is warranted**.
  The switchsim duty-cycle table remains the best guide to *which* nets contend, but its assumption
  that each contended net draws the full 262 mA pair current does not survive the thermal image.

- 2026-08-24 **[M6, hardware finding]** **Charge retention measured at 1.9–2.3 nA per FET — the
  clock floor is closed in the design's favour.** The open question below recorded this as
  unresolvable by simulation (`sim/retention.sp` moves 3.5 orders with solver tolerances and gets
  temperature backwards), with the written fallback being the tester's `w`/`W` clock-stall scan. It
  was instead measured **with a phone camera and no Pico on the board**. The method is sound because
  of a netlist fact, not a guess: `a1`, `a2` and `p1` carry **no pull-up resistor, no VCC-side FET and
  no pull-down** — only pass gates and two gate loads — so nothing on the board is *capable* of
  turning their LEDs off, and leakage is the only available mechanism. Filmed at
  `com.android.capture.fps=120`, peak-to-dark is 7 frames = **58.3 ms**; with C = 64 pF and 2 channels
  that is **1.92 nA at Vth = 1.5 V, 2.30 nA at 0.8 V**, both *upper* bounds since the node is charged
  capacitively by the rising rail (so cannot start above 5 V) and the LED extinguishes slightly above
  Vth. **Corroboration that was not fitted:** `p1` has one leaking channel against `a1`/`a2`'s two, so
  it should hold ~2× longer — exactly the order seen by eye. Consequences at the pessimistic end:
  worst node `sb6` holds 1.13 ms, floor **871 Hz**, window to the 20 kHz ceiling **23×**, margin on
  the 53 nA budget **23×**, temperature headroom **45 °C**. This also re-set the recommended external
  clock from 1–2 kHz to **4–5 kHz** (geometric centre of the real window), and makes 3.3 V operation
  better-supported than the 2026-07-28 entry assumed — its 27 nA budget now has a measured 2 nA
  against it.

- 2026-08-24 **[M6, hardware finding]** **A floating data bus jams the CPU; tie it to $EA.** With
  `db0-7` floating the CPU fetches random opcodes and **12 of the 256 are undocumented KIL/JAM** —
  4.7% per fetch, so it halts within ~20 instructions. Signature on video: the lit-LED count decays
  monotonically and never recovers (7 → 0, 8 → 4), which means nothing is writing registers. Camera
  exposure drifts only 1–3% and the *remaining* LEDs stay equally bright, so neither the camera nor a
  sagging rail explains it. Tying the bus to **$EA (NOP) through 10 kΩ** — `db1/3/5/6/7` high,
  `db0/2/4` low, resistors never wires so the CPU wins if it drives — makes it free-run the address
  space, and the count then holds at 10–14 and jitters across three power cycles. **Also settled: the
  clock is regenerated on-board**, proven by contrast rather than asserted — the same nodes lose
  charge in 65 ms unclocked and hold for *seconds* clocked, which only the recirculating dynamic
  latches can do, and they need `cclk` (482 gates) and `cp1` (198 gates) at full swing. **Not yet
  settled: orderly sequencing.** PCH must ripple at 4.4/2.2/1.1/0.55 Hz on a NOP free-run; after
  detrending the run's own envelope (which faked a 0.55 Hz peak) **no counting signature is present**
  and nothing reproduces across three tries. The test is underpowered — all 55 LEDs summed so PCH is
  diluted, PCL aliases at 1125 Hz, handheld camera — so it is not evidence of absence. The proper test
  is Step 3c: 3.3 V, ~3 kHz, camera on the PCL/PCH columns only, looking for 2.9/1.5/0.73 Hz.

- 2026-08-13 **[rev A defect, cosmetic]** **4 of the 36 bond pads are in the wrong slot** — found by
  the user comparing the board against visual6502's JSSim die view ("A6 seems to be where A0 should
  be"). Correct comparison, because the two orientations agree: JSSim draws
  `screen_y = grChipSize − die_y` (`wires.js drawSeg`) and `gen_pcb.py:178` maps
  `board_y ∝ (maxy − die_y)`. **It is neither mislabelling nor misrouting** — checked against copper,
  all 36 pads sit on the net their silk names (the pad silked `A6` is on net `ab6`) and the DIP pin
  numbers are right too. Wrong: **A6, VSS, D7, R/W**, which puts A0–A5 one slot down from where the
  die says they should be, and makes the right edge read PIN 33, 32, 34. Two independent causes,
  both in `rim_slot` (`tools/gen_pcb.py:192-201`): (a) the address run projects to a **16.0 mm
  average pitch against the 19.7 mm** `spacing`, so the greedy first-come allocator (component
  order TP1…TP36, not die order) accumulates a push — A5 lands +20.5 mm low, then A6 needs ≥ 317.96
  against a 308.95 corner limit and the outward search **wraps to the first free gap above A0**,
  −116 mm; D7 fails identically at the bottom-right corner; (b) `R/W` (y 7.61) and `VSS` (x 11.20)
  project **inside the 13.05 mm corner exclusion** outright, and being late in component order land
  in whatever gap survives. Root cause is certain rather than inferred: a re-simulation of
  `rim_slot` reproduces **every one of the 36 placed pads to 0.01 mm**. Fix (respin only, documented
  with the algorithm in `cards/bond-pad-ring.md`): allocate per edge in **die-coordinate order**
  with a forward/backward bound sweep, which makes order preservation structural instead of an
  accident of iteration order — feasible on every edge without changing `spacing` (L needs 137.9 mm
  of 295.9, B 197.0 of 264.6, R 157.6 of 295.9). **Not applied**: it moves pad positions and so
  forces the whole pipeline from `gen_pcb.py` onward, and rev A is the fabricated board whose
  fingerprints are pinned in `gen/fab/RELEASE.md`. Also settled while looking: **`cclk` is not a
  pad and must not become one** — it is internal node 943, and the shape at the top-right die edge
  that looks like a pad in JSSim is 76,156 units against ~158k–243k for real pads.

- 2026-08-08 **[M6, hardware finding]** **`irq` and `nmi` float on the assembled board.** Neither
  carries a pull-up — only a 100R input-protect resistor and the two clamp diodes — whereas `rdy` and
  `so` do have 10k (`R48`, `R991`), and the Pico's 26 GPIOs drive neither. A floating gate on a
  dynamic input can drift across threshold and fire a spurious interrupt, which would end a
  multi-hour functional-test run for no reason. **Mitigation: croc-clip both bond pads to VCC**
  (directly or through 10k) before any long run. Consequence if one fires anyway is benign because it
  is *identifiable*: the functional test traps them at `$380B` (NMI) and `$3819` (IRQ), neither of
  which is a test trap. Found by checking `gen/netlist.json` while asking why the decimal test's
  unset `$FFFF` vectors mattered — which is also why that test now has vectors of its own.

- 2026-07-26 **[M6, settled]** The bring-up acceptance test is **Klaus Dormann's `6502_65C02_functional_tests`** (GPLv3, found via 6502.org's Tools → Emulators page) — the standard suite for 6502 *re-implementations* rather than emulators. Checked against our constraints before adopting: with its stock configuration (`zero_page = $0A`, `data_segment = $200`, `code_segment = $400`, 13.1 kB) the image ends ≈ `$3800`, so it fits the 16 KB mirrored window with the reset vector at `$3FFC` clear — **the ab14/ab15 sacrifice does not block it**, and the suite's own `ram_top` option offers `$40 = 16k` as a mirrored-system preset. It has no I/O, so `pico-controller/common/functest.c` reads its two side channels off the bus: writes to `test_case` ($0200) as live progress, and a repeated opcode-fetch address (branch-to-self) as the verdict — pass and fail are both self-loops, distinguished by the address in the assembly listing. Runtime is order 10⁷–10⁸ cycles ⇒ an overnight run at 10–20 kHz; run `6502_decimal_test.a65` first (decimal mode comes free from the netlist and is what emulators most often get wrong). One gotcha: the suite's own RES vector points at `res_trap`, so `$3FFC/D` must be patched to `$0400` after loading.

- 2026-07-25 **[user decision, at order]** Core FET switched to **BSS138K, LCSC C504052** (JSCJ, SOT-323) — 2N7002W (C139444) not in JLCPCB inventory. BSS138 was the designated fallback since M2 and is SPICE-validated; Vth 0.8–1.5V improves 3.3V-bring-up margins. Same package/pinout; netlist, generator, and BOM updated (datasheet reviewed: 27pF Ciss, 50V, standard G/S/D). BOM also re-chunked to ≤2000-char designator cells (JLC upload limit).
- 2026-07-25 **[user decision]** The 26 Pico GPIO series resistors (1k 0402, C11702 basic) are now POPULATED in the factory assembly (was DNP) — prepares every board for the aftermarket Pico with zero hand-soldering of passives; cost ≈ +$0.30/board. Only the Pico module itself remains aftermarket. Changed consistently in gen_netlist.py, netlist.json, and all three board files; parity re-verified.
- 2026-07-24 **[locked, user decision]** Board goes **6-layer**: F.Cu(sig-H) / In1(GND) / In2(sig-V) / In3(sig-H) / In4(VCC) / B.Cu(sig-V). Rationale: 2 signal layers bottom out at ~36 conflicted nets across two independent 24h negotiation runs (a genuine capacity floor at 0.127 rules); 6 layers resolves with certainty for ≈ +$40–70 per assembled CPU at qty 5 (accepted). Implementation: layer-surgery on the presignal snapshot (VCC zone In2→In4) preserving all placement/power work; router generalized to 4 routing layers.
- 2026-07-22 **[user intent confirmed]** The Pico 2 W site's purpose is to DRIVE the 6502: clock master + memory emulator (serve reads / capture writes each cycle). GPIO budget (26) forced dropping ab14/ab15 → the Pico sees memory mirrored every 16 KB (reset vector $FFFC appears as $3FFC — fine for all planned test programs). Kept instead: res (controlled reset) + sync (instruction-boundary tracing). Dynamic logic ⇒ no indefinite clock-stop; single-step = burst-to-sync + brief pause. Full-address remap (trade res/sync) is a one-line gen_netlist change if ever needed.

- 2026-07-25: **M5 COMPLETE — board fully routed, electrically DRC-clean.** Final pipeline (order matters): gen_netlist → gen_pcb → route_power → route_power_finish (on snapshot!) → [6-layer surgery: In2/In3 signal, VCC→In4] → route_nc (G=0.13, 4 routing layers, warm-startable hist) → fix_same_net_vias → fix_via_pairs → check_gaps + check_parity + DRC. Final finishing insights: (a) emission stubs must stay INSIDE own pad copper (goal cells shrunk 0.1) — pad-edge stubs grazed power vias (154 violations); (b) net-carve must never release non-pad copper cells (hard-mask filter) — over-carve let tracks hug stitch vias (351 violations); (c) last 8 via-via pairs = sub-cell alignment, fixed by exact-geometry nudges ≤1.3mm (`tools/fix_via_pairs.py`). Renders refreshed. Next: JLC fab outputs (gerbers/BOM/CPL), verify 2N7002W LCSC part + FET stock (~27k needed for 5 assembled), real quote (6L large-format), review 146 silk-on-pad labels (intentional) before order.

- 2026-07-25: **M6 prep started — Pico firmware scaffolded** in `pico-controller/` (`common/` shared bus engine — clock master, 16KB mirrored memory serving, trace ring, reset ceremony; `tester/` interactive bring-up CLI; `general/` free-runner with `$3F00` char-out port). Builds against pico-sdk 2.x (`PICO_BOARD=pico2_w`), untested until hardware exists. **Open question (resolve before power-up): 3.3V Pico vs 5V core levels** — inputs are practically safe through the 1k series resistors. **Verified: the board has NO pull-up on clk0** (only 100R protection + pico series R), so the clock must be driven push-pull; open-drain would leave clk0 floating unless an external 10k is croc-clipped Φ0→VCC. **Corrected 2026-07-25:** the earlier claim that a 3.3V clock under-drives the pass-pair bootstrap was wrong — clk0 gates only two pull-downs, and the internal phases (cclk/cp1) are regenerated on-board at full VCC swing; simulated, a 3.3V clk0 into a 5V core is functionally identical to a 5V one (1.7mV low, 17ns delay). The external pull-up is optional polish, not a requirement. Recommended first bring-up: whole CPU at VCC=3.3V (single domain, logic smoke test) — SPICE the pass-pair at 3.3V before boards arrive.


- 2026-08-28 **[M6, hardware finding + repair]** **A single transistor, Q2577, was pinning
  S bit 0 high and breaking every stack operation.** Gate-to-drain leak of 20 kohm against
  177 kohm on its matched twin; its drain net `n983` carries a 10 kohm pull-up, and `s0` has
  no pull-down, so S bit 0 could never fall. Repaired by transplanting the FET from Q4050, a
  P2-flag LED driver. **Not the driver-contention ratio bug** — `s0` has no pull-up and no
  VCC-side FET — but a random fab defect, the first one located on this board.
  **Method that worked, after three wrong calls:** an in-circuit two-point reading measures
  the part *and* its surroundings, so on a faulty net every part reads wrong. Compare each
  suspect against its matched twin on an adjacent bit, and trust only the one whose reading
  cannot be borrowed from the fault itself.

- 2026-08-28 **[M6, milestone]** **23 datapath subtests pass on board #1**
  (`tools/quick_selftest.py`): registers and all transfers, ALU with carry and borrow, shifts,
  stack in both directions with S tracking, flag save/restore, zero-page and absolute-indexed
  addressing, and JSR/RTS. **Validated on the reference visual6502 netlist first**, which
  caught two bugs in the test program that would otherwise have read as hardware faults.
  The verdict is encoded as the **address the CPU loops at**, so it survives the wifi panel's
  32-cycle trace window and needs no memory read-back. Klaus Dormann's suite remains the
  acceptance gate.

- 2026-08-28 **[operational, learned the hard way]** **Never write Pico flash while the CPU is
  running**, and never poll a long run over wifi. `op=autorun`/`clocksave`/`store` stall the
  core including lwIP; issuing one mid-run wedged the web server during the write and the
  settings record — which holds the wifi credentials — had to be erased and reprovisioned.
  Separately, the lwIP stack wedges under repeated short-lived HTTP requests, observed at one
  poll per minute. The CPU survives both on core 1; only the observation channel dies, which
  is why the verdict is printed to USB serial.

## Current state / handoff

**Newest first, and only the live entries.** Everything older was moved out on 2026-08-30, verbatim
and by date, because this file is `@`-imported into every session and history is not state:
[`cards/bring-up-log.md`](cards/bring-up-log.md) holds the boards-on-the-bench record
(2026-08-12 … 2026-08-26) and [`cards/build-log.md`](cards/build-log.md) the design, fab-package and
firmware work that preceded it (2026-07-18 … 2026-08-08). A cross-reference of the form "the
2026-08-24 entry" resolves by date in whichever of the three files covers that date.

- 2026-08-29: **The board cannot be clocked on the present bench supply — measured to the
  millisecond — and the self-test firmware that found this is the way to a verdict once the
  supply is fixed.** Nothing in the netlist, the board or the fab package changed.
  **The number: unclocked the Pico runs at least 16 s and prints 29 clean lines at 2 Hz;
  clocked it dies in under 15 ms, five times out of five, on a USB link that was already open
  and talking.** The last trace is unambiguous — the firmware prints `link up, running 23
  subtests now`, starts the clock, and the link drops inside the test. VSYS is board VCC (pin 39
  soldered), so the board's draw takes the Pico down with it. **What is needed is 5 V at >=3 A on
  a real connector**, fed to TP36/TP35 or soldered to pins 38/39 — not croc clips, not a USB
  charger. No firmware change can reach this: the current is clock-independent (2026-08-25, same
  at 500 Hz as at 10 kHz), so it cannot be slowed under the limit, and riding out even 15 ms at
  ~1.5 A would need order 0.1 F of bulk capacitance.
  **An hour of firmware theories was excluded by experiment, which is what the diagnostic build
  is for.** `-DUSB_ONLY=ON` builds the identical firmware with clocking removed; it enumerated in
  under a second and printed continuously, proving the Pico, the cable, the port and tinyusb are
  all healthy. Every `ENXIO / device not configured` of the evening was the module resetting.
  Also excluded: USB task starvation (polling `stdio_usb_connected()` every 100 cycles changed
  nothing), enumeration ordering (enumerating first, then clocking, still dies), and a bad UF2
  (family id and load address are byte-identical to the tester's).
  **The CPU itself is not implicated, and two independent observations say so.** Resting current
  is **0.27 A** against a 0.30 A measurement on 2026-08-26 and a 0.548 A passive ceiling — a
  degraded board reads high, not at the design figure. And a 17.7 s video at 18:31 shows the
  board executing continuously with LEDs live. [user observation] **S1 blinking at ~2 Hz with no
  serial device present is the boot loop made visible**: nothing clocks the board after the first
  60 ms, so a repeating blink can only be the Pico rebooting and re-running the test. **S0 dark is
  expected** — its driver FET is the one transplanted into Q2577 on 2026-08-28.
  **New: `pico-controller/selftest/`** (`tools/gen_selftest_image.py` embeds the image from
  `tools/quick_selftest.py`, so firmware, wifi panel and serial path share one definition and one
  verdict rule). It exists because the tester stops clocking the moment a terminal attaches, and a
  parked clock is the high-current state — measured twice, the port died ~1 s after attach, so the
  observer destroyed what it was observing. The shipped shape is: wait for the host, announce, run
  the test in one 15 ms window, park `clk0` LOW, then repeat the verdict twice a second for as long as
  the rail lasts. **Not yet run to a verdict on hardware.**

- 2026-08-30: **The board navigator is deployed — the map of the board is now a URL, not a
  localhost port.** Live at **https://ai.memention.net/d6502navigator/**, served by nginx on the
  `ai` VPS from a systemd unit, `navigator/deploy.sh` to redeploy. Nothing about the board, the
  netlist or the fab package changed; this is tooling. **Reads are public, writes are token-gated**
  — anyone can pan, search and click parts, but `POST`/`DELETE` return 401 without the token, which
  lives only in `/etc/d6502navigator.env` (root, 0600, handed to the service by systemd, never on a
  command line where `ps` would show it). `navctl.py` takes `--token`/`$NAV_TOKEN`, and the page
  itself becomes a controller with `?key=<token>`; without it an attempted annotation says
  *read-only* rather than failing silently. Serving under a prefix is a `--base` argument: the
  server strips it and injects it into the page as `<body data-base>`, which is where `app.js`
  gets the prefix for its fetches and its WebSocket — **local use is byte-for-byte the old
  behaviour** (verified: no `--base`, no token, writes open). The deployment ships `data/board.json`
  and the two renders as **prebuilt artifacts**, so the VPS needs python3 stdlib and nothing else
  — no KiCad, no PIL, no numpy; rebuild `board.json` with `build_data.py` after any placement
  change and redeploy. The page now carries the **visual6502 CC BY-NC-SA attribution** that a
  public deployment requires and that it had been missing. One trap recorded because it cost a
  round trip: on that host `/etc/nginx/sites-enabled/` holds **regular files, not symlinks**, so
  editing `sites-available` changes nothing while `nginx -t` still passes.

- 2026-08-29 (later): **The excess current has a named cause, and `clk0` must never be left
  floating — both settled by tracing the netlist rather than arguing.** [user, thermal camera]
  **Q1830 and the seven parts above it ran very hot with the adh/adl rework already done.** The
  navigator named it in one query: `vcc_side` FET, **gate `cclk`**, precharging `idb7` — and the
  column above it is `idb0`-`idb6`. **They are the same 1:1 ratio defect as the sixteen reworked
  sites, take the same fix (10k in series with pin 3), and were never in the rework set.**
  `sb0`-`sb7` are eight more in the same condition. So the rework is incomplete, not wrong:
  32 FETs are cclk-gated precharge devices, 16 are done, 16 are not.
  **Why that is the whole 2 A: the chain `clk0` -> Q2229/Q2420 -> `n519`/`n358` ->
  `n1129`/`n1467` -> Q432/Q3504 -> `cclk` means clk0 LOW parks cclk LOW and all 32 precharge
  FETs off; clk0 HIGH turns them all on at once.** Eight at the simulated 262 mA is 2.1 A, the
  order of the draw that folded a 2.4 A charger to **3.6 V at 2.5 A** and tripped a 3 A adapter
  outright. **This reconciles two figures the plan carried as contradictory** — "clock parked,
  0.30 A" (Pico fitted, `bus_init` drives clk0 low) against "clock parked, 2.2 A" (floating).
  Same words, opposite pin states, 7x apart.
  **Consequences, all implemented:** (a) the selftest firmware now **parks clk0 low** instead of
  floating it — floating was exactly backwards, and there is no pull-up or pull-down on that pin;
  (b) **`bus_set_phase_us(high, low)`** splits the clock phases, because contention flows only
  while the clock is high, so the average scales with duty cycle. Bounds are measured: high
  >= ~25 us to settle (`sim/fanout_speed.sp`), low <= ~500 us against the 1.13 ms retention floor.
  **40 us / 400 us is ~2.3 kHz at 9% duty, about a tenth of the contention current**, with peaks
  short enough that **~500 uF of bulk across VCC/VSS can supply them** (against the ~0.1 F a 60 ms
  clocked window would need). `bus_set_half_period_us` still sets both, so wifi and general are
  unchanged; the tester gains `p US [LOW]`.
  **[user suggestion, endorsed] a 10k (better 47k) from the CLK0 pad TP25 to VSS TP35** would hold
  the board in its quiet state whenever nothing drives the clock — BOOTSEL, reset, between
  firmwares — which is when every failure this evening happened. A pull-UP would be the worst
  possible choice: it parks cclk high and turns all 32 precharge FETs on permanently.
  **Unpowered meter check after the rework matches the 2026-08-12 baseline** (2k: 310 vs 314 ohm;
  20k: 3.6k vs 3.77k; both polarities conduct, range-dependent) — **nothing is shorted**, though
  that test probes at ~0.5 V and cannot see a fault that only conducts when powered.
  **[user] epoxy was applied to the rework sites today** as strain relief; epoxy is insulating and
  the risk is mechanical — a lifted pin 3 pressed back onto its pad shorts out the series resistor
  and reverts that site. **Audit the sixteen with the FLIR: they should now be cold.**
  **Not yet run to a verdict on hardware.** Next: the pull-down, the asymmetric-clock build, and
  the 16 remaining precharge sites.

- 2026-08-28: **THE CPU COMPUTES — 23 datapath subtests pass — and the stack fault that
  produced `FAILED at $02F3` was a single leaking transistor, found and replaced.**
  `tools/quick_selftest.py` covers TXS/TSX, TAX/TXA/TAY/TYA, INX/DEX/INY/DEY with wrap,
  ADC/SBC/AND/ORA/EOR, ASL/LSR, PHA/PLA, S decrementing twice and restoring, PHP/PLP,
  zero page, absolute-indexed, JSR/RTS and both Z-flag directions. **All 23 pass on board #1.**
  That is far past the 2026-08-25 NOP free-run, which only exercised fetch, decode and the PC.
  **Root cause of the stack failure: Q2577** (pull-down, gate `s0`, drain `n983`, x 75.05
  y 183.40) had a **20 kohm gate-to-drain leak against 177 kohm on its matched twin Q3793**.
  `n983` carries a 10 kohm pull-up (R585), and `s0` is a pure dynamic node with no pull-down
  of its own, so the leak pinned S bit 0 high: `PHA` could not decrement S, `RTS` pulled flag
  bytes instead of a return address, the PC landed in the zero-filled void, `$00` = BRK, and
  the run ended at `int_trap`. Repaired by **transplanting the FET from Q4050** (the P2 flag
  LED driver, a cosmetic tap the CPU does not use) — **no donor board needed**. Cost: the S0
  and P2 LEDs are dark. **This was a random fab defect on a net the rework never touched**,
  exactly the class the yield estimate predicted (0.5–2 per board across ~14,700 joints);
  the contention and address-bus faults were simply louder.
  **Three wrong calls on the way, all the same mistake**, and worth recording because it cost
  hours: `alub0`/Q1313, then `sb0`/Q1804, then Q4024. Each was named from **a single
  in-circuit two-point reading**, which measures the part *and* everything around it — so on
  a net that is already faulty, every part sitting on it reads wrong. Q4024 measured 70 kohm
  gate-drain against a healthy OL and was removed on that basis; its gate *is* `s0`, so the
  meter was seeing the Q2577 fault straight through it. It shed a pin on removal and was not
  reused. **What finally worked: measure each suspect against its matched twin on bit 1, and
  trust only the part whose low reading cannot be explained by the fault itself** — Q2577 was
  the only one whose pin 3 (`n983`) is independent of `s0`.
  **The test program was validated before it was trusted**: the same image runs on the
  reference visual6502 netlist under `switchsim` and passes all 23 there, which caught two
  bugs in the test program itself (the interrupt trap was being written into the middle of the
  code; the `abs,X` subtest wrote on top of the fail-loop table). Either would have looked like
  a hardware fault. Its verdict is the **address it loops at** — `$0480` pass, `$0400+3(N-1)`
  names the failing subtest, `$0600` int_trap — because that is the one thing the wifi panel's
  32-cycle window can always show, and the panel cannot read memory back.
  **The `cclk` short is gone, and it was the smoke.** `cclk` measured **32 ohm to VCC** against
  `cp1`'s 540 ohm — a short that stopped the internal clock phases, froze the address bus at
  `$3FFF` with no SYNC, and made time-to-hang collapse 20.1 s → 4.1 s → 0.5 s as the board
  warmed. An IPA wash and water rinse cleared it: `cclk` and `cp1` now read **9 kohm each**.
  **Six 45-second trials afterwards, no freeze.** Since a wash removes surface contamination and
  not silicon, it was a bridge or conductive residue, not damage.
  **Address bus: all 14 bits toggle.** ab7 (`adl7`/Q3841) came good after the rework at that
  site was redone; ab6 (`adl6`/Q2458) lost its resistor during the wash and was resoldered;
  ab2 was fixed by reflowing the Pico GP10 joint. **Current 0.5 A clocked against a 0.548 A
  passive floor**, so the 16-site rework is doing its job. FLIR peak 40 C, no localised spot.
  **The one thing still blocking the acceptance run is bench power, not the board.** The Pico
  loses power every 25–45 s: the cycle counter resets to zero, USB disappears entirely, mDNS
  drops. **VSYS is tied to board VCC (pin 39 soldered), so USB cannot rescue it** — a port
  asked to carry 0.5–2.2 A current-limits and takes VSYS down with the board. A 10 uF at pins
  38/39 did not help, which fits: 10 uF holds a rail for microseconds, not for a dropout long
  enough to reset the chip. The firmware is not responsible — `watchdog_disable()` runs first
  in `main()` and the only deliberate reboot path fires once after saving credentials.
  **The distinguishing measurement, not yet taken: does supply current spike just before each
  dropout (a board fault) or does the voltage sag on its own (bench wiring)?**
  **Note the startup trap**: with the clock parked the board draws **2.2 A**, and that is the
  state at power-up before autorun starts clocking. A USB-C source without CC resistors
  supplies only 500–900 mA, which explains both "stuck from start" and "runs a few seconds".
  **Wanted: a 5 V supply rated >=3 A on a real connector, not USB.**
  **The decimal test reached 2.1% (965,606 cycles) at 9,811 Hz before the network dropped.**
  Corrected estimate: **77 minutes at 10 kHz**, not the 2h33m the firmware reports — that
  figure assumes a 5 kHz clock. **Do not monitor it over wifi**: the lwIP stack wedges under
  repeated short-lived requests, observed even at **one poll per minute**. The CPU is
  unaffected — it runs on core 1 and kept executing while the web server was dead — so start
  the run, leave it, and read `VERDICT :` from the **USB serial banner**, which is in the
  firmware for exactly this reason.
  **New tools:** `tools/quick_selftest.py` (the 23-test image, `--hex` to print it),
  `tools/board_probe.py` (push/push-even/push1/sxfer/dex, `hold-push`/`hold-dex`/`hold-idle`
  loops for thermal work, `--sweep` across clock rates), and four derived probe maps —
  `tools/mark_stack_sites.py`, `mark_probe_points.py`, `mark_s0_probe.py`,
  `mark_q2577_swap.py`. Full record in **`docs/stack-decrement-defect.md`** (742 lines).
  **Pico firmware:** flash erased and `wifi.uf2` reflashed; settings back to defaults
  (autorun on, 50 us half-period). **`discrete6502.local` resolves over mDNS**, so the IP
  never needs hunting after a power cycle.
  **Nothing in the fab package or the netlist changed.**

## Where the rest of it lives

Moved out of this file on 2026-08-30 — nothing was edited, only relocated, and each card carries a
trigger in `CLAUDE.md` so it loads when it is relevant instead of always:

| Card | What it holds | Read it when |
|---|---|---|
| [`cards/bring-up-log.md`](cards/bring-up-log.md) | Handoff entries 2026-08-12 … 2026-08-26 | you need what a measurement on board #1 actually showed, or why a conclusion was retracted |
| [`cards/build-log.md`](cards/build-log.md) | Handoff entries 2026-07-18 … 2026-08-08 | you need why a tool, gate or pipeline step exists, before changing `tools/` |
| [`cards/fab-order.md`](cards/fab-order.md) | Both cost tables, the stackup and DFM verifications, the yield estimate | costing a respin, or judging a defect against what the yield model predicted |
| [`cards/driver-contention.md`](cards/driver-contention.md) | The ratio bug and both its retractions | current draw, a hot site, rev B, or a series-resistor rework is in question |

**Landed cost, since it is the one number worth keeping here:** ≈ €973 for 5 PCBs (4 assembled),
≈ €243 per assembled CPU, paid 2026-07-28. **Yield expectation:** 0.5–2 defects per board; expect
2 of 4 working at first power-up, 3–4 after rework.

## Open questions

_(design questions from M1–M4 are settled and live in Decisions; only live items remain here)_

- **Achievable clock**: simulation says ~20 kHz at 5 V / ~10 kHz at 3.3 V (PLA-line fanout,
  `sim/fanout_speed.sp`), against the M2 target of >=50 kHz. Measure the real ceiling at
  bring-up by walking the clock up with the tester's `p` command. For scale, the original
  NMOS 6502's own window was **50 kHz to 1 MHz** (datasheet-verified 2026-07-28, three-way
  comparison in `cards/monster6502-lessons.md`) — a discrete rebuild of this logic style runs
  entirely below the band the real chip was specified for, and the MOnSter's ~50 kHz ceiling
  sits on the original's *minimum*.
- ~~**Clock floor / charge retention**~~ **RESOLVED 2026-08-24 by measurement on board #1 —
  leakage is 1.9–2.3 nA per FET, giving a floor of 456–871 Hz and a 23–44× operating window** (see
  the Decisions entry of that date). Measured from the decay of two accumulator LEDs on nets that
  have no path to either rail, filmed at 120 fps — not from the `w`/`W` clock-stall scan, which is
  still unrun. **The damage worry is also retired**: FLIR imaging found no hot spot anywhere on the
  board (peak ~30 °C), so the shoot-through concern below, while topologically real, does not produce
  concentrated dissipation in practice. The stall commands are therefore safe to run when wanted.
  Original text kept below for the reasoning.
  The worst dynamic node (`sb1..sb7`,
  32 pF against 12 leaking FET channels) must leak **< 53 nA per FET at 5 V** or the floor
  rises above the 20 kHz ceiling and nothing runs. Typical parts are ~1 nA, so ~50x margin is
  expected — but SPICE cannot resolve leakage at this level (see `cards/pass-pair-validation.md`)
  so it is unproven. **Measure at bring-up** — the tester firmware now does it: `w MS` for a
  single stall, `W [MAXMS]` to bisect the boundary automatically (runs a 0 ms control first,
  so a broken harness cannot masquerade as a retention result). Also bounds the safe
  single-step pause. **Measure it AFTER the driver-contention rework, not before** (2026-08-01):
  the stall test is the condition that parks a pull-up and pull-down on together, which the rework
  drops from 262 mA to 0.5 mA on the eight worst nets, and a pre-rework figure would read
  pessimistically anyway because eight FETs at ~0.8 W warm the board and leakage roughly doubles
  per 10 C. If both are measured, a floor that moves is evidence the eight sites were heating their
  neighbours. **Revision 2026-07-31:** Eric Schlaepfer documents the MOnSter's low-clock
  failure as shoot-through — *"if the clock slows down too much, the latch will change state,
  causing both pullup and pulldown to be turned on"* — which he had to add protective resistors
  to survive. Checked against `gen/netlist.json`: our 1,018 pull-ups are 10k **resistors**
  (0.5 mA, safe), but **266 nets have a FET-to-FET path** with no series resistance and only 105
  of those also carry a pull-up. Every one of the 164 is a **single** pull-up FET against its
  pull-downs (a 1:1 ratio), so each contended net is the same ~262 mA — there is no near-short.
  The stall commands may therefore damage rather than measure. Mitigations are procedural and
  documented in `pico-controller/README.md`: current-limited bench supply at ~0.5 A and never
  USB, first scans at 3.3 V, sub-millisecond stalls ramped up, and watch supply current. This is
  a topology result, not proof the overlap occurs — but the boards are built and protective
  resistors are no longer an option.
- ~~**Bring-up rail**: SPICE the pass pair at VCC = 3.3 V~~ **Resolved 2026-07-25**:
  `sim/passpair_33v.sp` sweeps 5.0/3.3/3.0 V over three FET models; all four pass gates
  (bootstrapped '1' >= rail, next stage fully driven, source-driven '0' valid, pull-up
  recovery inside a 50 kHz half-cycle) pass at every rail. 3.3 V bring-up is cleared.
  **Re-scoped 2026-07-28**: 3.3 V is a *fallback*, not the first step — bring-up now starts
  at 5 V with no Pico fitted (U1 is DNP, so the level question does not exist yet), and 3.3 V
  narrows the usable clock window from ~50x to ~13x (ceiling 10 kHz vs 20 kHz, leakage budget
  27 nA vs 53 nA), which makes a failure there ambiguous.
  LED brightness quantified separately in `sim/led_tap.sp`: 0.67 mA vs 1.42 mA at 5 V — 47% of the current but only ~20% less perceived brightness. Details in `cards/pass-pair-validation.md`.
- **Clock drive at 5 V**: the board has no pull-up on clk0, so open-drain full-swing clocking
  needs an external 10k croc-clipped from the Φ0 bond pad to VCC. Confirm at bring-up whether
  the 3.3 V push-pull clock is enough, or the external pull-up is mandatory.
- ~~**Optional LEDs**: address/data-bus (24) and IR (8) LED taps~~ **CLOSED 2026-08-09
  [user decision] — the 55 register LEDs stay exactly as designed.** Three reasons, in order of
  weight. (a) **Bus LEDs would duplicate what is already visible.** `ab0-15`, `db0-7`, `R/W` and
  `SYNC` all terminate on the bond-pad ring, and the Pico captures the whole bus every cycle with
  the `wifi` panel already displaying it live. The register LEDs earn their place precisely because
  A/X/Y/S/P/PC are *internal* and no external observer can see them; the bus is not. IR is the one
  genuinely internal candidate, and even IR is derivable — at `SYNC` the data bus carries the opcode
  being fetched, so the firmware can already name the instruction with no added part.
  (b) **A 7-segment alternative was considered and rejected on readability, not cost.** At the
  achievable ~10 kHz (~2,900 instructions/s against a ~50-60 Hz flicker-fusion threshold) a hex
  display is exactly as unreadable as the LEDs while free-running — the same blur, two digits wide.
  Per-bit LEDs are the *better* instrument at that speed: a stuck bit shows as a steady LED among
  flickering ones and localises the fault to one register bit and thus one region of the die, and
  apparent brightness encodes duty cycle, so the blur itself carries information. (c) **Driving
  7-segments is the real cost**: hex-to-segment decode from internal bits cannot come from the Pico
  (those nodes are invisible to it), so it needs either ~100 FETs per digit — order **1,200 FETs**,
  +30% on transistor count, and *our* logic rather than the die's — or a companion MCU plus
  shift registers, which puts a hidden microcontroller inside a board whose premise is that there
  isn't one. **Space was measured, not the blocker**: the top face is 41% component-free but only in
  strips, the largest usable being **233.5 x 11.5 mm** along the bottom edge (also 163.5 x 8.5 mm
  above the decode PLA), which would take a row of twelve 0.28" digits. Any of this is a **rev C
  respin** in any case — the full pipeline from `gen_pcb.py` onward, placement and routing included,
  and new nets would hang off `ab`/`db`, the most congested signals on a board that already needed
  6 layers. Revisit only if a rev B respin is ever fabricated.
- **Licensing**: `segdefs.js` is CC BY-NC-SA (noncommercial). Fine for this hobby build;
  would need clarifying before any commercial use of derived design files.
- ~~**Order status**~~ **RESOLVED 2026-07-28 — ordered and paid.**
  €775.88 at checkout, ≈ €973 landed (≈ €243 per assembled CPU). Full breakdown in the
  "Cost — AS ORDERED" table. Est. ship 2026-08-06; UPS bills the Swedish import VAT separately.
