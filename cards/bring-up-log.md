# bring-up log — the boards on the bench (2026-08-12 … 2026-08-26)

Split out of `project-plan.md` on 2026-08-30, verbatim and unedited, because the plan is
`@`-imported into every session and this is history rather than state. **Read it when you need to
know what a measurement on board #1 actually showed, or why a conclusion was retracted** — several
were, and the retractions are the most useful part. The newest entries stay in the plan's
"Current state / handoff"; this file holds everything from the boards arriving up to 2026-08-26.

Entries are newest-first, the same order they had in the plan, so a cross-reference of the form
"the 2026-08-24 entry" resolves by date here exactly as it did there.

- 2026-08-26 (later): **A stopped board draws 0.30 A — the passive budget, exactly as designed —
  and that retires the 1.4 A question open since 2026-08-23.** Measured with the Pico fitted and the
  clock parked: **0.30 A** against a design prediction of 0.35 A typical and a 0.548 A passive
  ceiling. **Nothing is wrong with the board at rest, and never was.** The 1.4 A that drove a
  fortnight of reasoning was measured with **no Pico on the board**, so `clk0` (which has no pull-up
  here), the data bus and reset were all *floating* — a condition that genuinely does drift the
  dynamic nodes and bias thousands of FETs near threshold, which is what the 2026-08-24 correction
  proposed. **It is simply not the condition the board runs in.** Executing, board #1 draws
  **1.70 A**, so **contention is 1.40 A**, or about **180 mA per contended net** against
  `switchsim`'s ~7.7 simultaneous — the same quantity `sim/driver_contention.sp` puts at 262 mA
  worst case. Two independent routes to one number. **Also: power-on order is worth 0.65 A**
  [user finding] — hot-plugging the VCC croc onto a live charger gave ~2.35 A; connecting both clips
  cold and energising at the charger gives 1.70 A. Keep the second, which is better practice anyway.
  **And the fluctuation is the CPU, not the instrument** — it had been written off as a meter or
  contact problem for two days, and with the clock stopped the reading is steady. A 30 s meter video
  was OCR'd (validated against five hand-read frames) and tested for the period the address counter
  would produce: **no support** (r = +0.02 at 6.5 s, −0.10 at 13.1 s, ±0.09 noise floor), though the
  *magnitude* fits — a 1.35 A swing at 180 mA/net is ~7 nets moving, the right size for the address
  bits sweeping. Left unresolved rather than argued; 30 s is two cycles of the period sought.
  **Target for the sixteen-site rework, written before it is done: executing current should fall
  from 1.70 A to roughly 0.7–0.9 A** (the `adh`/`adl` sites are ~5.2 of the 7.7 contending), with
  the stopped figure unchanged at 0.30 A. Logged as Step 6c in `docs/actual-bring-up.html`.

- 2026-08-26: **The NOP test falsified my prediction, and the board's answer was better than the
  one I asked for.** Prediction: `adh3/5/6/7` go cold under an all-NOP free-run while `adh4` gets
  hotter — a three-way split in one camera frame. **Result: every adh site stayed hot.** The cause is
  a measurement artifact I introduced. `tools/contention_duty.py` ran 300 half-cycles = 150 cycles,
  in which the PC barely moves, so **PCH sat at `$EA` for the whole simulation — and `adh` *is* PCH
  during a fetch.** A bit already high is not being pulled low and cannot contend. Re-running the
  identical measurement with the reset vector at `$0000` gives **48% on all eight**; at `$EA` the
  bits reading 0% are **exactly the bits set in `$EA`** (1,3,5,6,7). So contention here is
  **address-dependent, not workload-dependent**, and over any real run the address sweeps and every
  bit heats. **The user's own observation is the stronger result:** `adh6` and `adh7` were seen to
  stay cold about a second longer and then heat — *cycling*. PCH bit *n* toggles every 2ⁿ × 256
  instructions, so at 10 kHz `T = 2ⁿ × 512 / f` gives **3.3 s for adh6 and 6.6 s for adh7**, and
  those are the only two bits slow enough for copper's thermal mass to follow (adh0–adh4 are 50 ms
  to 0.8 s and just look warm). **This is the Step 3c program-counter ripple measurement again, in
  the thermal domain** — a better confirmation of the mechanism than the prediction it replaced.
  **Consequences:** all sixteen sites want the rework and the "some are only hot under real code"
  nuance is gone; **why the 2026-08-24 thermal sweep found nothing is UNEXPLAINED again**, since the
  workload split was the only thing reconciling it, and no replacement is offered because none has
  been earned; and any duty gate for rev B **must sweep addresses** or it will certify sites that
  contend heavily in use — the same class of error as the `has_pulldown` filter, committed a second
  time in the measurement instead of the generator. Docs swept: `tools/contention_duty.py` carries
  the caveat and labels low readings "quiet at THIS address", and `make_nop_image.py`,
  `mark_rework_adh.py`, `rework-adh-series-r.html`, `rework-dor-series-r.html`, `index.html`,
  `actual-bring-up.html` (Steps 5/6 and 6b) and `cards/rev-b-plan.md` are corrected. **The user has
  started the sixteen-site rework, which is needed regardless of the explanation.**

- 2026-08-25 (evening): **The Pico is soldered, the CPU runs a real program off it —
  and the 2026-08-24 retraction of the driver-contention model is itself retracted.**
  Board #1, Pico 2 W mounted, autorun on: **the A LEDs count**, which is Step 6 passed
  and the first time the CPU has executed from emulated memory rather than a tie-off.
  It draws **2.3 A**, against 0.7–1.2 A expected. Three independent lines now agree on
  why, and the conclusion is the opposite of the one this plan has carried for a day.
  **(a) The current is clock-independent** — the same at 500 Hz and at 10 kHz [user
  measurement]. Switching or near-threshold loss scales with rate; a `cclk`-gated
  contending pair conducts a fixed *fraction* of every cycle and does not. That single
  observation rules out the distributed explanation. **(b) The FLIR shows discrete
  spots at ~80 °C**, which is exactly what 2026-08-24 recorded as absent. **(c) New
  tool `tools/contention_duty.py`** measures, rather than assumes, how often each of
  the 164 VCC-side FETs is fighting its pull-down — `switchsim` resolves contention as
  low and is structurally blind to it, but the same model exposes it as "VCC-side FET
  on while the conduction group reaches vss". Run under two workloads it reconciles
  both thermal images: **adh1/3/5/6/7 contend 35% of the time under real code and
  0.3% under an all-NOP free-run**, and a NOP free-run through a $EA tie-off is
  precisely the condition the 2026-08-24 image was taken in. **The observation was
  sound; the generalisation drawn from it — "the excess is distributed over thousands
  of near-threshold FETs" — was not.** The 2026-08-01 model was right about the
  mechanism and was simply not being exercised.
  **The strongest positive result is that the hand rework demonstrably works**: the
  eight `dor` nets contend **91.8%** of the time under NOP free-run, i.e. through the
  whole 2026-08-24 measurement, and the camera found them **cold**. At 1:1 that would
  have been ~7 W in eight SOT-323s and impossible to miss.
  **The user's camera beat the model twice.** First by finding the spots at all.
  Then by marking `adl4`–`adl7` as among the hottest when `contention_duty.py` had
  **excluded all four before measuring them** — they have no pull-down FET sitting
  directly between the net and vss, but they are pulled low **through a pass-gate
  chain**, which contends identically. The FETs my filter did find on those nets are
  gated *by* adl4–7, i.e. loads they drive: **the same "counted FETs gated by X rather
  than on X" error already recorded against `cclk` on 2026-08-01, repeated.** The
  detector was always right — it follows conduction groups — so removing the filter
  was the whole fix, and it promoted **adl6 and adl7 to 45.7%, the two busiest sites
  on the board**, above every `adh` and every `dor`.
  **Sixteen address-path sites now want the same 10 kΩ-in-series rework** (8 `adh`,
  8 `adl`), mapped with positions, designators and neighbours in
  `docs/rework-adh-marked.jpg` (`tools/mark_rework_adh.py`). Nine are confirmed hot.
  **The 16 `ab*` output drivers measure 0.0% under both workloads and are cold on the
  camera — they do not want reworking**, despite being flagged red on the older
  `hotsites-marked.jpg`. Why the two clusters differ in temperature while barely
  differing in duty is layout, and it is quantified rather than asserted: per-part
  duty differs by 11%, but panel 2 packs nine sites into a **3.7 mm-wide column**
  against panel 1's 14.8 mm spread — **2.6x the duty per cm², and 2.8x the neighbouring
  dissipation within 12 mm**. Fixing panel 2 first should therefore gain more than the
  sum of its parts, since it removes the mutual heating too.
  **Not yet done, and it is the sharp test:** an all-NOP free-run predicts **three
  different behaviours in one camera frame** — adh3/5/6/7 go cold (35%→0.3%), adh4
  gets *hotter* (35%→48%), adl5/6/7 stay hot but ease (37–46%→22–34%). Same board,
  same framing, one variable. **Nothing on the board, in the fab package or in the
  netlist changed.** Safety: 80 °C is over the SOT-323 power rating but junction is
  ~90–110 °C against a 150 °C limit — short runs fine, **do not start the multi-hour
  functional test until the rework is done.**

- 2026-08-25 (later): **The firmware was audited, hardened against the network
  and the terminal both going away, and flashed — and asking "what happens if wifi
  does not connect?" found three real faults.** Nothing on the board, in the fab
  package or in the netlist changed; this is firmware and documentation only.
  **Measured first, because the audit turned up a claim worth checking:** the panel
  displays the clock as `1e6/(2*half)`, i.e. **nominal, never measured**. Timed over
  serial, the real rate at the 50 µs default is **9,878 Hz against 10,000 nominal —
  1.2 µs of loop overhead per cycle**, confirmed independently a second time at
  9,876 Hz. That is 1.2% at 10 kHz and ~2.4% at the 20 kHz ceiling, so **the concern
  was real but small** — I had implied it was significant and it is not, and it
  would not have corrupted the PC-ripple work (under 0.5% at 2–5 kHz). Worth
  surfacing on the panel eventually; not a blocker. **The three faults:** (a) *the
  verdict existed only in `/status`*, so a nearly-three-hour functional-test run was
  readable only over the network — core 1 clocks straight through an outage, so the
  run survives one and the result now does too, printed on the serial banner with
  its trap address and listing line; (b) *nothing watched the station link* — zero
  references to `cyw43_wifi_link_status` or any reconnect, so a dropped link cost
  the panel until a power cycle. `link_watch()` polls `cyw43_tcpip_link_status`
  every 5 s (associated-but-no-address is still unreachable), allows 20 s of grace
  so roaming and rekeying do not tear down a working setup, then retries and falls
  back to the setup AP — which is itself no longer terminal, re-trying the stored
  network every 5 min but never while the portal is open; (c) **the one that was
  actually biting, found by the user deliberately entering a wrong password**: the
  portal came up stuck on `scanning…` with no AP list. `try_sta()` enables station
  mode and nothing turned it off on failure, so the AP came up on a radio still
  retrying an association, which **starves the scan** — it stays "active" forever,
  `busy` never clears, and the page never replaces its placeholder. **A virgin board
  never hit this** because `try_sta()` returns before enabling station mode when no
  SSID is stored, which is exactly why setup worked the first time and broke after
  one wrong password. `start_ap()` now disables station mode first, and a scan that
  has not finished in 15 s is treated as finished. **Verified end to end by the
  user: AP list appears, correct password joins, and the new panel control
  (Network → Forget this network) reboots to setup mode and reprovisions cleanly.**
  Also: **no firmware blocks waiting for a terminal any more** [user directive] —
  the tester's `autorun off` path sat in `while (!stdio_usb_connected())` with clk0
  parked LOW, which is the **1.4 A peak-draw state its own comment warns about**,
  potentially forever. It now has one non-blocking wait, `read_line()` returns −1 on
  disconnect so a dropped terminal mid-paste unwinds instead of wedging, and the
  banner reprints on every attach. Verified on hardware: 317,508 cycles free-ran
  before first attach, commands still work, and a detach/reattach clocked 119,100
  cycles in 12 s. **Two bugs of my own caught before they shipped**, both from the
  same class — an edit whose blast radius was wider than the line I was looking at:
  `next_ap_retry` started at zero, so the board tore its own AP down for 40 s of
  retrying *the instant* setup mode came up, killing the in-flight scan (that was
  the first `scan stalled` in my own test); and the warning colour was first added
  as `.w`, which is **already the page-wrapper class** — every element is inside
  `<div class=w>`, so it would have tinted the whole panel. Incidental: `cmd()`
  displayed `j.err` but **silently dropped `j.warn`**, which the console op had been
  returning all along. **Flashed and running** (wifi build, `EMBED_FUNCTEST=ON`,
  430,088 B text / 99,712 B bss). **Next is unchanged: Step 5 — solder a Pico.**
  Still unexercised: the link-drop and rejoin paths, which need a real AP outage;
  and `pico-controller/README.md`'s bring-up steps 1/2/2b remain stale against
  `docs/bring-up.html` (Step 1 still states the falsified "must read high" gate,
  Step 2 still leads with 0.35 A, Step 2b still reads as pending) — a documentation
  sweep nobody has done yet.

- 2026-08-25: **THE CPU EXECUTES. The program counter was found in a video of the LEDs, bit by bit,
  at exactly the frequencies arithmetic demands.** After rewiring the supply, tying `irq`/`nmi` high
  and halving the clock to 2250 Hz, a 14.7 s clip contains the 6502's PC — **92 LEDs land on a
  predicted PC-bit frequency and not one strong peak matches anything else**. Full record:
  `docs/actual-bring-up.html` Step 3c; reproduce with `tools/pc_ripple.py --clock 2250 --frames DIR`.
  **The test needs no LED to be identified**: on a NOP free-run the CPU only fetches and increments,
  so PC bit *b* must toggle at `1125 / 2^(b+1)` Hz and either those frequencies are there or they are
  not. **CORRECTED the same day.** This entry first claimed the decisive evidence was *aliased* fast
  PCL bits — 35.16 Hz appearing at 5.256 Hz and so on. **That argument is wrong.** Aliasing requires
  *point* sampling; a camera **integrates over its exposure**, which low-passes the signal, so a
  562 Hz LED averaged over even a 1/500 s exposure spans ~1.1 cycles and comes out a constant
  half-brightness glow. **PCL0–PCL5 are physically unmeasurable from video**, and the apparent
  detections at their aliased frequencies were **drift artifacts** — the board wanders **76 px**
  through the clip (phase correlation), which manufactures spurious blobs and modulations in a max
  projection. **The real proof is four bits identified BY NAME**: PCL7 4.407 vs 4.395, PCH0 2.170 vs
  2.197, PCH2 0.542 vs 0.549, PCH3 0.271 vs 0.275 Hz, with a ladder on *measured* rates confirming
  each runs at half the one above (2.031, 4.000, 2.000 against 2, 4, 2). The other eight marked bits
  all returned **the same 0.475 Hz** — one artifact, not eight signals; their markers sit on genuinely
  lit LEDs (peak 186–202, duty 0.22–0.58), and 0.475 Hz is a 2.1 s period, i.e. camera sway surviving
  as residual tracking error. **PCL6 at 8.789 Hz is below Nyquist and should have worked; that it did
  not is unresolved.** Two of my own bugs surfaced here and are fixed: the ladder compared *predicted*
  rates, exact by construction, so it always printed "ok"; and a marker on dark board reported
  whatever the detrending residual peaked at instead of "no signal". **This resolves the
  previous entry's warning**: the 2026-08-24 spectra really were measuring an artifact, and the
  reasons are now known — a browning-out Arduino, floating `irq`/`nmi` vectoring PC to $EAEA, and two
  method errors recorded in the log (aggregating 55 LEDs so the 16 PC bits are diluted, and failing to
  detrend the record's own envelope, which faked a 0.55 Hz peak at 11.9× the noise floor). Underlying
  all of it: **only the direct low-frequency bits were ever looked for**, and those share a spectrum
  with every slow artifact. **What is proved:** fetch, decode, execute, and the PC incrementing
  correctly through **at least 12 bits** — which requires the decode PLA, the PC incrementer, the
  address drivers and on-board clock phase generation to all work, i.e. 4,051 discrete transistors
  doing 6502 logic. It also retroactively confirms the clock regenerates on-board, the dynamic nodes
  hold at the leakage measured in Step 2b, and the `irq`/`nmi` fix took. **What is not proved:** a NOP
  free-run never touches the ALU, A/X/Y, the stack, the flags, addressing modes or branches —
  **Klaus Dormann's suite remains the acceptance gate**. New: `tools/pc_ripple.py`, which prints the
  predicted (and aliased) frequencies for any clock and frame rate and, given extracted frames, finds
  them. **Nothing on the board, in the fab package or in the firmware changed.** **Next: Step 5** —
  solder a Pico, which replaces the Arduino entirely (clock + reset + memory) and turns every question
  since 2026-08-12 into a printed instruction trace instead of a video analysis.

- 2026-08-24 (later, **UNVERIFIED — hypotheses, not findings**): **the bench supply arrangement is
  suspect, and if it is, several of the day's LED analyses were measuring the Arduino rather than the
  6502.** Nothing here is confirmed; it is written down so tomorrow starts with the right three
  measurements instead of more video. **(a) Too much series resistance.** The supply path ran
  charger → junc1 → junc2 → ammeter → board VCC with a matching return, i.e. **six croc segments
  carrying ~0.9 A**. The board's own Step 2 I-V curve puts 0.66 A at **V_board ≈ 3.7 V**, so ~1.3 V
  is being lost in the leads (~2 Ω loop, ~0.33 Ω per segment). **The junc1→junc2 segment is the
  prime suspect**: it is being used as the on/off switch, so it is a repeatedly made-and-broken croc
  contact carrying the full 0.9 A, which is exactly where oxide and wear produce the worst and least
  repeatable resistance. Replace it with a real toggle rated ≥2 A, or switch on the charger side,
  rather than making and breaking a clip in the high-current path. Note the board has **exactly one VCC
  pad (TP36) and one VSS pad (TP35)** in the whole 36-pad ring, so the current cannot be split across
  pads; a soldered connection to the DNP Pico footprint's **pins 38/39 (`vss`/`vcc`)** is the better
  feed if croc clips prove to be the limit. **(b) The Arduino was browning out.** It was powered from
  **VIN at ~3 V** with no USB of its own; the NCP1117 needs ~6.5 V in for 5 V out, the ATmega328P
  needs 4.5 V at 16 MHz, and the brown-out detector trips near 2.7 V. If it was resetting, every
  reset re-runs `setup()` and therefore **re-asserts RES on the 6502** — which would produce exactly
  the broad, clock-independent **0.15–0.46 Hz** LED activity measured that afternoon and never
  explained. There is even a plausible feedback loop: unclocked the board draws 1.4 A → larger drop →
  Arduino stays dead; clocked it draws 0.87 A → smaller drop → Arduino runs. **(c) An earlier
  configuration is resolved and closed**: powerbank → USB meter → Arduino → VIN → board read 0.11 A /
  4.96 V at the powerbank while the board's series ammeter read 0.66 A. Conservation settles it —
  everything had to pass the USB meter, so the board was getting **~60 mA** and browning out, and the
  0.66 A was a bad reading on an unfused 10 A range. No damage: the UNO's regulator has thermal
  shutdown and the USB polyfuse limits near 1 A. **Consequence: treat every LED spectrum from
  2026-08-24 as provisional**, including the 78.8 s / 120 fps capture — its headline result (no
  counting signature at 8.79/4.39/2.20/1.10 Hz, activity instead a broad 0.15–0.46 Hz hump with
  independent per-LED switching, mean pairwise r = 0.002, PC1 47%) may be a portrait of a resetting
  Arduino. **Also still not done: `irq` and `nmi` were left floating for all of these runs** (user
  caught this), which alone breaks a NOP free-run — an interrupt pushes 3 bytes, changes S and P, and
  vectors PC to $EAEA, destroying the PCH ripple being looked for. **Next session, in order, and with
  the oscilloscope that has been on the bench unused: (1)** separate supplies — Arduino on its own
  USB, board straight to the 2 A charger with the shortest possible path (a 2 A charger is now
  adequate *because* the 2.1 A figure was falsified); **(2)** scope on **RES** — is it pulsing every
  few seconds? That confirms or kills the brown-out hypothesis in one trace; **(3)** scope on **Φ0**
  for the real clock frequency and on **TP36/TP35** for the real rail under load; **(4)** tie `irq`
  and `nmi` to VCC; **then** re-run one capture. Only after that is Step 3c (PCL/PCH ripple at 3.3 V,
  ~3 kHz) worth attempting.

- 2026-08-24: **The board is powered, clocked and free-running — and the driver-contention model
  that has driven planning since 2026-08-01 was falsified by a thermal camera.** Four bring-up steps
  ran in two days and every one of them produced a number this plan did not have. Full log with the
  reasoning: `docs/actual-bring-up.html`. **(a) Step 2, without a bench supply** — there wasn't one,
  so a fixed 5 V source, a cheap ammeter and series power resistors were used instead, which is
  arguably better: the resistor makes the limit physical rather than behavioural, and stepping it
  down *is* the voltage ramp. **The board draws 1.4 A at 5 V against a written expectation of
  0.35 A** — 7 W, four times budget. A short is excluded *arithmetically*: at 1.50 V the board draws
  35 mA, so any parallel ohmic path is ≥ 43 Ω and could contribute at most 116 mA. Below ~3.5 V
  everything sits inside the passive network's hard ceiling (10.56 Ω of pull-ups + LED legs =
  0.548 A at 5 V); above it a second path opens, reaching **+852 mA of unexplained excess**.
  **(b) Step 2b, the retention measurement, made by accident and worth the most.** Two accumulator
  LEDs flash and fade at power-up; `a1`, `a2` and `p1` have **no pull-up, no VCC-side FET and no
  pull-down**, so *nothing on the board can turn them off* — they can only leak. Filmed at 120 fps,
  peak-to-dark is **58.3 ms**, giving **1.9–2.3 nA per FET**, and that is an upper bound. The model
  assumed 1 nA typical and was right. Corroboration nobody fitted: `p1` has one leaking channel to
  `a1`/`a2`'s two, so it should hold twice as long — exactly the order observed. **This closes the
  clock-floor open question in the design's favour** (floor 456–871 Hz, **23–44× window**, 45–55 °C
  headroom) — the thing `sim/retention.sp` explicitly could not resolve, settled by a phone camera
  with no Pico on the board. **(c) Step 3, the Arduino clock.** 4500 Hz push-pull on Φ0, frequency
  chosen from the *measured* floor. First try, data bus floating: the CPU **jammed** — 12 of 256
  opcodes are undocumented KIL, so it halts within ~20 instructions, and the LED count decays
  monotonically to a frozen state (exposure checked, and the remaining LEDs stay equally bright, so
  neither camera nor rail is responsible). **The clock is proven working by the contrast**: those
  same nodes lose charge in 65 ms unclocked but hold for *seconds* clocked, which is the recirculating
  latches refreshing and therefore `cclk`/`cp1` being regenerated on-board. Tying the bus to **$EA
  through 10k** stops the jamming and the count holds at 10–14, jittering, across three power cycles.
  **Sequencing is still NOT demonstrated** — the PCH ripple at 4.4/2.2/1.1/0.55 Hz is absent from the
  spectra, though the test is underpowered (all 55 LEDs summed, PCL aliasing at 1125 Hz, handheld
  camera), so it is not evidence of absence either. **(d) Step 3b — the correction.** The rising
  current (1.15 → 1.33 A over 3 s) was called thermal runaway on 3–4 contending pairs and a thermal
  sweep was recommended to find them. **A FLIR One found no hot spot at all**: peak ~30 °C against
  25 °C ambient, and a broad diffuse warm region over the die. A 0.9 W SOT-323 would run 50–150 °C
  above ambient and be unmissable; distributed and concentrated dissipation differ by ~30× in peak
  temperature here, so the images discriminate cleanly. **The excess is distributed — 0.85 A over
  4,051 FETs is ~210 µA each**, ordinary for a FET biased *near* threshold, which is exactly what
  undefined dynamic nodes produce. That also re-explains the current climb as **self-limiting**
  (board warms a few °C, Vth falls ~2 mV/°C, current rises 16%, plateaus) and why clocking moved
  1.4 A → 0.7–1.2 A instead of to 0.35 A. **Retracted: the runaway alarm and "seconds, not minutes".**
  What survives is that rev B's *serious* half was never thermal — the invalid 1.0–1.9 V low against
  a 1.1–1.5 V threshold is a correctness bug and still needs fixing — but **rev B is not a fix for
  the current draw and no further hand rework is warranted**. New: `tools/mark_hotsites.py` →
  `docs/hotsites-marked.jpg` (all 164 sites grouped by what they drive; the 22 with no pull-down that
  *cannot* be hot are marked distinctly, and the 142 that can independently reproduces rev B's site
  count). `docs/bring-up.html` corrected in two places — the clock frequency (1–2 kHz → 4–5 kHz,
  against the measured floor) and the expected current *direction*, which the page had backwards.
  **Nothing on the board, in the fab package or in the firmware changed.** **Next: Step 3c — does it
  compute?** 3.3 V, ~3 kHz, camera fixed on the PCL/PCH columns, looking for a binary cascade at
  2.9 / 1.5 / 0.73 Hz. That is the lowest clock the measured floor allows, and therefore the only rate
  at which a human can watch the program counter at all.

- 2026-08-16: **The tester can now carry the acceptance images itself, and building that found a
  real error in what this plan said about floating interrupts.** [user decision] the images are
  compiled in only behind **`-DEMBED_FUNCTEST=ON`, off by default** — not a technical call but a
  licensing one, since Klaus Dormann's suite is GPLv3 and this repo is CC BY-NC-SA 4.0, which GPLv3
  forbids combining with. The user's framing is what shaped it: *"separate it to an option, not
  default — we do not ship it built in but make it simple to add."* So `tools/embed_functest.py`
  generates `common/functest_images.c` on request only, that file is **gitignored**, a default build
  links `functest_images_none.c` (so no call site needs an `#ifdef`), and **no binary containing
  GPLv3 material is ever produced here**. A flag rather than an interactive prompt because CMake is
  non-interactive by contract — instead every configure prints how to turn it on. With it on, `T f`
  / `T d` replace the 37.6 kB hand-paste, and a self-loop is reported as **PASS/FAIL with its
  listing line** rather than as an address to look up in a CSV. Cost measured, not estimated:
  **+39 KB flash and 0 bytes RAM** (tester text 41,604 → 81,348; **bss unchanged at 32,400**, which
  is the proof the const data stayed in XIP flash). Both configurations build warning-free and the
  embedded data was checked on the host against known addresses. **The finding is the more valuable
  half.** Verifying those addresses showed the 2026-08-08 claim — that a spurious interrupt is
  benign *because identifiable* — is only half true. `$380B` (NMI) is a genuine self-loop, so the
  CPU stops where you can see it. **`$3819` (IRQ) is not a trap at all**: it is `irq_trap`, the
  BRK-test handler, live code starting `php / dey / dey / dey`. A spurious IRQ is absorbed, corrupts
  Y and SP, and reappears as a failure at an unrelated address — **a wrong verdict that looks like a
  real CPU defect, which is worse than a stopped run.** Tying `irq` high before any long run is now
  necessary rather than prudent; the firmware warns at load time, deriving it from the image's own
  vector block instead of a hard-coded address. Incidental fixes: `gen/functest/README.md` now
  carries the attribution and licence, which were **absent entirely**, and `bus6502.h`'s `bus_init`
  comment no longer claims a board pull-up on clk0 (there is none — `README.md` had it right).
  **Nothing on the board or in the fab package changed.** Next is unchanged: **Step 2** — 5 V,
  unclocked, ramped from zero, current recorded at 0.5/1/2/3/4/5 V.

- 2026-08-13: **Four bond pads are in the wrong slot on the delivered boards — cosmetic, and worth
  knowing before anyone probes by counting positions.** The user spotted it against visual6502's
  JSSim ("A6 seems to be where A0 should be"), and the comparison was legitimate: our board and
  JSSim have the same handedness, so position-by-position reading works. **A6, VSS, D7 and R/W sit
  out of die order**; A6 heads the left-edge address run instead of ending it, which shifts A0–A5
  one slot down from where the die puts them. **Nothing is miswired and nothing is mislabelled** —
  every one of the 36 pads was checked against copper and carries the net its silk names, and the
  DIP pin numbers are correct as well (which is why the right edge honestly reads PIN 33, 32, 34).
  So the silk is trustworthy and the die photo is not: **locate a pad by its label, never by
  counting**. Cause is `rim_slot`'s greedy first-come allocation running in component order while
  the die projects the address pads at a 16.0 mm pitch against a 19.7 mm required spacing — the
  push accumulates until A6 has nowhere legal below the corner limit and wraps 116 mm back up the
  edge; R/W and VSS separately project inside the corner exclusion. Confidence is high because a
  re-simulation of `rim_slot` reproduces all 36 placed pads to 0.01 mm. **New: `cards/bond-pad-ring.md`**
  — how the ring is derived, the defect, and the order-preserving fix with its feasibility numbers,
  ready to apply at a respin. **`tools/gen_pcb.py` was deliberately NOT changed**: the fix moves pad
  positions, so it forces the full pipeline from `gen_pcb.py` onward (placement, power, routing,
  finishing, silk, fab outputs) and would break parity against the fabricated golden board. It also
  suggests a cheap permanent gate that would have caught this pre-fab — assert the placed order
  equals the die-coordinate order on all four edges. Incidental: **`cclk` is internal node 943, not
  a pin** — the shape at the top-right die edge that looks like a pad in JSSim is a third the area
  of a real one and is clock distribution running through the R/W driver. **Nothing on the board, in
  the fab package or in the firmware changed** — documentation only. **Next is unchanged: Step 2** —
  5 V, unclocked, no Pico, voltage ramped from zero, current recorded at 0.5/1/2/3/4/5 V.

- 2026-08-12: **THE BOARDS ARE HERE, AND STEP 1 IS PASSED — bring-up has actually started.**
  4 assembled + 1 bare, depaneled, visually good. Receiving inspection confirmed on real hardware
  the two things that were previously verified only on JLC's DFM render: **FET orientation is
  uniform across the array** (pin-1 marker against the silk triangle everywhere) and **one marking
  code throughout**, so the all-four-boards rotation and wrong-reel risks are now closed by
  inspection of the delivered product. Fillets look formed and consistent at the magnification
  available — encouraging, not conclusive, since the predicted defects are singles.
  **Step 1 read ≈195 Ω on all four boards and this looked like a short. It is not.** The written
  gate ("must read high") was wrong, and correcting it produced the first real finding of bring-up:
  **there is no resistor-only path between VCC and VSS at all** — the meter is reading the FET body
  diodes, of which **1,899 across 947 nets** conduct VSS → drain → 10k → VCC. So the display is a
  diode drop divided by the range's test current, and the same board legitimately reads 195 Ω / 314 Ω
  / 3.77 kΩ on the 200 / 2k / 20k ranges while the **voltage across it stays at 0.36–0.47 V**. Four
  arguments kill the short hypothesis, the strongest needing no model: **a reading that changes with
  range is not a resistance**, and a plane-to-plane bridge would read under an ohm, not hundreds.
  The reverse direction (red on VCC, which is also the normal operating polarity) conducts too —
  not predicted — and was resolved by observation: held 20 s it drifted *down*, killing the
  capacitor-charging hypothesis, and its two points give **55.4 mV/decade against an ideal 59.5**,
  i.e. an exponential junction rather than a resistive fault. ~95 µA of leakage at 0.8 V.
  **A model prediction made before the measurement landed within 5%** (3601 Ω predicted at 0.1 mA;
  3.77 kΩ read at an implied 95 µA), which is independent evidence the netlist-derived model matches
  the hardware. **The upgrade worth remembering: Step 1 is a positive test, not a null one** — the
  forward path cannot exist unless the 10 kΩ pull-ups are populated, so one 10-second measurement
  confirms ~1,000 back-side 0402s are present and connected, which no photograph of a green board
  can do. New: `tools/step1_model.py` (derives all of the above from `gen/netlist.json`, measured
  values in one editable table) and `docs/actual-bring-up.html`, the measurement log, kept separate
  from `docs/bring-up.html` which stays the procedure. The Step 1 gate in the procedure page is
  corrected in place, with the old wording left visible as a correction. **Nothing on the board, in
  the fab package or in the firmware changed.** **Next: Step 2** — 5 V, unclocked, no Pico, voltage
  ramped from zero, expecting ≈0.35 A; record the current at 0.5/1/2/3/4/5 V rather than only at
  5 V, which turns it into the board's I-V curve and retires the leakage question with a real
  instrument. Then the eight-site rework *before* any stall test. Still open from Step 1: reverse
  readings on boards #2–#4, and a diode-mode reading to remove the inferred test currents.


