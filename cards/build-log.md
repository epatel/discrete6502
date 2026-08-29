# build log — design, fab package and firmware (2026-07-18 … 2026-08-08)

Split out of `project-plan.md` on 2026-08-30, verbatim and unedited. Everything here predates
the boards arriving: the netlist and routing saga, the fab package, the order, and the Pico
firmware written before there was hardware to run it on. **Read it when you need to know why a
tool, a gate or a pipeline step exists**, or before changing anything in `tools/`.

Entries are newest-first, the same order they had in the plan, so a cross-reference by date
resolves here exactly as it did there. The hardware-era entries are in
[`cards/bring-up-log.md`](bring-up-log.md).

- 2026-08-08 (later): **The acceptance suite is built, validated, and passing — in an emulator, so
  the images are no longer an unknown at bring-up.** Klaus Dormann's suite is checked out as a
  sibling directory (`../6502_65C02_functional_tests`, which already carried a verified
  `BUILDING.md` recipe for running the i386 AS65 under `docker --platform linux/386`).
  `tools/build_functest.py` now drives it end to end and writes `gen/functest/` — see the two
  Decisions entries above for what it does and what it measured. **The headline: both images reach
  PASS in an emulator against a mirrored 16 KB memory**, so if the board fails the suite, the board
  is what failed. Deliberate choices worth knowing: the images are **committed** rather than
  regenerated at bring-up time, so no Docker is needed on the day; and the toolchain is checked by
  reproducing upstream's own committed binary byte-for-byte, which tests the assembler path
  independently of anything we changed. **The user's question — "add an output addr to follow their
  progress?" — turned out to be already answered by the suite and better left alone.** `test_case` at
  `$0200` is exactly that address, `functest.c` already watches it, and adding a *second* dedicated
  port would have been actively harmful: with `ram_top = $40` the RAM-integrity check checksums
  everything from the data segment up to `$3FFF`, so any I/O address inside the window is inside the
  checksum, and every address is inside the window because the Pico only decodes 14 bits. So the
  progress channel is `k 0200` for the functional test and `k 0001` (the `N2` outer counter) for the
  decimal test. Two real problems were fixed rather than documented around: the decimal test ended on
  `db $db`, a **65C02 STP that is an undefined opcode on NMOS**, and it emitted **no interrupt
  vectors**; both now produce identifiable self-loops. **Nothing on the board, in the fab package or
  in the firmware changed** — a new tool, its outputs, and documentation. Docs updated to match:
  `pico-controller/README.md` (build recipe, address table, measured runtimes replacing the
  "overnight" estimate) and `docs/bring-up.html` Step 8. **Next, unchanged: the boards.** Bring-up
  Step 1, Step 2's current reading, then the eight-site rework, then Step 6 onward — and tie `irq`
  and `nmi` high before starting a multi-hour run.

- 2026-08-08: **The bring-up procedure is now written down, and writing it exposed two soft claims
  in our own instructions.** Boards were expected to ship 2026-08-06, so this session produced the
  document that gets used when they arrive: `docs/bring-up.html`, linked from `docs/index.html`
  (live at `epatel.github.io/discrete6502/bring-up.html`). Nine steps from receiving inspection to
  the overnight functional test, each tagged with its power state, gated on a stated measurement,
  and paired with what a wrong reading means. Content is assembled from
  `pico-controller/README.md`, the "Driver contention" and "Expected fab yield" sections here, and
  the tester's own help text — no new engineering, but three decisions the sources had left
  implicit. **(a) Where the rework belongs: between the unpowered checks and the first clocked
  run.** Steps 1–2 are the only tests that catch a *systematic* assembly fault, and any such fault
  makes the rework wasted labour on four boards; everything after the Pico goes on involves
  sustained clocking, which is what makes the defect thermal. The README had **no rework step at
  all** — it now has Step 2b, numbered rather than renumbered so existing Step 3/Step 4 references
  stay valid. **(b) The 0.5 A limit is below the 0.65 A legitimate worst case**, so a healthy board
  at worst case would trip the limit and look like a fault. Both documents now say to ramp the
  voltage from zero, because *where* it folds back is the diagnostic — a bridge limits at a
  fraction of a volt, a healthy-but-high board near the top — with an escalation to 0.8 A that is
  still far below the ~1.8 A contention draws. **(c) "An unclocked board cannot contend" was
  overstated** and is now qualified: the dynamic nodes are not in a defined state on an unclocked
  board, so nothing forbids a `dor` gate and its pull-down both sitting above threshold. Operationally
  nothing changes, because the protection was always the current limit rather than the absence of
  contention — but the honest form of the claim is "sustained contention is unlikely". **Also
  settled: pre-flash the Pico before soldering it.** It can be reprogrammed in place indefinitely
  (`pico_stdio_usb/reset_interface.c` is linked, so the 1200-baud touch works and BOOTSEL is never
  needed again), but flashing once beforehand lets a bad module be rejected while rejection is still
  cheap — the footprint's pads run *under* the module — and makes first power-up a known state
  rather than merely a harmless one. Safe because **the firmware is inert at boot**: `bus_init(false)`
  then a block on `stdio_usb_connected()`, so a powered board with no terminal attached does
  nothing. One subtlety recorded in both files: `bus_init` leaves **clk0 an output driven LOW**, so a
  powered pre-programmed board sits with the clock *parked* — the stall condition, which the
  retention test creates deliberately and which contention makes dangerous. Safe in this order, and
  a reason not to move Step 2b after Step 3. Two README corrections fell out: Step 4 no longer tells
  you to flash a firmware Step 3 already flashed, and it now carries the clocked-current check and
  the "measure the retention floor after the rework, never before" rule. **Left unverified and
  marked as such:** the module mounts pads-down, so USB and BOOTSEL should face away from the PCB —
  reasoned from the footprint, not from a board in hand, and it decides how the board must be
  propped for flashing. **No design, board, fab or firmware files were touched** — documentation
  only. Incidental: `docs/index.html` has a pre-existing `<head>` tag mismatch (confirmed against
  `git show HEAD:`); it renders fine and was left alone.

- 2026-08-01 (later): **Rev B validated in SPICE — the fix holds, and the hand rework is now
  simulated rather than merely argued.** Yesterday's rev B was implemented against a green
  `switchsim` run, which `cards/verification.md` had just finished recording as *structurally
  incapable* of judging a ratio change — so the fix rested on exactly the gate that missed the bug.
  `sim/revb_driver.sp` closes that: a representative driver lifted out of `gen/netlist.json`
  (`dor1 → Q401 → n798 → Q192 → db1` — the worst-measured contender at 90% duty, carried two stages
  deep to a real chip output), simulated as rev A and rev B side by side at both rails and at
  typical and datasheet-max Vth. **Contention current 262 mA → 0.499 mA, contended level 1.86 V →
  2.9 mV, rise 18 ns → 271 ns against a 25 µs budget, fall unchanged.** Since the eight-site hand
  rework is the same topology, this validates the boards-in-flight rework too, not just a future
  respin. Three things the simulation produced that the reasoning had not: **rev B's high levels
  come out higher than rev A's** (the 10k keeps bootstrap charge that rev A's stiff VCC drain
  conducts back into the supply — probed node by node before believing it); **the 3.3 V worst-Vth
  marginality is pre-existing**, shown by adding a rev A worst-Vth chain purely so the comparison
  could not be rigged — at 3.3 V rev A's db1 stops at 1.306 V and never reaches the 1.5 V threshold
  it must drive, while rev B reaches 1.579 V; and **the one genuine caveat, the two 100R sites**
  (`cclk`, `cp1`), which dissipate 200 mW in an 0402 rated 0.0625 W while contended — harmless at
  ~4% duty, but a real limit if the clock is ever stopped with `cclk` contended, which is precisely
  what the retention test creates. Rev B does not break the clock: `cclk` keeps its level to within
  2 mV and rises 25x inside a half-cycle. Full tables in "Driver contention" below. Two measurement
  traps worth keeping: rev A's contended nodes **never reach 0.5 V**, so a rise measured from 0.5 V
  silently fails on rev A only and would have looked like rev B being the broken one; and one
  measurement in the deck is *expected* to fail (rev A worst-Vth at 3.3 V never crosses 1.5 V) — the
  failure is the finding and the deck says so, so nobody "fixes" it later. Rev A output re-verified
  byte-identical (sha256) after generating rev B. **Nothing changed on the board, the fab package
  or the firmware** — simulation and documentation only.

- 2026-08-01: **A real design defect found, measured, and fixed two ways — the boards in
  production need a hand rework before they can run.** Following yesterday's shoot-through lead
  into our own netlist turned up a genuine bug, not a scare: **the transform preserved topology
  but not device ratios.** Ratioed NMOS needs a weak load against a strong pull-down; the 1,018
  depletion loads correctly became 10k resistors, but the **164 enhancement-mode VCC-side FETs
  kept the same BSS138W as their pull-down — a 1:1 ratio.** `sim/driver_contention.sp` (new deck,
  models calibrated to the datasheet 6.0 Ω RDS(on), cross-checked against the onsemi vendor model)
  measures **262 mA and 0.90 W per contended net at 5 V**, against 220 mA and ~0.3 W ratings. Worse
  than the heat: the contended node sits at **1.0–1.9 V against a 1.1–1.5 V receiver threshold**,
  so the stage can read HIGH when it should read LOW — the CPU may write wrong data.
  `tools/switchsim.py` shows **8 nets contended 47–93% of the time** (mean 6.7 at once), all eight
  **data-bus output drivers**: `RnWstretched` holds their pull-down on through every *read* while
  the stale `dor` bit holds the pull-up on. That is **+1.76 A and +8.8 W**, taking the board to
  **≈2.1 A / ≈10.4 W against a recorded 0.32 A / 1.6 W — the budget was wrong by 6×.** The
  corroboration nobody had asked for: the MOnSter 6502 publishes 2 A / 10 W for the same logic,
  and our figure being six times cheaper had sat unexamined for two weeks.
  **What was done:** (a) the power budget corrected everywhere and every stale 0.32 A / 1.6 W /
  0.35 A figure swept — 3 A supply, USB-only not viable at 5 V; (b) a hand rework specified for the
  four boards in flight — **10k in series with eight FETs**, all on the front face in one column,
  with illustrated instructions and true-scale renders generated from the board at
  `docs/rework-dor-series-r.html`; (c) **rev B implemented in the generator**
  (`DISCRETE6502_REV_B=1`), 142 sites, sized per net, off by default and rev A byte-identical;
  (d) the **verification blind spot recorded** in `cards/verification.md` — `switchsim` resolves
  any contention as low, so it proves topology and never levels, which is exactly how this passed
  five green gates. **Two of my own errors were caught and corrected along the way** and are worth
  knowing about: the "cclk is 33 VCC-side FETs against 31 pull-downs" claim came from counting
  FETs *gated by* cclk rather than *on* it (really 1 and 1), and the intro page kept asserting the
  old 1.6 W in a summary table beside the corrected prose. **Next: nothing is blocked** — the
  boards are still in fab. When they arrive: bring-up Step 1, then the eight-site rework *before*
  any retention measurement, since the stall test is the condition the rework makes safe.

- 2026-07-31: **The clock floor's failure mode is probably worse than recorded — found by reading
  the MOnSter's designer rather than our own notes.** Asked whether the MOnSter has a clock floor;
  it does, and [TubeTime](https://tubetime.us/index.php/category/monster-6502/) describes the
  mechanism as **shoot-through**, not the charge-retention *correctness* failure this plan had
  assumed: *"if the clock slows down too much, the latch will change state, causing both pullup
  and pulldown to be turned on"*. He added protective resistors between pullup and pulldown to
  survive it, and those same resistors are what cap his ~60 kHz ceiling — the two limits are one
  component. Re-derived our exposure from `gen/netlist.json` rather than assuming symmetry: all
  **1,018 pull-ups are 10k resistors** (0.5 mA, inherently safe — structurally better than the
  MOnSter), but **266 nets carry a FET-to-FET path** with no series resistance, only 105 of them
  also having a pull-up. **Corrected 2026-08-01:** this entry first called `cclk` the worst at
  "33 VCC-side FETs against 31 pull-downs" — a bad query that counted FETs *gated by* cclk rather
  than FETs *on* it. Re-measured, **every one of the 164 nets has exactly one pull-up FET** (cclk
  included: 1 up, 1 down, 482 gates hanging off it), so no net is a near-short and each contended
  net is the same ~262 mA pair. **Consequence for bring-up: the tester's `w`/`W` commands
  deliberately create exactly this condition**, so they may damage rather than measure. It also
  re-weights earlier advice — the bench supply matters mainly because its **current limit is the
  protection**, not because of rail sag; a USB charger will push 3 A into a partially-conducting
  clock driver. Safety block added to `pico-controller/README.md` above the retention section
  (0.5 A limit, 3.3 V first, sub-ms stalls ramped, watch current). Stated honestly as a topology
  result rather than proof the overlap occurs; boards are in production so protective resistors
  are not an option and the mitigations are procedural. No board, fab or firmware code changed.

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


