# decision log — the long entries, in full

Split out of `project-plan.md`'s Decisions section on 2026-08-30, **verbatim and unedited**. The plan
keeps every decision, but the narrative ones — hardware findings and milestones that were filed as
decisions — are condensed there to the part that still binds, with a link here for the reasoning,
the measurements and the retractions.

**Read this when a condensed entry in the plan is not enough**: when you need the numbers behind a
finding, the method that produced it, or why an earlier conclusion was wrong. Several entries here
correct earlier ones, and the correction is usually the valuable half.

Entries are in the order they had in the plan, which is roughly append order and not strictly
chronological; a cross-reference by date resolves here as it did there.

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
