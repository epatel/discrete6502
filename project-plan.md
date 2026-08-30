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

**Append new decisions here.** Short directives and settled choices are kept in full; the long
narrative entries — hardware findings and milestones filed as decisions — were condensed on
2026-08-30 to the part that still binds, each linking to its verbatim text in
[`cards/decision-log.md`](cards/decision-log.md). Nothing was removed from the record.

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

- 2026-07-27 **[correction]** The core FET is **BSS138W** (LCSC `C504052`, JSCJ, SOT-323, Ciss 27 pF,
  Vgs(th) 1.5 V), not "BSS138K" — a name the part does not have, used in earlier entries below.
  **No engineering consequence:** the LCSC code was always right and every simulated figure matches.
  `tools/gen_netlist.py` still emits the string "BSS138K" **on purpose** — it is the BOM Comment
  field, whose sha256 is pinned in `RELEASE.md` and already uploaded; JLC matches on the LCSC code.
  [full entry](cards/decision-log.md)

- 2026-08-08 **[M6, settled]** The acceptance suite is **built by script, not by hand** —
  `tools/build_functest.py` emits `gen/functest/<test>.hex` + `<test>_traps.csv`, sets `ram_top = $40`,
  folds 64 KB to 16 KB the way the hardware does, and patches the reset vector. **Both images reach
  PASS in an emulator before hardware existed**, and the toolchain reproduces upstream's committed
  binary byte-for-byte. Consequences that bind: **`report = 1` does not fit** (the image runs past
  the `$3FFA` ceiling), so the bus side channels are the only option; the run is **an afternoon, not
  overnight** (2 h 41 m at 10 kHz); `test_case` runs 0..43 then `$F0`, 45 checkpoints.
  [full entry](cards/decision-log.md)

- 2026-08-12 **[M6, hardware finding]** **Step 1's "must read high" gate was wrong: there is no
  resistive VCC–VSS path at all**, so the meter reads 1,899 FET body diodes and the number depends on
  the range — the same board reads 195 Ω / 314 Ω / 3.77 kΩ on the 200 / 2k / 20k ranges at a constant
  0.36–0.47 V. **A fault is <1 Ω, or a value that does NOT change with range.** Step 1 is therefore a
  *positive* test: the path needs the pull-ups, so it proves ~1,000 back-side 0402s are populated.
  Run `tools/step1_model.py` rather than re-deriving. [full entry](cards/decision-log.md)

- 2026-08-16 **[M6, correction + firmware]** **A spurious IRQ produces a wrong verdict, not a stopped
  run** — correcting 2026-08-08 below. `$380B` (NMI) really is a `jmp *`, but **`$3819` is not a trap**:
  it is `irq_trap`, the live BRK-test handler, so a spurious IRQ is *absorbed*, corrupts Y and SP, and
  surfaces later as a failure at an unrelated address. **Tie `irq` high before any long run.** Also
  settled [user decision]: the test images compile in only behind `-DEMBED_FUNCTEST=ON`, **off by
  default, for licensing** — the suite is GPLv3, this repo CC BY-NC-SA 4.0, and no binary containing
  GPLv3 material is ever produced here. [full entry](cards/decision-log.md)

- 2026-08-25 **[M6, MILESTONE]** **The discrete 6502 executes instructions**, proved by finding the
  program counter in a video of the register LEDs: on a NOP free-run PC bit *b* must toggle at
  `(clock/2)/2^(b+1)` Hz, and **four bits were identified BY NAME** on a measured factor-of-two ladder
  (PCL7 4.407, PCH0 2.170, PCH2 0.542, PCH3 0.271 Hz). 92 LEDs land on a predicted rate, no unexplained
  peaks. **Lesson kept: the anonymous test cannot fail interestingly** — naming the LEDs is what makes
  it falsifiable; an earlier version credited *aliased* fast bits and was falsified within hours, since
  a camera integrates over its exposure and cannot alias. **Scope:** fetch, decode PLA, PC incrementer,
  address drivers, on-board clock regeneration — **not** the ALU, registers, stack, flags or branches.
  Tooling `tools/pc_ripple.py`. [full entry](cards/decision-log.md)

- 2026-08-24 **[M6, hardware finding — CORRECTS 2026-08-01, then itself corrected 2026-08-25/26]**
  A FLIR image found **no localised hot spot** (peak ~30 °C), which retracted the 3–4 nets at 0.90 W
  model and proposed a distributed ~210 µA-per-FET explanation instead. **Both halves have since been
  scoped**: the image was taken under a NOP free-run through a `$EA` tie-off, the one workload that
  hides the effect, and the distributed reading applied to a board with *no Pico* and everything
  floating. See `cards/driver-contention.md` for the full chain before quoting any figure.
  [full entry](cards/decision-log.md)

- 2026-08-24 **[M6, hardware finding]** **Charge retention measured at 1.9–2.3 nA per FET — the clock
  floor is closed in the design's favour.** Measured with a phone camera at 120 fps and no Pico fitted,
  from the decay of `a1`/`a2`/`p1`, nets that carry no pull-up, no VCC-side FET and no pull-down, so
  **leakage is the only mechanism that can turn them off**. Worst node `sb6` holds 1.13 ms ⇒ floor
  **871 Hz**, a **23× window** to the 20 kHz ceiling and 45 °C of headroom. Recommended external clock
  moved to **4–5 kHz** (geometric centre of the real window). [full entry](cards/decision-log.md)

- 2026-08-24 **[M6, hardware finding]** **A floating data bus jams the CPU; tie it to `$EA` through
  10 kΩ.** 12 of 256 opcodes are undocumented KIL/JAM, so a floating bus halts within ~20 instructions
  — signature is a monotonically decaying lit-LED count. Resistors never wires, so the CPU wins if it
  drives. Also settled: **the clock is regenerated on-board**, proven by contrast — the same nodes lose
  charge in 65 ms unclocked and hold for seconds clocked. [full entry](cards/decision-log.md)

- 2026-08-13 **[rev A defect, cosmetic]** **4 of the 36 bond pads are in the wrong slot** — A6, VSS,
  D7, R/W — which puts A0–A5 one slot down from where the die says. **Nothing is miswired or
  mislabelled**: every pad sits on the net its silk names, so **locate a pad by its label, never by
  counting**. Cause is `rim_slot`'s greedy first-come allocation in `tools/gen_pcb.py`; the
  order-preserving fix and its feasibility numbers are in `cards/bond-pad-ring.md`, **not applied**
  because it moves pad positions and forces the whole pipeline. Also: **`cclk` is internal node 943,
  not a pad, and must not become one.** [full entry](cards/decision-log.md)

- 2026-08-08 **[M6, hardware finding]** **`irq` and `nmi` float on the assembled board** — neither
  carries a pull-up (unlike `rdy`/`so`), and the Pico drives neither. **Croc-clip both bond pads to VCC
  before any long run.** See the 2026-08-16 correction above for why this is necessary rather than
  merely tidy. [full entry](cards/decision-log.md)

- 2026-07-26 **[M6, settled]** The bring-up acceptance test is **Klaus Dormann's
  `6502_65C02_functional_tests`** (GPLv3) — the standard suite for 6502 *re-implementations*. Checked
  against our constraints: the stock image ends ≈ `$3800`, so **the ab14/ab15 sacrifice does not block
  it**. It has no I/O, so `pico-controller/common/functest.c` reads its two side channels off the bus:
  `test_case` (`$0200`) as progress, a repeated opcode-fetch address as the verdict. Run
  `6502_decimal_test.a65` first — decimal mode is what emulators most often get wrong.
  [full entry](cards/decision-log.md)

- 2026-07-25 **[user decision, at order]** Core FET switched to **BSS138K, LCSC C504052** (JSCJ, SOT-323) — 2N7002W (C139444) not in JLCPCB inventory. BSS138 was the designated fallback since M2 and is SPICE-validated; Vth 0.8–1.5V improves 3.3V-bring-up margins. Same package/pinout; netlist, generator, and BOM updated (datasheet reviewed: 27pF Ciss, 50V, standard G/S/D). BOM also re-chunked to ≤2000-char designator cells (JLC upload limit).
- 2026-07-25 **[user decision]** The 26 Pico GPIO series resistors (1k 0402, C11702 basic) are now POPULATED in the factory assembly (was DNP) — prepares every board for the aftermarket Pico with zero hand-soldering of passives; cost ≈ +$0.30/board. Only the Pico module itself remains aftermarket. Changed consistently in gen_netlist.py, netlist.json, and all three board files; parity re-verified.
- 2026-07-24 **[locked, user decision]** Board goes **6-layer**: F.Cu(sig-H) / In1(GND) / In2(sig-V) / In3(sig-H) / In4(VCC) / B.Cu(sig-V). Rationale: 2 signal layers bottom out at ~36 conflicted nets across two independent 24h negotiation runs (a genuine capacity floor at 0.127 rules); 6 layers resolves with certainty for ≈ +$40–70 per assembled CPU at qty 5 (accepted). Implementation: layer-surgery on the presignal snapshot (VCC zone In2→In4) preserving all placement/power work; router generalized to 4 routing layers.
- 2026-07-22 **[user intent confirmed]** The Pico 2 W site's purpose is to DRIVE the 6502: clock master + memory emulator (serve reads / capture writes each cycle). GPIO budget (26) forced dropping ab14/ab15 → the Pico sees memory mirrored every 16 KB (reset vector $FFFC appears as $3FFC — fine for all planned test programs). Kept instead: res (controlled reset) + sync (instruction-boundary tracing). Dynamic logic ⇒ no indefinite clock-stop; single-step = burst-to-sync + brief pause. Full-address remap (trade res/sync) is a one-line gen_netlist change if ever needed.

- 2026-07-25: **M5 COMPLETE — board fully routed, electrically DRC-clean.** The pipeline order is
  load-bearing and lives in `cards/layout.md`; the three finishing insights that made it clean (stubs
  inside pad copper, hard-masked net-carve, exact-geometry via nudges) are recorded there too.
  [full entry](cards/decision-log.md)

- 2026-07-25: **M6 prep started — Pico firmware scaffolded** in `pico-controller/`. Two facts that
  still bind: **the board has NO pull-up on clk0**, so the clock must be driven push-pull; and a 3.3 V
  clk0 into a 5 V core is functionally identical to a 5 V one (simulated — clk0 gates only two
  pull-downs and the internal phases are regenerated on-board at full swing).
  [full entry](cards/decision-log.md)

- 2026-08-28 **[M6, hardware finding + repair]** **A single transistor, Q2577, pinned S bit 0 high and
  broke every stack operation** — 20 kΩ gate-drain leak against 177 kΩ on its matched twin, on a net
  whose drain carries a pull-up and whose gate `s0` has no pull-down. Repaired by transplanting the FET
  from Q4050 (a P2-flag LED driver). **Not the ratio bug** — a random fab defect, the first located.
  **Method that worked after three wrong calls: an in-circuit two-point reading measures the part AND
  its surroundings, so on a faulty net every part reads wrong.** Compare each suspect against its
  matched twin on an adjacent bit and trust only the reading the fault cannot explain. Full record in
  `docs/stack-decrement-defect.md`. [full entry](cards/decision-log.md)

- 2026-08-28 **[M6, milestone]** **23 datapath subtests pass on board #1** (`tools/quick_selftest.py`):
  registers and transfers, ALU with carry and borrow, shifts, stack both directions with S tracking,
  flag save/restore, zero-page and absolute-indexed addressing, JSR/RTS. **Validated on the reference
  visual6502 netlist first**, which caught two bugs in the test program that would have read as
  hardware faults. The verdict is the **address the CPU loops at**, so it survives a 32-cycle trace
  window and needs no memory read-back. Klaus Dormann's suite remains the acceptance gate.
  [full entry](cards/decision-log.md)

- 2026-08-28 **[operational, learned the hard way]** **Never write Pico flash while the CPU is
  running, and never poll a long run over wifi.** `op=autorun`/`clocksave`/`store` stall the core
  including lwIP — one issued mid-run wedged the web server and cost the stored wifi credentials. The
  lwIP stack also wedges under repeated short-lived requests, seen at one poll per minute. The CPU
  survives both on core 1; only the observation channel dies, which is why the verdict is printed to
  USB serial. [full entry](cards/decision-log.md)

- 2026-08-30 **[M6, settled — hardware facts about the Pico site]** Three things about `U1` that
  close recurring proposals. **(a) Pico VSYS cannot be decoupled from board VCC.** Pad 39 is a B.Cu
  SMD pad with a via-in-pad 0.28 mm off centre and **no attached tracks**, so it reaches `vcc` only
  through the In4 plane — there is nothing to cut, and lifting the pin is impossible with the module
  soldered. **Stop proposing it.** **(b) `RUN` (pin 30) is `nc30`, unconnected** — so the module can
  be reset without unplugging: hold BOOTSEL and short pin 30 to pin 28 (`vss`), *avoiding pin 29
  which is `clk0`*. Equivalently, cycle the board supply with BOOTSEL held, since VSYS is board VCC.
  **BOOTSEL was never broken** — unplugging USB simply never reset anything. **(c) `VBUS` (pin 40) is
  `nc40`**, and with the user's data-only cable there is no host-to-board path but ground; tinyusb
  forces `VBUS_DETECT_OVERRIDE_EN` (`dcd_rp2040.c:364`) so the module still enumerates self-powered.
  The VBUS→VSYS Schottky hazard is therefore closed, and **BOOTSEL mode is the guaranteed recovery
  path** because the bootrom drives no pin and leaves the board at 0.24 A.

## Current state / handoff

**Newest first, and only the live entries.** Everything older was moved out on 2026-08-30, verbatim
and by date, because this file is `@`-imported into every session and history is not state:
[`cards/bring-up-log.md`](cards/bring-up-log.md) holds the boards-on-the-bench record
(2026-08-12 … 2026-08-26) and [`cards/build-log.md`](cards/build-log.md) the design, fab-package and
firmware work that preceded it (2026-07-18 … 2026-08-08). A cross-reference of the form "the
2026-08-24 entry" resolves by date in whichever of the three files covers that date.

- 2026-08-30 (evening, bench session): **The polarity is inverted from everything this plan has
  assumed: the board is quiet with `CLK0` held LOW and draws an unstable 1–2 A when it is not.**
  Nothing in the netlist, the board or the fab package changed. All board changes were temporary
  clip-on experiments; the 31 kΩ pull-down on the `CLK0` pad is still fitted.
  **Use silk labels, not `TPnn`** [user directive, asked twice]. The bond pads are labelled `CLK0`,
  `VCC`, `VSS`, `A0`–`A15` … on the silk; `TPnn` designators exist only in `gen/netlist.json` and
  are invisible at the bench. For translation: `TP25` = `CLK0`, `TP35` = `VSS`, `TP36` = `VCC`.
  There is only **one `VSS` pad** on the ring, so "clip the ground somewhere else" is not available.
  **THE RESULT, measured two ways:**

  | `CLK0` pad | Board current | Rail (DSO112 on `VCC`/`VSS`) | Pico |
  |---|---|---|---|
  | grounded through 1 kΩ to `VSS` — **60 mV** | **0.24 A** | **stable** | **will not start** |
  | not grounded (31 kΩ only) — **1.7 V** | **1–2 A, swinging** | — | starts |

  **This reconciles the orphan measurement the plan has carried as a contradiction since 08-29** —
  "clock parked, 2.2 A" with `clk0` floating against "clock parked, 0.30 A" with it driven. Same
  words, opposite pin states. Floating is the bad state; low is the good one. **"Park `clk0` low"
  was never the problem, and the 08-30 proposal to invert it in `selftest`, `tester` and `wifi` must
  not be carried out.**
  **RETRACTED, and it is listed as an established fact in `docs/plan-2026-08-30.md` §1:**
  *"`clk0` above ~1 V ⇒ the board draws 2+ A — 0.77 V → 0.24 A; 1.76 V → 2.5 A."* Measured tonight:
  **1.7 V and 0.24 A simultaneously.** The most likely reading of the original pair is that 1.76 V
  was measured *while* the board already drew 2.5 A and the charger had folded to 3.6 V — an effect
  of the sagging rail, recorded as its cause. That table row is struck in the file.
  **The mystery current is measured cleanly for the first time: ~62 µA sourced into `CLK0`.**
  60 mV across 1 kΩ ∥ 31 kΩ ≈ 969 Ω. Consistent with the 55–85 µA implied by the 0.77 V and 1.7 V
  readings, and independent of the 31 kΩ. **Two candidates, neither yet tested.** (a) **`D66`** — a
  `1N4148WS` clamp on this net, **cathode to `vcc`, anode to `clk0`**, so its reverse leakage flows
  from `VCC` *into* `clk0`, exactly the observed direction; a healthy part leaks tens of nA, so 62 µA
  would mean a degraded one. Testable **unpowered**: a healthy clamp shows a diode drop, a leaky one
  does not. (b) **RP2350 GPIO input leakage (the `E9` erratum class)**, whose documented workaround
  is an external pull-down of ~8.2 kΩ or stiffer — check it against the datasheet, SDK 2.1.1 does not
  name it. **This substantially weakens the contamination hypothesis in the entry above**, which was
  built on the premise that 62 µA had no legitimate source. It has at least two.
  **The `CLK0` net topology, which was being reasoned about wrongly.** The pad is **not** on net
  `clk0`:

      U1 pin 29 (GP22) --[R1107 1k]-- clk0_ext --[R1079 100R]-- clk0 --+-- Q2229 gate
                                          |                            +-- Q2420 gate
                                    CLK0 pad, 31k                      +-- D66 -> vcc  (clamp up)
                                                                       +-- D67 -> vss  (clamp dn)

  **UNEXPLAINED, and left standing rather than explained away: with `CLK0` grounded the Pico will not
  start** — no USB, no BOOTSEL — while `VCC`–`VSS` reads **4.97 V**, current is 0.24 A and the scope
  shows a stable rail. **It is not a power problem.** Nor is there an obvious path: GP22 sits behind
  1 kΩ + 100 Ω, and at reset RP2350 pads are `PADS_BANK0_GPIO0_RESET = 0x116` — `IE=0` (input buffer
  **disabled**), `OD=0`, `PUE=0`, `PDE=1` — and `usbonly` never touches the pin, so that pad is
  electrically inert. Disconnecting the 1 kΩ with power applied lets the Pico start again.
  **The live hypothesis, and the next measurement, both concern the board rather than the Pico:**
  a swinging 1–2 A with an undefined input on the node feeding on-board clock regeneration suggests
  **the chain is self-oscillating** — `CLK0` at 1.7 V sits in the inverter gain region, and the chain
  drives `cclk` (13 nF) and `cp1` (5.4 nF). **Put the scope probe on the `CLK0` pad with the 1 kΩ
  removed.** Oscillating ⇒ the board free-runs whenever `CLK0` is undefined, which would explain the
  1–2 A, three days of brownouts, and why every firmware touching the pin behaved unpredictably.
  Flat at 1.7 V ⇒ the current comes from elsewhere.
  **Firmware and tooling, all working.** `python3 tools/pico_flash.py usbonly` flashed **via the
  1200-baud touch with no button and no supply cycle** — the tool does what it claims. The board then
  ran **181 consecutive passes over 90.01 s, 181 of 181 expected, no gap over 0.5 s, no counter reset**,
  and the counter was already at 56 when the port was opened, so **~118 s of continuous uptime**
  against the 45 s `usbonly` managed on 08-30. Rest current 0.24–0.29 A. **The Pico, the cable, the
  port and the rail at rest are healthy**, and [user] **a data-only USB cable (red wire cut) works** —
  tinyusb forces `VBUS_DETECT_OVERRIDE_EN` (`dcd_rp2040.c:364`), so the module enumerates self-powered.
  **Five models were proposed and falsified tonight, listed so nobody re-proposes them:** (1) a
  "forbidden zone" in which no `CLK0` logic state is safe — grounding it is safe; (2) grounding `CLK0`
  browns out the rail — current does not move; (3) an `E9` synthesis in which `clk0` was never truly
  low — it is now, and the board likes it; (4) DMM-blindness to microsecond transients — the scope
  shows a stable rail; (5) the clip disturbing the power feed — `VCC` reads 4.97 V with it fitted.
  Each died on the next measurement, which is the process working, but **the record should carry the
  measurements and not the models.**
  **Operational:** **leave the 1 kΩ fitted from the `CLK0` pad to `VSS` whenever the Pico is not in
  use** — 0.24 A with a stable rail is the safe storage state, and 1–2 A swinging is what the board
  defaults to without it. **`gen/firmware/wifi-known-good-0891df4.uf2` is built and waiting but must
  not be flashed yet** — at `0891df4` `defaults()` sets `autorun = 1` and the flash is erased, so it
  would start clocking at power-up.
  **Next:** (1) scope the `CLK0` pad, oscillating or not; (2) check `D66` unpowered for the 62 µA;
  (3) the 16 `idb`/`sb` precharge reworks, starting at `idb7`/Q1830 — [user] **`idb` heat confirmed
  with the camera, `sb` not yet examined**; (4) ~500 µF low-ESR across `VCC`/`VSS`; (5) only then the
  known-good image and a 23-subtest verdict.

  **LATER THE SAME EVENING — the board has hysteresis, and that is why every model kept dying.**
  [user, with the DSO112 on the `CLK0` pad] The node is **intermittent**: sometimes below 1 V,
  sometimes above 1.5 V, wandering across the switching threshold on its own. tty presence tracks the
  **voltage**, not the current — tty appears when `CLK0` is above ~1.5 V, and in that condition the
  board is *usually* at 1.5–2.5 A but was once seen at 0.27 A. **The same voltage giving two different
  currents is the tell:** the board's state is not a function of `CLK0`'s present level.
  **The sequence that shows it, and it should be impossible:** with tty up and the board running, the
  1 kΩ was fitted → **tty vanished**; removing it did **not** bring the tty back; the tty returned only
  when the **DSO112 was clipped from `VSS` to the `CLK0` pad**, at which point the board also began
  drawing more current. **A ~1 MΩ scope input cannot pull that node anywhere** — it is thirty times
  weaker than the 31 kΩ already fitted. What it can do is give stored charge somewhere to go, or
  perturb a node balanced at a tipping point.
  **So the board's behaviour depends on where `CLK0` has recently been, not only on where it is** —
  and the discharged state **persists after the 1 kΩ is removed**. There is a state variable nobody has
  been tracking. Plausible storage: the `Q2229`/`Q2420` gates and the `D66`/`D67` junction capacitance
  on `clk0` itself, and one stage back `cclk` (13 nF) and `cp1` (5.4 nF), which are large.
  **This is the single best explanation for the whole three days**, and specifically for why five
  successive models each died on the next measurement (listed above): every one of them assumed the
  node's voltage determined the state. **Treat any single-point reading of `CLK0` as meaningless
  unless its recent history is recorded with it.**
  **It also reframes the Pico puzzle and reopens it.** The statement is not "the Pico will not start
  when `CLK0` is low" but "**the Pico will not start when the board is in the discharged state**" —
  a state that outlives the resistor that caused it. Whether GP22 is involved at all is **open again**;
  the `IE=0`/`PDE=1` argument for the pad being inert still stands and is now less obviously in conflict
  with anything.
  **Pull-down sizing, now against a measured leak of ~62 µA** (superseding the 47 kΩ and 4.7 kΩ figures
  in `docs/clk0-pulldown.md`, both sized against a leak nobody had measured):

  | pull-down | `CLK0` sits at | observed |
  |---|---|---|
  | **31 kΩ (currently fitted)** | **1.9 V** — above threshold | 1.5–2.5 A, wanders |
  | 4.7 kΩ | 0.29 V | untried — the obvious candidate |
  | **1 kΩ** | **0.062 V** — matches the measured 60 mV | 0.24 A, stable rail |

  **NEXT MEASUREMENT, and it needs only the scope already connected:** leave the probe on `CLK0` and
  watch it **while fitting and then removing the 1 kΩ**. A charge-storage node recovers on an RC ramp,
  and the timebase that shows the ramp gives the capacitance — 62 µA into a few hundred pF is
  microseconds, into the nanofarad range is milliseconds. **If it snaps back instantly, charge storage
  on `CLK0` is the wrong idea and the memory lives deeper in the chain.**
  **Standing warning:** whenever the board is at 1.5–2.5 A, **check whether it is warming.** Sustained
  amps through the 16 un-reworked `idb`/`sb` precharge sites is the one mechanism by which this
  diagnostic work could do lasting damage, and it is the state the board keeps falling back into.

  **THERMAL CONFIRMATION, end of evening — all sixteen un-reworked sites heat, and the 2026-08-29
  model is vindicated end to end.** [user, board now powered off] **`sb0-7` AND `idb0-7` all got hot**,
  the first direct thermal evidence on the `sb` half, which until tonight was "not looked at yet".
  **The heat tracks tty** — i.e. it appears when `CLK0` is above ~1.5 V — "sometimes only briefly on
  power up, most times it stays on while tty is on".
  **That is exactly what the 2026-08-29 entry predicted:** *"`clk0` LOW parks `cclk` LOW and all 32
  precharge FETs off; `clk0` HIGH turns them all on at once."* `CLK0` above threshold → `cclk` high →
  all 32 precharge FETs on → the 16 with no series resistor contend → 2.5 A and hot. **The 2026-08-30
  `cp1` worry is retired: park-`clk0`-low is correct**, and my "the polarity is inverted" framing above
  overstated it — nothing inverted, the 08-29 trace was right and is now confirmed thermally.
  **A stuck-HIGH `CLK0` is worse than clocking the board.** Clocking gives those sites ~50% duty;
  sitting at 1.9 V gives them **100%**, conducting continuously. That is the 2.5 A now against the
  **0.5 A measured while actually clocking on 08-28**, and it retroactively explains that day's
  "startup trap: with the clock parked the board draws 2.2 A". **So the board's default state with the
  31 kΩ fitted is the most damaging one available to it**, and every hour it has sat powered and
  unattended since 08-29 has been cooking those sixteen parts. **Do not leave the board powered until
  a stiff pull-down is fitted** — the hysteresis means it sometimes lands quiet and sometimes lands
  hot, so "it looked fine when I walked away" is not predictive.
  **Two fixes, independent, neither substituting for the other:**
  **(1) A stiff pull-down on the `CLK0` pad to `VSS` — 4.7 kΩ (0.29 V) or 1 kΩ (0.062 V, measured).**
  Makes the *resting* state safe. Urgent, one part, and it protects the board during the rework.
  Try **4.7 kΩ first**: it is comfortably below the 0.8 V threshold while presenting a much higher
  impedance than the 1 kΩ, which is the value the Pico demonstrably objects to.
  **(2) The 16 series resistors (10 kΩ in series with pin 3), `idb0-7` and `sb0-7`.** Makes the board
  *operable*: clocking **requires** driving `CLK0` high, so those FETs conduct by design and the
  resistor is what stops that being 262 mA each. Map: `docs/rework-precharge-marked.jpg`
  (`tools/mark_rework_precharge.py`). Start at **`idb7`/Q1830**, where camera and duty model agree.
  **[user] The 16 reworks are planned for 2026-08-31.**

- 2026-08-30 (later): **The regression hunt eliminated every candidate the previous entries were
  built on, and the leading explanation is now contamination from the 2026-08-28 water rinse.**
  Nothing on the board, in the netlist or in the fab package changed today.
  **First, a correction that resets the baseline: 2026-08-28 was never a healthy state.** The same
  entry that records 23 subtests passing also records the Pico **losing power every 25–45 s** —
  cycle counter to zero, USB gone, mDNS dropped — and the decimal test's 98 s ended when the network
  dropped. So the comparison is not working→broken but **25–45 s of clocking (08-28) → 15 ms
  (08-29)**, roughly 1000×. **Withdrawn: my claim that the failure is monotonically worsening** —
  230 ms (08-30) is *longer* than 15 ms (08-29), and those were different firmwares under different
  workloads. Only the 08-28 → 08-29 step is a clean comparison.
  **Four candidates eliminated, each by evidence rather than argument:** [user] the **epoxied
  `adh`/`adl` sites run cold**, so no lifted pin 3 shorted out its series resistor and reverted a
  site — the failure mode the plan warned about did not happen; [user] the **supply never changed**
  — the same 2.4 A charger throughout, so a supply swap explains nothing; `git diff
  0891df4..HEAD -- pico-controller/common/bus6502.c` touches **only the phase-split setters**, so
  **`bus_init` and its clk0 handling are byte-identical to the build that ran on 08-28** — the board
  was already being parked clk0-low on the day it clocked for tens of seconds; and the **31 kΩ
  pull-down postdates the 08-29 step**, so it cannot be its cause.
  **That leaves no human action between the 28th and the 29th, which points at a delayed-onset
  physical change — and the 08-28 IPA wash and water rinse is the only candidate.** No drying
  protocol is recorded. It fits three things otherwise unexplained: the `cclk` fault that the wash
  cleared was itself diagnosed as **conductive residue, not damage**, so this board has a
  demonstrated contamination history and a water rinse redistributes as easily as it removes;
  trapped moisture under 5,425 packages evaporates over hours to days, which is exactly the
  overnight onset; and **the 25–57 µA sourced into `clk0` should not exist** — that node's only
  loads are two FET gates and one Pico pin, so gate leakage is picoamps and 25 µA is seven orders
  of magnitude too much. **Treat that current as the smoking gun, not as an open question.**
  **The pull-down sizing debate is a distraction and should stop.** 31 kΩ versus 4.7 kΩ argues about
  how firmly to hold `clk0` near ground, while **driving it hard to ground is what kills the board in
  1 ms**. A push-pull drive is stronger than any pull-down; if low were safe the hard drive would be
  the safest case. No resistor value addresses that. **Leave the 31 kΩ fitted and unchanged** until
  the other variables are closed — swapping it tests nothing.
  **Withdrawn: lifting pin 39 to decouple Pico VSYS from board VCC.** [user caught it — the module is
  soldered] Checked in the board file: pad 39 is a **B.Cu SMD pad with a via-in-pad 0.28 mm from its
  centre and zero attached track segments**, so it reaches VCC only by dropping into the In4 plane.
  There is nothing to cut; separating it means drilling a via into an internal plane on a 6-layer
  board. **Do not attempt it.**
  **The reflashing difficulty has a free fix instead: `U1` pin 30 is `RUN` and the netlist has it as
  `nc30` — entirely unconnected.** Reset the module without unplugging by holding BOOTSEL and
  momentarily shorting **pin 30 (board 30.31, 102.27) to pin 28 (VSS, 30.31, 107.35)**. **Pin 29 sits
  between them and it is `clk0`** — fine probe, not a clip. Simpler still, and needing no probing:
  **charger off, hold BOOTSEL, charger on** — VSYS *is* board VCC, so cycling the board supply is a
  real power-on reset with BOOTSEL sampled. The button was never broken; unplugging USB just never
  reset anything.
  **[user] A data-only USB cable now exists (red wire cut), and it is verified to work.**
  `lib/tinyusb/src/portable/raspberrypi/rp2040/dcd_rp2040.c:364` writes
  `USB_PWR_VBUS_DETECT | VBUS_DETECT_OVERRIDE_EN` at device-controller init, so the module enumerates
  self-powered with no VBUS. Combined with **pin 40 (VBUS) being `nc40`**, there is now **no
  electrical path from the host to the board except ground** — the VBUS→VSYS Schottky hazard is
  structurally impossible rather than procedurally avoided, and the host is permanently off the
  suspect list. **It also cleans up a confounded signal: any future USB dropout is now unambiguously
  the board rail folding.** The cost is that the Pico is powered only from board VCC, so every USB
  session needs the board rail up. **The guaranteed recovery path is BOOTSEL mode**, where the
  bootrom runs instead of user firmware, nothing drives `clk0`, and the board stays at its 0.24 A
  rest current. *Caveat: on a C-to-C cable, cutting VBUS may also break CC attach negotiation.*
  **TRAP, before anyone flashes the known-good image: at `0891df4` `defaults()` sets
  `live.autorun = 1`, and the flash is erased.** That build will start clocking at power-up and go
  straight to the 2.5 A state. The "blank flash does not autorun" guard was added on 08-30 and is
  **not** in it. **Do not flash `wifi-known-good-0891df4.uf2` until the 16 `idb`/`sb` reworks are
  done.**
  **Built and waiting: `gen/firmware/wifi-known-good-0891df4.uf2`** (781,312 bytes, 1,526 blocks;
  ABSOLUTE block at `0x10ffff00` plus RP2350_ARM_S `0x10000000–0x1005f500`, structurally identical to
  the current builds). Built from `git archive 0891df4` in a scratch tree; the working copy was not
  touched, and `gen/firmware/` is gitignored. No build-time wifi credentials are needed.
  **Next, in this order and none of it needs the board clocked:** (1) flash `usbonly` (HEAD build —
  it does not exist at `0891df4`) by BOOTSEL + supply cycle; (2) **re-clean and dry properly** — IPA
  flood, a second IPA pass to displace water, then a real dry, an hour at 60–70 °C or several hours
  of warm airflow — then with the board powered and nothing driving the pin, **re-measure `clk0` to
  VSS**; if 0.77 V falls toward ground and the 25–57 µA disappears, the last two days were chasing a
  contamination artifact; (3) the **16 `idb`/`sb` precharge reworks**, starting at `idb7`/Q1830 where
  the thermal camera and the duty model agree — [user] **new heat is confirmed at `idb`; `sb` has not
  been looked at yet**; (4) only then flash the known-good image and look for the 23-subtest verdict.
  **The clean comes before the rework on purpose:** sixteen more rework operations on a board that
  may be leaking would leave the next set of measurements as ambiguous as this one, and if the
  leakage is real the reworks will not fix it.

- 2026-08-30: **The asymmetric clock did not save it, and that is a real result: the brownout is
  peak-limited, not average-limited.** Flash erased with `picotool erase -a` and the 9%-duty selftest
  (40 us high / 400 us low, ~2.3 kHz) flashed clean. **Two attaches, identical both times: the link
  comes up, prints `link up, running 23 subtests now`, and drops 0.32-0.36 s later** — the firmware
  sleeps 300 ms after the banner and then clocks, so the rail collapses within roughly 20-60 ms of
  the first clock edge, and the verdict never prints. The Pico then takes ~27 s to come back, which
  is its own 30 s USB wait, i.e. it is rebooting and re-running, not hung.
  **What this rules out:** cutting the average current is not enough. The 2026-08-29 entry predicted
  9% duty would give "about a tenth of the contention current" and it does — but VSYS browns out on
  the **40 us peak**, which duty cycle does not touch. That was in the same entry as a condition
  ("peaks short enough that ~500 uF of bulk across VCC/VSS can supply them") and the bulk capacitor
  was never fitted, so the experiment tested half the proposal.
  **Consequence: bulk capacitance is now the gating item, not an option** — order 500 uF+ low-ESR
  across VCC/VSS (TP36/TP35), or the 16 remaining `idb0-7`/`sb0-7` precharge sites reworked to remove
  the peak at source. The clk0 pull-down (`docs/clk0-pulldown.md`) fixes the *undriven* state and
  would not have helped here, since the clock was being driven throughout.
  **Not a firmware problem, and one more possibility is closed:** `tools/quick_selftest.py` documents
  itself as a ~200-cycle test, so `RUN_CYCLES = 300` is adequate and the missing verdict is not the
  test being cut short.

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

- 2026-08-30: **The fault is isolated to a single pin transition, and it falsifies the model this
  plan has carried since yesterday. Full handoff for a fresh agent:
  [`docs/session-2026-08-30.md`](docs/session-2026-08-30.md).** Nothing on the board, in the netlist
  or in the fab package changed.
  **The isolation, by three builds that each remove one variable:** a firmware touching no pin at
  all holds a USB link for **45 s** (91 lines); `bus_init` with `clk0` left an *input* is healthy for
  **8.5 s**; **driving `clk0` low kills the module in 230 ms, and a 1 ms pulse is enough.** So the
  Pico, the cable, the port and the rail at rest are all cleared — every failure is caused by one
  GPIO transition.
  **The model gap that matters:** `docs/clk0-pulldown.md` traced `clk0` → `cclk` and concluded
  "clk0 low is the quiet state". **It never traced `cp1`.** Traced now — `clk0` LOW → `n358` HIGH →
  `n1715` LOW → `n1399` HIGH → **`cp1` HIGH**, 198 gate loads, and φ1 is when the pass gates conduct.
  So clk0 low turns 32 precharge FETs off *and* 198 gates on, and only the first half was ever
  checked. **All three firmwares park `clk0` low on the strength of that half-trace.**
  **Unresolved, and left standing rather than explained away:** undriven, `clk0` sits at 0.77 V —
  below the 0.8 V threshold, logically identical to ground — and the board draws 0.24 A; driving the
  same pin to ground is fatal. Eliminated: the Mac cutting the port (no overcurrent in the logs), a
  pin-mapping error (GP22 → pin 29 → `clk0`, all 26 signals on real GPIOs), a short (the 9.5 k/8 k
  readings are diode paths). **Withdrawn: my claim that 1 ms was too fast for a sagging rail** — the
  Pico's ~10 µF of VSYS bulk collapses in microseconds at 2.5 A.
  **Next, and it needs clips rather than firmware:** flash `usbonly` (touches no pin), then move
  `clk0` by hand — a clip to VSS and a 10 k to VCC — and read the ammeter. If a hard clip to VSS
  draws 2.5 A then **park-low is backwards and must be inverted everywhere**.
  **Also measured:** the 16 un-reworked precharge sites contend **14.7–16.0%** under real code
  (`tools/contention_duty.py --halves 600`) ≈ **0.65 A**, mapped in
  `docs/rework-precharge-marked.jpg`; **the 31 kΩ pull-down the user fitted is too weak and the
  47 kΩ I recommended would have been worse** (25–57 µA is sourced into that node — 4.7 kΩ is right);
  and the **asymmetric clock did not save it**, because the brownout is peak-limited, not average.
  **New tooling:** `tools/pico_flash.py` flashes via the 1200-baud touch, so the BOOTSEL button —
  awkward because pin 39 ties VSYS to board VCC — is never needed again.
  **Repo restructure the same day:** `project-plan.md` 158 KB → 41 KB, history moved verbatim into
  `cards/bring-up-log.md`, `cards/build-log.md`, `cards/fab-order.md`, `cards/driver-contention.md`
  and `cards/decision-log.md`, each with a trigger in `CLAUDE.md`. **Append new handoff entries
  here, not to those logs.**

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
| [`cards/decision-log.md`](cards/decision-log.md) | The long Decisions entries, verbatim | a condensed decision above is not enough — you need its numbers, its method, or why it was later corrected |

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
