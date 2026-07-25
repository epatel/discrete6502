# pass-pair-validation

Decision + evidence: NMOS transmission gates are implemented as back-to-back 3-terminal MOSFET pairs; validated by SPICE on a 6502-style dynamic latch (2026-07-18).

Decision: every bidirectional pass transistor in the netlist becomes two identical N-MOSFETs in series — drains facing outward, common source/body node in the middle, both gates on the clock signal. No 4-terminal FETs or array chips anywhere in the design. Ordinary pull-downs stay single FETs; depletion pull-ups become 10k resistors (ratioed NMOS logic, 5V supply).

Evidence — `sim/passpair_latch.sp` (ngspice, VDMOS models): a full latch chain (ratioed driver inverter → pass pair → floating storage node → output inverter) simulated at 6502-like clocking for three candidates:

| FET (model approx.) | stored '1' | stored '0' | output low | output high |
|---|---|---|---|---|
| BSS138 (Vto 1.1V) | 6.06 V | −0.23 V | 1.3 mV | 5.00 V |
| 2N7002 worst (Vto 2.4V) | 6.05 V | −0.36 V | 1.5 mV | 5.00 V |
| AO3400A (Vto 0.9V, Ciss≈1nF) | 6.83 V | −0.42 V | 37 µV | 5.00 V |

Key findings:

- **Clock-edge bootstrap over-charges the stored '1' above VDD** (~6V): the floating common-source node couples up on clock edges through the two gate capacitances and rectifies charge into the storage node through the pair's body diodes. This *eliminates the classic pass-gate threshold drop* — even a worst-case Vto=2.4V 2N7002 stores a robust '1'. Result held from 5pF to 50pF storage-node loading. Caveat: this mechanism is doing load-bearing work; it must be re-verified with manufacturer SPICE models (the VDMOS models here are hand-approximated from datasheet values) and on other 6502 circuit topologies (series pass-gate chains, clock drivers, register file) before layout.
- **Retention** is a non-issue at 50 kHz: droop over a 25µs hold was <2mV.
- **Speed** rules out high-capacitance FETs: node rise time ≈ 2.2·R_pullup·C_node. At 10k, 2N7002/BSS138-class (~30pF) gives ~0.3µs (fine to a few hundred kHz); AO3400A (~1nF) gives ~10µs (too slow). Choose FETs by *low Ciss*, not low Rds_on.

Part selection (JLCPCB, checked 2026-07-18): primary FET **2N7002, part C8545** — basic library, SOT-23, huge stock, cheapest available; fallback **BSS138, C52895** if lower Vto proves necessary with real vendor models. Pull-ups: 10kΩ 0402 (basic). Power estimate at 10k pull-ups: ~half of 1,018 pulled-up nodes low at any time → ~0.25 A / ~1.3 W core power (vs. MOnSter's ~10 W incl. LEDs). A SOT-323/SOT-723 2N7002 variant (extended part, one-time reel fee only) is the lever for shrinking the board.

Board-size target derived from this: ~4,022 FETs + ~1,018 resistors, double-sided assembly, 4 layers → roughly 225×225 mm with SOT-23, ~180×185 mm with SOT-323. Target: **fit within 200×250 mm** (about half the MOnSter's 305×380 mm footprint).

**Superseded by later decisions (this section is the M2 record, kept for the reasoning):**
the part is now **BSS138K, LCSC C504052, SOT-323** (the fallback above, chosen at order time —
2N7002W was out of stock); the board is **290.7 × 322 mm, 6 layers**, deliberately larger than
the packing minimum because the die-mimicry directive requires preserving the die's empty space.
The power estimate held: measured-by-calculation ≈ 1.4–1.5 W at 5 V (see README).

## 3.3 V validation (2026-07-25) — `sim/passpair_33v.sp`

The recommended first power-up runs the whole board at 3.3 V (one supply domain with the Pico),
so the bootstrap was re-checked at that rail. Same worst-path topology as the M4 vendor bench
(driver → pass pair → 20 pF bus → pass pair → 5 pF storage node + LED tap → output inverter),
three FET flavours in parallel — onsemi vendor 2N7002 BSIM3v3 (pessimistic Vth), BSS138 typical
(Vto 1.1), BSS138K worst case (Vto 1.5) — swept over 5.0 / 3.3 / 3.0 V by `alterparam`.

| Measurement (vendor model — the pessimistic one) | 5.0 V | 3.3 V | 3.0 V |
|---|---|---|---|
| Stored '1' after transfer, held 13 µs | 5.17 V | 3.39 V | 3.08 V |
| … as a fraction of the rail | 1.035× | 1.027× | 1.027× |
| Next-stage output driven low by that '1' | 0.9 mV | 1.0 mV | 1.2 mV |
| Source-driven '0' through a pass pair | −1.11 V | −1.09 V | −1.08 V |
| 10k pull-up recovery (10→90%) | 1.10 µs | 1.31 µs | 1.36 µs |

**All four pass gates in the deck pass at every rail, including 3.0 V.** The bootstrap is not a
5 V-only effect: it over-charges the storage node slightly *above* the rail at 3.3 V too, so the
classic pass-gate threshold drop stays cancelled and the next stage sees full overdrive
(1.4 V over Vth on the vendor model, 2.7 V on BSS138K worst case — the ordered part is the
*better* case here, which is why its lower Vth was welcome). Pull-up recovery slows only 19% at
3.3 V (1.3 µs), so a 50 kHz clock (10 µs half-cycle) still has ~7× margin.

Known non-regression: writing '0' from one *floating* island to another still fails at 3.3 V
exactly as it does at 5 V (the M4 finding) — the storage node holds ~2.6 V instead of going low.
This is the documented, accepted limitation; the 6502 never relies on floating-to-floating '0'
transfer, and the switch-level equivalence run is the logic-side evidence. The 56 DNP ballast
caps exist as the hardware fallback if reality disagrees.

## LED tap brightness vs rail — `sim/led_tap.sp` (2026-07-25)

The only practical 3.3 V caveat, and it is not a logic problem. Deck models the real topology
(VCC → 2.2 kΩ → red 0603 LED → tap FET → GND) with a diode fitted to Vf ≈ 1.90 V at 2 mA;
the tap FET's saturation voltage turns out to be negligible (2–4 mV), so brightness is set
entirely by (VCC − Vf)/2.2 kΩ.

| VCC | LED current | LED Vf | vs 5 V | perceived (∝ I^⅓) |
|---|---|---|---|---|
| 5.0 V | 1.42 mA | 1.88 V | 100% | 100% |
| 3.3 V | 0.67 mA | 1.83 V | 47% | ~78% |
| 3.0 V | 0.54 mA | 1.82 V | 38% | ~72% |

So the 3.3 V bring-up loses over half the LED *current* but only about a fifth of the apparent
brightness — dim, clearly readable, not a fault. Nothing can be done about it without reworking
the 2.2 kΩ ballasts, and it is not worth it.

Consequence for the power budget: 55 LEDs at 1.42 mA is **~78 mA / 0.39 W at 5 V** with every
LED lit (about half that in typical operation) — the README's earlier 75 mW figure for this row
confused mA with mW. Board total is ≈ 1.6–1.8 W at 5 V, ≈ 0.7 W at 3.3 V.
