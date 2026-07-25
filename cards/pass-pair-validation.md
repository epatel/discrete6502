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
