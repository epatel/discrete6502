# monster6502-lessons

What the original MOnSter 6502 did, what it proved, and where this project deliberately diverges to be simpler (the MOnSter is inspiration, not a spec to copy).

Facts about the original (monster6502.com, by Eric Schlaepfer with Evil Mad Scientist Laboratories):

- Faithful dynamic-NMOS re-implementation of the 6502 at transistor level. 4,769 total components: 3,218 functional enhancement-mode N-MOSFETs (2,588 discrete + 630 on 164 quad-array chips), 1,019 resistors replacing the depletion pull-ups, 313 LEDs, ~998 support parts (LED drivers, caps, diodes).
- Board: 12 × 15 in (~305 × 380 mm), 4 layers, components on both sides. 5 V supply, ~2 A (10 W). Max reliable clock ≈ 50 kHz (~1/20 of original) — limited by discrete MOSFET gate capacitance, not layout.
- The 164 quad-MOSFET array chips exist because NMOS transmission gates need a 4-terminal MOSFET (separate substrate pin); individually packaged 4-terminal FETs are no longer made.
- Eric wrote a custom LVS tool to check the layout against the netlist — at ~3,000+ transistors, hand-checking is impossible. Any re-creation needs equivalent scripted verification.

What this proves for us: dynamic NMOS logic from the visual6502 netlist does work with discrete MOSFETs and resistor pull-ups at 5 V and tens of kHz. Charge-storage nodes hold state fine at these speeds (discrete gate capacitance is large, which *helps* retention while hurting speed).

## Clock windows compared (the original had a floor too)

Verified 2026-07-28 from the [MOS 6500-family datasheet](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf) in 6502.org's archive, not from memory. The Electrical Characteristics header states, on both the 1/2 MHz and the 3/4 MHz pages:

> **Minimum clock frequency = 50 KHz**

The cycle-time row gives only a minimum (tCYC 1000 / 500 / 333 / 250 ns for the 6502 / A / B / C, i.e. 1–4 MHz); its MAX column is an em dash. The floor is not expressed as a maximum cycle time at all — it is that separate frequency line. Φ0(in) pulse width is bounded at both ends too (460–520 ns at 1 MHz), so duty cycle is not free either. Rockwell's R65C02 datasheet carries the matching warning that holding the clock low beyond 5 µs can lose register and status data. The CMOS W65C02 removed the floor entirely by being fully static.

| | Original NMOS 6502 | MOnSter 6502 | discrete6502 |
|---|---|---|---|
| Ceiling | 1 MHz (4 MHz for the C grade) | ~50 kHz | ~20 kHz at 5 V, ~10 kHz at 3.3 V |
| Floor | 50 kHz (datasheet) | not recorded | ~378 Hz expected, **unproven** |
| Window | 20x | — | ~53x |
| Limited by | process | discrete gate capacitance | PLA-line fanout (10k against up to 1.9 nF) |

Two things follow. Our ceiling is ~50x below the original's, which is the expected price of 27 pF discrete gates behind 10k pull-ups (`sim/fanout_speed.sp`). But our **floor is ~130x lower** than the original's, so the usable window is *wider in ratio* than the real chip's — it just sits two decades further down. Same effect as the paragraph above: large discrete gate capacitance hurts speed and helps retention, and here it helps more than it hurts.

The practical consequence is identical to the original, and it is why the tester has `w`/`W` and why single-stepping is a burst-to-sync rather than a clock stop: **the clock cannot be stopped.** Note also that the MOnSter's ~50 kHz ceiling lands almost exactly on the real chip's *minimum* — a discrete rebuild of this logic style operates entirely below the window the original was specified for.

Deliberate divergences for discrete6502 (decided 2026-07-18: MOnSter is inspiration only — improve and simplify while keeping the discrete-transistor-6502 concept):

- **Trim the LEDs to meaningful state (~55 vs. 313)**: LEDs only on registers and counters — A, X, Y, S, P flags, PCL, PCH (all named nodes in the netlist). Each is buffered by a single 2N7002 whose gate taps the dynamic node (capacitive load only, no DC drain), sinking an 0603 LED + resistor from 5 V: 3 parts per LED, ~165 parts total vs. the MOnSter's ~1,300 display parts. Buffer gate capacitance (~25 pF/tap) must be included in verification sims. Bus (ab/db) and IR LEDs are cheap script-generated add-ons if wanted.
- **Avoid the 4-terminal MOSFET arrays**: for each of the 783 pass transistors, use two identical back-to-back 3-terminal MOSFETs with common source (the standard discrete load-switch trick — the two body diodes oppose, so the pair blocks both ways and conducts when the shared gate is high). Costs ~783 extra placements but every FET on the board becomes the same cheap jellybean part — one part number, economic assembly class, no exotic sourcing. Alternative if pair behavior proves problematic in simulation: selectively convert dynamic latches to static equivalents.
- **Exploit netlist redundancy**: 271 of the 3,510 netlist transistors are exact parallel duplicates (die-layout artifacts for drive strength) — merge them; discrete FETs have plenty of drive.
- **Design for pick-and-place from day one**: small packages (SOT-323/SOT-723 class FETs, 0402 resistors), part choices restricted to JLCPCB economic class with deep stock, board size driven by assembly cost rather than aesthetics.

Rough part budget after divergences: ~2,456 ordinary logic FETs (3,239 unique minus 783 pass) + ~1,566 pass-pair FETs + ~1,018 pull-up resistors + decoupling ≈ 5,100 parts of essentially 2–3 distinct types — more placements than the MOnSter but radically simpler sourcing and assembly.
