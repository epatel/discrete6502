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

- 2026-07-26 **[M6, settled]** The bring-up acceptance test is **Klaus Dormann's `6502_65C02_functional_tests`** (GPLv3, found via 6502.org's Tools → Emulators page) — the standard suite for 6502 *re-implementations* rather than emulators. Checked against our constraints before adopting: with its stock configuration (`zero_page = $0A`, `data_segment = $200`, `code_segment = $400`, 13.1 kB) the image ends ≈ `$3800`, so it fits the 16 KB mirrored window with the reset vector at `$3FFC` clear — **the ab14/ab15 sacrifice does not block it**, and the suite's own `ram_top` option offers `$40 = 16k` as a mirrored-system preset. It has no I/O, so `pico-controller/common/functest.c` reads its two side channels off the bus: writes to `test_case` ($0200) as live progress, and a repeated opcode-fetch address (branch-to-self) as the verdict — pass and fail are both self-loops, distinguished by the address in the assembly listing. Runtime is order 10⁷–10⁸ cycles ⇒ an overnight run at 10–20 kHz; run `6502_decimal_test.a65` first (decimal mode comes free from the netlist and is what emulators most often get wrong). One gotcha: the suite's own RES vector points at `res_trap`, so `$3FFC/D` must be patched to `$0400` after loading.

- 2026-07-25 **[user decision, at order]** Core FET switched to **BSS138K, LCSC C504052** (JSCJ, SOT-323) — 2N7002W (C139444) not in JLCPCB inventory. BSS138 was the designated fallback since M2 and is SPICE-validated; Vth 0.8–1.5V improves 3.3V-bring-up margins. Same package/pinout; netlist, generator, and BOM updated (datasheet reviewed: 27pF Ciss, 50V, standard G/S/D). BOM also re-chunked to ≤2000-char designator cells (JLC upload limit).
- 2026-07-25 **[user decision]** The 26 Pico GPIO series resistors (1k 0402, C11702 basic) are now POPULATED in the factory assembly (was DNP) — prepares every board for the aftermarket Pico with zero hand-soldering of passives; cost ≈ +$0.30/board. Only the Pico module itself remains aftermarket. Changed consistently in gen_netlist.py, netlist.json, and all three board files; parity re-verified.
- 2026-07-24 **[locked, user decision]** Board goes **6-layer**: F.Cu(sig-H) / In1(GND) / In2(sig-V) / In3(sig-H) / In4(VCC) / B.Cu(sig-V). Rationale: 2 signal layers bottom out at ~36 conflicted nets across two independent 24h negotiation runs (a genuine capacity floor at 0.127 rules); 6 layers resolves with certainty for ≈ +$40–70 per assembled CPU at qty 5 (accepted). Implementation: layer-surgery on the presignal snapshot (VCC zone In2→In4) preserving all placement/power work; router generalized to 4 routing layers.
- 2026-07-22 **[user intent confirmed]** The Pico 2 W site's purpose is to DRIVE the 6502: clock master + memory emulator (serve reads / capture writes each cycle). GPIO budget (26) forced dropping ab14/ab15 → the Pico sees memory mirrored every 16 KB (reset vector $FFFC appears as $3FFC — fine for all planned test programs). Kept instead: res (controlled reset) + sync (instruction-boundary tracing). Dynamic logic ⇒ no indefinite clock-stop; single-step = burst-to-sync + brief pause. Full-address remap (trade res/sync) is a one-line gen_netlist change if ever needed.

- 2026-07-25: **M5 COMPLETE — board fully routed, electrically DRC-clean.** Final pipeline (order matters): gen_netlist → gen_pcb → route_power → route_power_finish (on snapshot!) → [6-layer surgery: In2/In3 signal, VCC→In4] → route_nc (G=0.13, 4 routing layers, warm-startable hist) → fix_same_net_vias → fix_via_pairs → check_gaps + check_parity + DRC. Final finishing insights: (a) emission stubs must stay INSIDE own pad copper (goal cells shrunk 0.1) — pad-edge stubs grazed power vias (154 violations); (b) net-carve must never release non-pad copper cells (hard-mask filter) — over-carve let tracks hug stitch vias (351 violations); (c) last 8 via-via pairs = sub-cell alignment, fixed by exact-geometry nudges ≤1.3mm (`tools/fix_via_pairs.py`). Renders refreshed. Next: JLC fab outputs (gerbers/BOM/CPL), verify 2N7002W LCSC part + FET stock (~27k needed for 5 assembled), real quote (6L large-format), review 146 silk-on-pad labels (intentional) before order.

- 2026-07-25: **M6 prep started — Pico firmware scaffolded** in `pico-controller/` (`common/` shared bus engine — clock master, 16KB mirrored memory serving, trace ring, reset ceremony; `tester/` interactive bring-up CLI; `general/` free-runner with `$3F00` char-out port). Builds against pico-sdk 2.x (`PICO_BOARD=pico2_w`), untested until hardware exists. **Open question (resolve before power-up): 3.3V Pico vs 5V core levels** — inputs are practically safe through the 1k series resistors. **Verified: the board has NO pull-up on clk0** (only 100R protection + pico series R), so the clock must be driven push-pull; open-drain would leave clk0 floating unless an external 10k is croc-clipped Φ0→VCC. **Corrected 2026-07-25:** the earlier claim that a 3.3V clock under-drives the pass-pair bootstrap was wrong — clk0 gates only two pull-downs, and the internal phases (cclk/cp1) are regenerated on-board at full VCC swing; simulated, a 3.3V clk0 into a 5V core is functionally identical to a 5V one (1.7mV low, 17ns delay). The external pull-up is optional polish, not a requirement. Recommended first bring-up: whole CPU at VCC=3.3V (single domain, logic smoke test) — SPICE the pass-pair at 3.3V before boards arrive.

## Current state / handoff

- 2026-07-28 (later): **THE ORDER IS PLACED AND PAID — M6 has officially started.** 5 PCBs
  (6-layer ENIG, 5–6 days) + 4 of them assembled (Standard PCBA, both sides, 3–4 days +1 for
  depaneling). €775.88 paid,
  ≈ €973 landed, **est. ship 2026-08-06**. Full breakdown in "Cost — AS ORDERED".
  The order entry was reviewed setting-by-setting before payment and two things were fixed:
  **depaneling was off** (JLC's own banner was nudging for it) — measured against the golden
  board, the nearest SMD joint to a rail break line is **8.55 mm and 130 pads sit within 10 mm**,
  all of them MLCCs, the parts most prone to invisible flex cracking, so €2.60 and one build day
  buys away the risk of hand-snapping four populated boards; and **the PCB Remark was empty**, now
  carrying the stackup in words as a third guard on inner-layer order alongside the `.g1`–`.g4`
  extensions and the `.gbrjob`. That guard matters because an In1/In4 swap produces a board that
  looks entirely normal while every stitching via lands on the wrong plane — one of the two
  faults (with SOT-323 rotation) that would take out all four boards at once. The JLCPCB
  order and job numbers are kept OUT of this repo on purpose — git history is permanent and the
  repo is pushed, so an identifier committed once cannot be redacted later; they live in the
  gitignored `gen/fab/ORDER.local.md`. Verified before
  payment: 6L/300.7 × 322 (290.7 + 2 × 5 mm rails), qty 5 PCB / 4 PCBA, Epoxy Filled & Capped at
  €0.00, 0.3 mm via class, Standard PCBA + Both Sides, Parts Selection **By Customer** (so
  C504052 cannot be substituted), Confirm Parts Placement Yes + the rotation note, Confirm
  Production file Yes (€0.91), Remove Mark, antistatic packaging; BOM **22/22 rows confirmed**
  (our 9 line items re-chunked) with every quantity reconciling to per-board × 4 plus attrition,
  including **BSS138W C504052 at 16,234**. User checked the Gerber Viewer independently: layer
  order OK. Two non-issues chased down and dismissed: the cart's missing PCBA thumbnail (a
  missing asset — the quote page's assembly previews render and the price is computed from the
  parsed BOM), and an apparent price jump at checkout (a EUR→USD display switch; both line items
  convert at exactly 1.1390 and the €8.78 coupon is a flat $10). **Next: the production-file
  confirmation** — check that inner layers 2 and 5 are the solid planes — then receiving, and
  bring-up per the sequence in `pico-controller/README.md`.

- 2026-07-28: **Bring-up sequence restructured, and the 3.3 V-first plan dropped** — documentation
  only, no design or firmware files touched. Three findings, each checked rather than assumed.
  (a) **The Pico site is DNP**, so the delivered boards have no 3.3 V part on them at all: the
  first two bring-up steps (VCC-VSS resistance, then board-alone current draw at 5 V against the
  0.35 A prediction) have no logic-level question at any rail, which is exactly what the 3.3 V
  step was invented to provide. What protects a mis-assembled board is the bench supply's current
  limit, not a lower rail. (b) **3.3 V is the tighter operating point, not the safer one**: the
  clock ceiling halves (20 → 10 kHz) *and* the retention floor rises (leakage budget 53 → 27 nA
  per FET), narrowing the usable window from ~50x to ~13x, so a failure at 3.3 V cannot be
  attributed to assembly versus margin without going to 5 V anyway. (c) **"Leave pin 39
  unsoldered" was not a safe instruction**: the `RaspberryPi_Pico_W_SMD` pads are 3.2 x 1.6 mm and
  run *under* the module, so an unsoldered castellation is two flat copper faces held apart only
  by the adjacent joints' uncontrolled standoff — an intermittent contact, and a rail that makes
  and breaks corrupts every dynamic node at once. Pin 39 is now always soldered (which also
  removes the 5 V power-up sequencing question, since VSYS and board VCC become one node), and
  3.3 V is reached by removing the competing USB supply instead. Also documented: pins 38/39 are
  `vss`/`vcc` adjacent at 2.54 mm pitch, so a bridge there is a dead short — re-measure after
  soldering the module. `pico-controller/README.md` now carries a numbered 4-step sequence plus a
  "3.3 V operation: a fallback, not a first step" section; `cards/pass-pair-validation.md`,
  `cards/verification.md`, root `README.md` and the plan's bring-up-rail question updated to match.
  One item left unverified and marked as such: whether the RP2350 enumerates over a data-only USB
  cable when self-powered (test on a spare Pico before relying on it for 3.3 V serial).

- 2026-07-27 (later): **The clock's LOWER bound quantified — dynamic logic has a floor as well as a ceiling.** `tools/dynamic_nodes.py` finds 456 dynamic storage nodes and identifies the worst: the special-bus bits `sb1..sb7`, one gate driven (32 pF) against **twelve** FET channels leaking them — the big nets like `cclk` (13 nF, 2 channels, 259 ms) are the safe ones. `sim/retention.sp` confirms `t = C·ΔV/I` exactly (predicted 4.625 V / 4.000 V, measured 4.62500 / 3.99875). **The decisive number: at the 20 kHz ceiling the worst node must leak < 53 nA per FET (< 27 nA at 3.3 V), or the floor rises above the ceiling and there is no working clock at all.** Typical parts are ~1 nA (≈ 378 Hz floor, ~50× margin, ~57 °C of headroom); at the 500 nA datasheet guardband the floor would be 187 kHz and the design would not run. **SPICE could not resolve the leakage and the deck says so honestly** — ngspice + BSIM3 does not converge at tens of pA (3.5 orders of movement with tolerances; the temperature control comes out non-monotonic, leakage *falling* with heat, which is impossible). So this must be **measured at bring-up**: stop the clock for N ms mid-program, restart, bisect N — which also bounds how long the tester's single-step pause may last. Added `tools/test_extract.py`, promoting the ad-hoc negative controls to a real gate-has-teeth test (clean 0/0, cut → OPEN, bridge → SHORT; all PASS); it taught two things — deleting an arbitrary track often changes nothing (neighbouring collinear segments still overlap, so the victim must be the longest), and each board edit needs its own process or the second `LoadBoard` returns a bare `SwigPyObject`.

- 2026-07-27: **Fifth gate added — reverse validation from copper** (`tools/extract_netlist.py`). Motivation, established by reading the existing checkers rather than assuming: `check_parity` compares pad net *labels* to the netlist and `check_gaps` groups copper **by KiCad's net codes** before testing connectivity — and `check_gaps` never touches zones, so the GND/VCC planes were covered only by KiCad's own unconnected count. The new tool discards every net label and unions copper geometrically (pads, tracks, vias, **zone fills**, exact `SHAPE::Collide`), then reports LVS in both directions and emits `gen/extracted_netlist.json`, which `switchsim.py` simulates as a third netlist. Golden board: **2,639 conductors, 0 opens, 0 shorts, 0 unmapped pads**, 4,051 FETs recovered, VCC rail derived from copper alone (1,078 resistor pads) agreeing with the zone labels, and the extracted netlist matches the original visual6502 trace for half-cycles 28..219 with the test program passing. **Proven able to fail:** cutting one 2.6 mm track → exactly 1 OPEN naming `dpc2_XSB`; bridging two pads → 1 SHORT naming `cp1 + pipeT4out + vss`, a three-way short traced through a stitching via into the ground plane — the transitive path no forward gate can see. Three traps documented in `cards/verification.md`: KiCad copper layer IDs are not in stack order (via spans must be sliced from `CuStack()`, not a numeric range — cost 1,153 phantom opens), `board.Zones()` returns fresh wrappers so `id(z)` keys match only by address reuse (silently dropped a whole plane), and a non-golden board argument must not overwrite the canonical artifact. Limits stated in the card: pad→terminal mapping and component values remain unprovable from copper, so this proves topology, not values. No board or fab files changed.

- 2026-07-26 (latest): **Third firmware added: `pico-controller/wifi/` — browser control panel.** Motivated by the functional test being an hours-long run at 10–20 kHz, which is no way to work from a tethered terminal. Feasibility was measured, not assumed: the CYW43 uses GP23/24/25/29, which on the W are internal to the module and never brought out to castellations, so **no pin conflict with our 26 GPIOs is even possible**, and the layout already gives the antenna strip an all-layer keepout. Built and measured: **342 KB flash / 92 KB RAM** (8% of flash, 18% of SRAM; two thirds of the flash is the fixed `w43439A0` radio blob), leaving ~430 KB RAM free. **The load-bearing design decision is the core split** — bus engine alone on core 1, WiFi/lwIP/HTTP on core 0 — because this is dynamic logic where a stretched clock phase is a correctness bug, and association/DHCP block for milliseconds. Same reasoning forced `functest_set_quiet()`: pico `stdio_usb` blocks up to 500 ms when a terminal is attached but not draining, which on core 1 would stretch a 50 µs phase ten-thousandfold. Serves a dependency-free page from flash (upload Intel hex, run/stop/step/reset, clock, watcher, live bus + test progress); memory-touching operations return `409` while the CPU runs. Credentials are build-time cmake vars with no defaults so they cannot be committed. Also refactored: the Intel hex parser moved to `common/ihex.c` and is now shared with the tester. All three firmwares rebuilt clean (tester 37.6 KB, general, wifi). **Untested against hardware; the wifi path is additionally untested against a real network.** Two physical caveats recorded in the firmware README: range will be same-room only (antenna at the edge of a large ground structure), and USB-only demo mode plus WiFi approaches ~0.9 A worst case.

- 2026-07-26 (later): **Bring-up acceptance test chosen and the firmware taught to run it.** 6502.org's Tools → Emulators page carries a "6502 Test Programs (for Emulators and Re-implementations)" section; Klaus Dormann's suite there is the right acceptance test for this board and — checked against the source, not assumed — fits the 16 KB mirrored window (details in Decisions). Firmware changes — **both firmwares now actually compiled** (pico-sdk 2.1.1, `PICO_BOARD=pico2_w`, arm-none-eabi-gcc: `tester.uf2` 74 KB, 37 KB text / 32 KB bss; `general.uf2` 45 KB; zero warnings from our sources), still untested against hardware: `bus6502` gained an optional per-cycle watcher (`bus_set_watch`) that can stop a long run early plus `bus_aborted()`; new `common/functest.c/.h` narrates a functional-test run from the bus alone (progress from `test_case` writes, verdict from a repeated opcode-fetch address); the tester CLI gained `L` (paste an Intel hex image — the suite assembles straight to Intel hex), `k` (watcher on/off/address) and `g` (free-run until a self-loop, chunked with keypress interrupt and a cycle heartbeat). `pico-controller/README.md` documents the whole run recipe including the `m 3FFC 00 04` vector patch. No board or fab files touched.

- 2026-07-26: **FAB PACKAGE REV A RELEASED — the design is done.** `gen/fab/RELEASE.md` pins the release: sha256 fingerprints of the three upload files, the full board spec, the verification results and the order settings. The zip was byte-compared against a fresh plot of the golden board (15/15 files identical bar timestamps), so what is on disk is what the board is. All four gates re-run against this exact board: switchsim PASS, parity 5,421/0 errors, check_gaps 0 broken, DRC 2 benign Pico-library errors + 0 unconnected (plus 199 same-net hole_to_hole warnings at a 0.22 mm gap, inside JLC's 0.20 mm minimum). Three things changed since the first package a day earlier: the FET became BSS138K/C504052, the silkscreen was re-placed so no text crosses pad copper (the fab subtracts pad openings — titles were printing half-eaten), and the vias were re-worked onto JLC's free 0.3 mm drill class with pads grown to keep the annular ring (≈ €25 saved). **Remaining before M6 proper: place the order.** Re-upload the new zip, keep the default 0.3 mm via class, keep Epoxy Filled & Capped (free at 6 layers, and required — 3,817 vias sit inside SMD pads), set Confirm Parts Placement and send the rotation note.

- 2026-07-26: **Vias re-worked to use JLCPCB's free 0.3 mm drill class** (`tools/enlarge_vias.py`, user's idea — "identify the breakers and see if a nudge is enough"). The 0.2 mm class costs ≈ €25; drilling our 0.45 mm pads at 0.3 mm would have cut the annular ring to 0.075 mm, so instead every via now drills 0.30 mm with its pad grown to keep the ring: **13,028 at 0.125 mm, 534 at 0.11 mm, 892 at 0.075 mm** (JLC pair a 0.3 mm hole with a 0.4 mm via = 0.05 mm ring, so all are inside capability). Only 5 vias needed moving; 1,421 resolved by taking one size down in place. Verified: parity 5,421/0, check_gaps 0 broken, DRC 2 errors (the Pico pair) + 199 same-net hole_to_hole warnings at a 0.22 mm gap, 0 unconnected. Two checker bugs were caught by DRC before shipping and are now documented in `cards/layout.md`: segments indexed only at their endpoints are invisible to a via beside their middle (45 clearance errors + 5 shorts on the first attempt), and a via inside a same-net pad is that pad's only link to the plane so it must never be moved (broke one vss pad). `min_via_annular_width` relaxed 0.1 → 0.075 to match the fab.

- 2026-07-25 (power-budget audit): **Two real corrections found by re-deriving the numbers from `gen/netlist.json` instead of from memory.** (a) The README's LED row said 75 mW where 55 LEDs at 1.42 mA is 0.39 W — board total at 5 V is ~1.6 W typical / 3.2 W absolute worst case (all 1,023 pull-ups low, all LEDs lit), not ~1.45 W; a 5 V/1 A supply still covers it. The budget now separates typical from worst case and includes the Pico's ~0.12 W when VSYS is soldered. (b) **The ≥50 kHz clock target is not achievable**: the M2 speed rule assumed one gate per node, but the decode-PLA input lines drive up to 71 discrete gates (~1.9 nF) behind a single 10k pull-up. `sim/fanout_speed.sp` measures 7 µs at 5 V / 11.4 µs at 3.3 V just to flip the receiving stage, ~25 µs to a comfortable level — so realistic operation is **~20 kHz at 5 V, ~10 kHz at 3.3 V**. Firmware default changed from a 10 µs to a 50 µs half-period; `p` walks it up so the true ceiling gets measured at bring-up. The big clock nets (`cclk` 13 nF, `cp1` 5.4 nF) are unaffected — the transform gave them FET pull-ups, not resistors.

- 2026-07-25 (later): **3.3 V pass-pair validation done** — `sim/passpair_33v.sp` added and run. The clock-edge bootstrap survives the lower rail (stored '1' still lands slightly *above* VCC at 3.3 V and even 3.0 V), the next stage is fully driven, source-driven '0' through a pass pair reaches −1.1 V, and 10k pull-up recovery slows only 19% (1.31 µs — 7x margin inside a 50 kHz half-cycle). BSS138K's lower Vth makes it the better case, not the risk. Known floating-island-'0' limitation is unchanged (not a 3.3 V regression). Only cosmetic consequence: register LEDs run 0.67 mA instead of 1.42 mA (`sim/led_tap.sp`) — 47% of the current, ~78% of the perceived brightness. That deck also corrected the README power budget: the LED row was stated as 75 mW when 55 LEDs at 1.42 mA is 0.39 W, so the board total at 5 V is ~1.6-1.8 W, not ~1.45 W (the current figure, ~0.3 A, was right). **The recommended first power-up at 3.3 V is now simulation-cleared**; the remaining bring-up unknowns are physical (assembly quality, clk0 pull-up choice at 5 V).

- 2026-07-25 (late): **Agent-file audit.** Added a standing "keep the agent files current" rule to `CLAUDE.md` and swept every card for facts the last month of work had made stale: board outline corrected to the real 290.7 × 322 mm (was 283 × 309.6), core FET updated to BSS138K/C504052 everywhere, the router description updated to the shipped configuration (G=0.13 fine grid, 4 routing layers, warm-startable history), the full as-ordered BOM table added to `cards/netlist-pipeline.md`, silk + fab-output documentation added to `cards/layout.md`, the M5 "remaining work" list replaced by the M5-complete verification results, and the M2 part/board-size paragraphs in `cards/pass-pair-validation.md` explicitly marked superseded. `pico-controller/README.md` added to the card trigger list. Open questions pruned to live items only; cost section replaced with the real quote. **No design or board files were touched** — documentation only; the golden board and fab package are unchanged.

- 2026-07-18: Project initialized from `initial-idea.md`; agentic setup created (this plan, `cards/`, `CLAUDE.md`, project skills).
- 2026-07-18: M1 research complete. visual6502 netlist in `data/visual6502/` (3,510 transistors → 3,239 unique; 1,018 pull-up nodes; 783 pass transistors needing body-effect treatment). MOnSter 6502 facts and our simplification divergences documented in `cards/monster6502-lessons.md`.
- 2026-07-19 (routing saga, in progress): Freerouting abandoned (10h → 700/8,500 routed). Custom router built: `tools/route_signals.py` — per-net tree growth, multi-goal A*, 2 layers (F horiz / B vert), 0.15/0.15 rules. **Critical lesson: a tree-poisoning bug (failed pads still seeded the net tree) produced fake 100%-routed claims for several iterations — verify with `tools/check_gaps.py` (independent union-find connectivity), never trust the router's own count alone.** Honest state: greedy saturates — v12 (0.25mm+halo) 46%, v13 (0.3mm halo-free) 53% — congestion collapse, not capacity. Stage 2 built: **negotiated-congestion (PathFinder) router** — `tools/route_nc.py` (extract/emit) + `tools/route_nc.c` (C core: route through conflicts, penalize shared cells, rip-up/reroute conflicted nets until no cell shared); ~1s per full iteration vs 3h in Python. 2026-07-20 progression (each step documented in `cards/layout.md`): retune (soft pres cap + strong history) 980→750 conflicted nets; whole-net carve + real keepout zones: 14→4 hard fails; **rasterize diagonal tracks** (bbox marking over-blocked hugely) 750→149; **switch to 0.127/0.127 5-mil rules on 0.26mm grid** (JLC-capable) big drop; **skip paste-only pads** (Pico anchors were phantom obstacles) → 0 hard fails, all 8,421 connections routable. Coarse 0.26 grid plateaus at ~50 conflicted nets (31 micro-knots, quantization artifacts; grid-offset re-thread of ripped nets made it WORSE — frozen board + shifted lattice ≈ no corridors). **Fine grid G=0.13 (SCALE=2 body/halo stamping in C) breaks the plateau**: 76 conflicted at iter 2000 and still declining. 2026-07-21: power stitching completed to 100% by `tools/route_power_finish.py` run against the presignal snapshot (119 leftover pads; MUST run before signal routing — after, signal copper makes ~14 unfixable). Production run: fine grid on stitched snapshot, 8000 iters, in progress. Then: check_gaps + check_parity + DRC, renders, fab outputs. Pipeline: gen_pcb → route_power → snapshot `gen/board_presignal.kicad_pcb` (restore this before each router rerun!) → route_signals → DRC + check_gaps + check_parity. Known cosmetic leftovers: 2 Pico-internal DRC items, silk_over_copper ~146 (bond-pad labels), hole_to_hole ~14 to review before fab.
- 2026-07-19: **Layout redesigned around die mimicry and user-approved** (iterated live via HTML preview + comment loop). Board now 283×309.6mm ("30cm class", die aspect): front = only SOT-323 FETs (2N7002W — part swap from SOT-23 2N7002) + inline LEDs at die-true positions (~36% occupancy, die texture self-reproduces), 11.6mm die-scaled THT bond-pad ring with croc-clip holes, all passives on back, unpopulated Pico 2 W site (SMD) + DNP GPIO series resistors behind the die gap. Netlist equivalence still green. Power: planes + ~3,700 stitch vias (two-tier placer), DRC clean (2 benign Pico-internal items). Freerouting running on signals. See `cards/layout.md` for v6 rules. Supersedes the 2026-07-18 200×250 checkerboard design (its lessons remain in the card). Cost note: bigger PCB ≈ +$60-80/assembled board vs old estimate.
- 2026-07-18 (later): M5 layout rework + power routing complete. Netlist gained a 36-pad edge ring (die-mimicry directive). Placement checkerboards FETs across both faces (single-face packing proved unroutable — Freerouting routed 0 nets). Power distribution fully scripted (`tools/route_power.py`): inner GND/VCC planes + ~3,830 stitching vias via a per-cell site scheme; **DRC zero violations**. Freerouting (headless, OpenJDK, jar in scratchpad) running on the ~8,450 signal airwires. Next: import `.ses`, DRC, board-vs-netlist parity, re-render, fab outputs. All geometry rules documented in `cards/layout.md` — read it before touching placement.
- 2026-07-18: M5 placement complete. Netlist extended with periphery (120+4 decoupling/bulk caps, 56 DNP ballast caps on internal buses, series-R + dual-diode protection on res/irq/nmi/rdy/so/clk0, J1 40-pin header in DIP-40 pin order) — equivalence gate still green. KiCad 10 installed; `tools/gen_pcb.py` places all 5,378 parts (FETs on front at scaled die coordinates, R/C on back), 200×250mm, DRC zero violations. Renders: `gen/board_top.png` / `gen/board_bottom.png`. Next: routing (power planes + via stitching, scripted Manhattan or Freerouting for ~2,500 signal nets, clock trees first), then board-vs-netlist parity check and JLC fab outputs — see `cards/layout.md` item list.
- 2026-07-18: M4 complete. (a) Switch-level sim proves the transformed netlist behaviorally identical to the original visual6502 netlist — same traces, same correct execution of a stack/JSR/ADC/branch test program. (b) onsemi BSIM3v3 2N7002 model confirms pass pairs analog-correct for all source-driven transfers (incl. 4-FET series chains, '1'≈5.1V bootstrap-assisted, '0' clean); the only failing pattern — '0' between two floating islands via clock-edge charge injection — is one the 6502's precharge-high design never relies on. Layout insurance: DNP ballast-cap footprints on main buses (open question). Next: M5 — install KiCad, import `gen/discrete6502.net`, scripted placement (functional-block clustering from netlist `origin` fields), routing strategy, DRC vs. `cards/jlcpcb-constraints.md`, plus connector/power-entry/input-protection design.
- 2026-07-18: M3 complete. KiCad chosen as EDA target (netlist-direct-to-pcbnew, scripted placement in M5; no hand schematic). `tools/gen_netlist.py` transforms visual6502 data → 5,179 components / 2,587 nets / 5 part numbers, all JLCPCB basic class, with LED taps included; invariant checks pass (`cards/netlist-pipeline.md`). Next: M4 — behavioral verification: export the transformed netlist to a simulator (perfect6502-style switch-level sim or SPICE subcircuits with vendor 2N7002 models), run real 6502 test programs, compare against visual6502 golden model; re-verify the bootstrap-dependent pass pairs with manufacturer models.
- 2026-07-18: M2 complete. Dynamic latch with back-to-back pass-FET pair SPICE-validated for BSS138/2N7002/AO3400 (`sim/passpair_latch.sp`); clock-edge bootstrap over-charges stored '1' above VDD, eliminating threshold drop — but must be re-verified with manufacturer SPICE models and on more topologies (series pass chains, clock drivers) in M4. AO3400A rejected (1nF Ciss too slow with 10k pull-ups). Parts, voltages, and board target settled (see Decisions). Next: M3 — pick EDA tool (KiCad assumed) and build the scripted netlist→schematic/placement pipeline from `data/visual6502/transdefs.js` (dedup 271 parallel transistors, expand 783 pass FETs to pairs, emit pull-up resistors from segdefs '+' flags).

## Cost — AS ORDERED (paid 2026-07-28)

| Line | | |
|---|---|---|
| PCB, 5 pcs, 6-layer ENIG, build 5–6 days | €131.38 | $149.64 |
| — invoiced as 1 bare board @ €26.28 + 4 boards that go on to assembly | | |
| PCBA, 4 pcs, Standard, both sides, build 3–4 days +1 | €593.93 | $676.46 |
| — invoiced as 4 populated boards @ **€174.76** each (€699.04) | | |
| **Merchandise** | **€725.32** | **$826.10** |
| Shipping, UPS Worldwide Express Saver, 4.84 kg | €59.34 | $67.59 |
| Coupon | −€8.78 | −$10.00 |
| **Paid at checkout** (2026-07-28 18:39:59, status Paid) | **€775.88** | **$883.69** |
| Depaneling the two 5 mm edge rails — priced at "advanced option review finished", **paid separately 2026-07-29** | €2.60 | $2.96 |
| **Total paid to JLCPCB** | **€778.48** | **$886.65** |
| Swedish import VAT (25% of €778.48 goods + freight, billed by UPS) | ≈ €195 | |
| UPS customs clearance / disbursement fee | a few hundred SEK | |

Advanced options are excluded from the checkout total by design and invoiced after JLC's review,
so the order was paid in **two** transactions ($883.69 then $2.96) which sum exactly to the
$886.65 order total — not a double charge. The coupon also moved from its own discount line onto
the PCBA line item at that point, which is why the PCBA figure drops $10 without the order
getting cheaper.

**Personal purchase, no VAT number** [user, 2026-07-28] — the blank `VAT No:` on the invoice
is correct and intentional. The import VAT is a final cost, not reclaimable; do not raise this
again when the UPS clearance bill arrives.
| **Landed total** | **≈ €973** (≈ **€243 per assembled CPU**) | |

Shipping is **UPS Worldwide Express Saver** and the incoterm is **CPT** (carriage paid by JLC, import VAT borne by us) — both read off the commercial invoice, which is the authority; the cart panel's carrier label is clipped and easy to misread. JLCPCB's order page shows merchandise net of the coupon ($826.10 - $10.00 = $816.10, plus
$67.59 shipping = $883.69). JLCPCB's native currency is USD; the coupon is a flat $10 shown as €8.78, and both line items
convert at exactly 1.1390. Against the 2026-07-26 quote the order came in **€3.59 cheaper**
(merchandise €725.32 vs €728.88). Component cost is €404.20 for 9 items = **€101.05 of parts
per assembled board**.

Two settings changed between the quote and the order, both reviewed 2026-07-28:
**depaneling switched ON** (€2.60, +1 build day — the golden board has 130 MLCC joints within
10 mm of the break lines and ceramics are the parts most prone to flex cracking, so
hand-snapping four populated boards was not worth €2.60), and the previously empty **PCB Remark
now carries the stackup** (`6-layer stackup top to bottom: F_Cu, In1 GND plane, In2 sig, In3
sig, In4 VCC plane, B_Cu. Gerber ext .g1-.g4 = inner 1-4. Inner layer order is critical, do NOT
reorder.`, 169/200 chars).

## Cost (quote on the rev A upload, verified 2026-07-26 — superseded by the table above)

JLCPCB quote for **5 PCBs, 4 of them assembled** (6-layer, 290.7 × 322 mm ≈ 9.4 dm², ENIG,
Standard PCBA both sides — *Economic offers no double-sided* — 5,328 placements each).
**[user decision 2026-07-26]** the fifth board stays bare: the die artwork with no parts on
it photographs far better than a populated board, and it is a free spare.

| Item | Cost |
|---|---|
| **PCB fab, 5 pcs, 6-layer ENIG** — engineering €28.99, large size €22.84, surface finish €24.24, board €54.46, confirm production file €0.91 | **€131.44** |
| **PCBA, both sides, 4 boards** | **€597.44** |
| Shipping (UPS Worldwide Express Saver to Sweden; 4.84 kg) | €59.37 |
| Coupon | −€8.78 |
| **Cart subtotal** | **€779.47** |
| Depaneling the two 5 mm edge rails (billed after engineering review) | €2.88 |
| Swedish import VAT (25% of goods + freight) | ≈ €195.59 |
| **Landed total** | **≈ €978** (≈ **€245 per assembled CPU**) |

Assembly does not scale linearly — setup €44.90 + stencil €14.42 + feeders €12.10 are
one-time. At 5 assembled the PCBA line was €715.83 (€143.17/board; components 9 items
€509.20, SMT assembly €84.28, large size €50.47, packaging €0.46); at 4 it is €597.44
(€149.36/board). So dropping the fifth **saves €118.39 and costs €6.19 more per CPU** —
worth it when that board's job is to be looked at. Note the bare board will probably arrive
with its edge rails still attached, since depaneling is a PCBA-side option; snapping them off
a board with no solder joints on it is safe by hand.

Verified line-by-line against the rev A upload: via covering **€0.00** (Epoxy Filled & Capped
is free at 6 layers) and there is no via-hole-class line item at all, which confirms the
default 0.3 mm class carries no surcharge — the ≈ €25 for the 0.2 mm class was an *avoided*
cost, not a reduction. Parts dominate assembly — €509.20 of the 5-board quote's €715.83 was
components, i.e. **€101.84 of parts per assembled board** (the 4-board line item is not broken
down in the cart, but the per-board parts cost does not change). Free build
times selected: PCB 5–6 days, assembly 3–4 days (2–3 days would add €43.27). The design
changes since the 2026-07-25 cart (BSS138K, silk re-place, 0.3 mm vias) moved the total by
**€0.55**.

Cart as built (upload `discrete6502_gerbers_Y6`, not yet paid): PCB `Y6-2923600A`,
Standard PCBA `SMT026072660664-29…`, both line items checked, estimated ship **2026-08-04**.

(The 2026-07-18 preliminary estimate of ~$180–210/CPU assumed a 200×250 mm 4-layer board;
the die-mimicry directive and the 6-layer decision account for the difference.)

## Expected fab yield (estimate recorded 2026-07-28, before the boards arrive)

Not a JLCPCB-specific figure — published industry DPMO ranges applied to this board's real
joint count. Per assembled board (`gen/netlist.json`): **5,328 placements, ~14,700 solder
joints**, of which 12,153 are the 4,051 FETs × 3 pins. **The netlist has no redundancy** (the
271 parallel visual6502 transistors were merged), so ~95% of those joints are fatal if
defective; only the 55 LED taps and the decouplers are forgiving, and the decouplers only
against opens — a shorted decoupler is a dead rail.

P(perfect board) = e^(−joints × DPMO × 10⁻⁶):

| Assembly DPMO | Expected defects/board | P(board perfect) | P(≥1 of 4 perfect) |
|---|---|---|---|
| 10 (excellent) | 0.15 | 86% | ~100% |
| 25 (good) | 0.37 | 69% | ~99% |
| 50 (typical) | 0.74 | 48% | 93% |
| 100 (mediocre) | 1.5 | 23% | 65% |

Component-level failures add 0.1–0.5 per board (5,328 parts at 20–100 ppm for economy-brand
parts). **Central estimate: 0.5–2 defects per board.** Ordering four is what makes that
acceptable, and every FET being on the top face makes SOT-323 rework by hand realistic.

Random defects are the benign case, because they are independent across boards. The risks that
matter are **systematic and hit all four identically**:

0. ~~**Inner-layer order**~~ **CLOSED 2026-07-29 by measurement** — see "Stackup verified from
   JLC's production files" below. Kept in this list because it was one of the two all-four-boards
   failures, and because the method generalises to any future respin.
1. ~~**SOT-323 rotation**~~ **CLOSED 2026-07-30 on the DFM image** (see "Placement verified from JLC's DFM" below) — 4,051 parts from one reel. Wrong rotation is four dead boards with no
   worthwhile rework. This is why the order settings require Confirm Parts Placement plus the
   rotation note; it is the highest-value review step in the project.
2. **Via-in-pad** — 3,817 vias sit inside SMD pads, which is why Epoxy Filled & Capped is
   mandatory, not optional. Imperfect capping wicks solder down the via, giving opens and voids
   concentrated wherever the capping failed. The most design-specific risk we carry.
3. **Wrong part or value on a reel** — only 9 line items, but it is an all-boards-at-once fault.

**Density is NOT a risk factor — measured 2026-07-29, not assumed.** The intuition that 5,328
parts packed close together must raise the per-joint defect rate does not survive measurement:
across all 14,912 SMD pads, the **closest gap between pads of two different parts on different
nets is 0.955 mm** (C99/C100, the tightest pair on the board). Routine SMT handles 0.2–0.3 mm
gaps, so this board is ~4x more relaxed than ordinary work, and the parts are unremarkable
(SOT-323 is 0.65 mm pitch, 0402 is a standard chip size — nothing is fine-pitch). This is a
direct dividend of the die-mimicry directive: refusing to pack the transistors preserved the
die's empty space, so the board is physically huge but locally sparse. **Closeness is not the
risk; count is** — and count is what the DPMO model above already captures.

**Three size-driven risks the DPMO model does NOT capture**, all consequences of building on a
300 × 322 mm 6-layer board rather than of part density:

1. **Thermal mass** — six layers with two solid copper planes. A uniform reflow profile across
   that area is genuinely harder than on a small board: too little heat gives cold joints, too
   much cooks the edges. The most plausible source of a defect *cluster* rather than scattered
   singles.
2. **Warpage** — 1.6 mm thickness over a 300 mm span is a floppy ratio at reflow temperature.
   Bow can lift parts off their pads mid-profile and produce opens, typically toward the centre
   or the corners.
3. **Two reflow passes**, since assembly is double-sided — the bottom-side passives see the
   profile twice.

None of these move the 0.5–2 defects/board central estimate, but they widen the uncertainty
upward and they make defects **more likely to be clustered by region than uniformly scattered**.
That is useful at bring-up rather than merely bad news: if the functional test fails in a way
that maps onto one area of the die, suspect the process, not a random joint.

**The answer in one line: expect 2 of the 4 boards to work at first power-up** (plausibly 1–3),
**~85% chance at least one works immediately**, and **3–4 working after rework** — a
single-defect board is a repair job, not a loss, since every FET is on the top face and the
functional test localises the failure. That assumes no systematic fault: rotation or stackup
errors are all-or-nothing and give 0 of 4, which is why both were gated by explicit JLC
confirmation before production.

Bare-board risk is comparatively low: 5-mil rules and 0.3 mm drills are standard capability, and
JLC flying-probe tests every board before assembly.

**Consequence for bring-up:** Step 2 of the sequence in `pico-controller/README.md` (board-alone
current draw at 5 V against the 0.35 A prediction, before the Pico is fitted) is the
systematic-fault detector — a rotation error, a shorted decoupler or a wrong reel moves that
number grossly. Single-joint random defects will not move it; those surface as functional-test
failures, which is why the acceptance suite's per-`test_case` progress reporting matters: it
narrows 4,051 FETs to a functional block.

## Stackup verified from JLC's production files (2026-07-29)

JLC sent the PCB production package (the €0.91 "Confirm Production file" option — assembly/DFM
is a separate confirmation still pending). The check that mattered was inner-layer order, and it
was settled **by measurement, not by trusting the label**.

File sizes alone only prove that *planes* sit at L2/L5 (12.9 MB each vs 1.0 MB for L3/L4) — they
cannot tell which plane is which, and a GND/VCC swap is exactly the catastrophic case. So their
gerbers were aligned to `gen/board_routed_golden.kicad_pcb` (their CAM output is in inches, Y
flipped, +4.5 mm X offset from the 5 mm rails) and polygon vertices were counted within 0.5 mm
of the 2,501 known vss via positions and the 1,349 vcc ones. **A plane floods over vias of its
own net and cuts an antipad around foreign ones**, so the asymmetry identifies each plane with
no reference to any layer name:

| JLC layer | vertices/via near VSS | near VCC | verdict |
|---|---|---|---|
| l2 | 2.1 | **26.4** | voids at VCC vias → **GND plane** (= our In1) |
| l3 | 1.1 | 1.1 | no plane behaviour → signal (= In2) |
| l4 | 1.3 | 1.4 | no plane behaviour → signal (= In3) |
| l5 | **18.3** | 2.3 | voids at VSS vias → **VCC plane** (= our In4) |

One board-wide alignment fits all four layers; a per-layer alignment search is the trap, since
it finds spurious local optima (it put l5 at dy = −3.0 mm and halved the contrast). Alignment is
a property of the board, not of the layer.

Also confirmed in their metadata (`YG/4te.json`, GBK-encoded): `batCountRemark` records our
L1–L6 filename mapping verbatim, and the auto-appended order remark contains a Chinese
translation of our email **including the self-check** ("L2 and L5 are solid copper, L3 and L4
sparse; if L2 or L5 shows sparse traces the layer order is reversed") and the 13,000-via
rationale — the CAM engineer propagated the reasoning rather than just ticking a box. Board
parameters all match: 6 layers, FR-4, 1.6 mm, inner 0.5 oz / outer 1 oz, 300.7 × 322 mm, 沉金
(ENIG), green mask, white silk, `[不加客编]` (no customer code — the "Remove Mark" selection).

Two incidental findings: a `vcut` file is present, so **the edge rails are V-scored** (that is
what gets snapped at depaneling); and `qrCodeFlag` is true but the remark places the SMT QR and
plain code **on the process edge, both sides**, so the code lives on the rails and leaves with
them — the board itself stays unmarked.

**Lesson worth keeping:** the PCB Remark did its job, but the *proof* came from geometry. Any
future respin should re-run this vertex-density test rather than reading layer names.

**Confirmed and released 2026-07-29 — the PCB is in production.** The bare boards are now
committed; no further change to the fab data is possible. The assembly/DFM confirmation is the
remaining gate, and SOT-323 rotation is the last all-four-boards risk still open.

## Placement verified from JLC's DFM (2026-07-30)

The assembly gate, separate from the PCB one. Ground truth pulled from
`gen/board_routed_golden.kicad_pcb` first, because the useful check is whether the *pattern* of
orientations matches rather than whether one part looks plausible:

| Family | Count | Rotation | Side | Cathode = pad 1 |
|---|---|---|---|---|
| Q1–Q4051 (SOT-323) | 4,051 | **all 0°** | top | n/a (pad 1 = gate, at −0.89, −0.65 = upper-left) |
| D1–D55 (LED 0603) | 55 | all 0° | top | **−x (left)** |
| D56–D67 (SOD-323) | 12 | all 180° | **bottom** | **+x (right)** |

- **FETs ✓** Every FET is at 0°, so the DFM's uniform appearance — pin-1 marker at upper-left on
  all of them — is correct. A uniform 180° misread would have put the marker at lower-right.
  **This closes the last all-four-boards risk.**
- **LEDs ✓** Unambiguous in the top view: DFM draws the minus bar left and `+` right, matching
  cathode on −x.
- **SOD-323 ✓** Needed care, because the bottom view's mirroring was unknown and the answer flips
  with it. Resolved three ways: (a) D66/D67 are the **rightmost** of the six pairs (x = 243.1 of
  290.7) and render at the **left**, so screen-left = increasing board X, i.e. the view IS
  mirrored, making the left-hand bar the +x pad = pad 1 = cathode; (b) the cursor readout
  (X 252.36, Y 310.85) fits `Y_display = 322 − y_board` with D66/D67 at y = 9.90/12.00, so the
  coordinate mapping is confirmed; (c) **our own silk asymmetry agrees** — the SOD-323 silk spans
  −1.05..+1.61 mm, poking past the pad on the cathode side and stopping inside it on the anode
  side, and on screen the outline pokes out on the same side as their bar. Since JLC derive
  polarity from the silkscreen, (c) is their reading agreeing with our drawing.

Also confirmed: part numbers C504052 / C2286 / C2128 match the BOM, sides match the board
(FETs + LEDs top, clamp diodes bottom), and R1079 (the 100R clk0 protection resistor, y = 7.80)
renders directly above D66 as it should.

**Bounded-risk note kept for the record:** had the 12 clamp diodes been reversed, the cost was
repairable, not fatal — they would forward-conduct from the rail and hold res/irq/nmi/rdy/so/clk0
at a fixed level, obvious on first power-up and fixable by reworking or simply removing 12
back-side SOD-323s, since they are protection only and not in the signal path. That asymmetry of
consequence is why the FET rotation deserved the greater scrutiny.

**Released to production 2026-07-30.** Both systematic risks are now closed by inspection, and
what remains is the random-defect picture in "Expected fab yield": expect 2 of 4 working at first
power-up, 3–4 after rework.

## Open questions

_(design questions from M1–M4 are settled and live in Decisions; only live items remain here)_

- **Achievable clock**: simulation says ~20 kHz at 5 V / ~10 kHz at 3.3 V (PLA-line fanout,
  `sim/fanout_speed.sp`), against the M2 target of >=50 kHz. Measure the real ceiling at
  bring-up by walking the clock up with the tester's `p` command. For scale, the original
  NMOS 6502's own window was **50 kHz to 1 MHz** (datasheet-verified 2026-07-28, three-way
  comparison in `cards/monster6502-lessons.md`) — a discrete rebuild of this logic style runs
  entirely below the band the real chip was specified for, and the MOnSter's ~50 kHz ceiling
  sits on the original's *minimum*.
- **Clock floor / charge retention** (opened 2026-07-27): the worst dynamic node (`sb1..sb7`,
  32 pF against 12 leaking FET channels) must leak **< 53 nA per FET at 5 V** or the floor
  rises above the 20 kHz ceiling and nothing runs. Typical parts are ~1 nA, so ~50x margin is
  expected — but SPICE cannot resolve leakage at this level (see `cards/pass-pair-validation.md`)
  so it is unproven. **Measure at bring-up** — the tester firmware now does it: `w MS` for a
  single stall, `W [MAXMS]` to bisect the boundary automatically (runs a 0 ms control first,
  so a broken harness cannot masquerade as a retention result). Also bounds the safe
  single-step pause.
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
- **Optional LEDs**: whether to add address/data-bus (24) and IR (8) LED taps in a future
  revision — script-generated, cheap, but more parts and more routing.
- **Licensing**: `segdefs.js` is CC BY-NC-SA (noncommercial). Fine for this hobby build;
  would need clarifying before any commercial use of derived design files.
- ~~**Order status**~~ **RESOLVED 2026-07-28 — ordered and paid.**
  €775.88 at checkout, ≈ €973 landed (≈ €243 per assembled CPU). Full breakdown in the
  "Cost — AS ORDERED" table. Est. ship 2026-08-06; UPS bills the Swedish import VAT separately.
