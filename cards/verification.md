# verification

How the transformed discrete netlist is proven correct — the switch-level equivalence harness, its results, and the analog vendor-model findings (M4, 2026-07-18).

**Switch-level equivalence** — `tools/switchsim.py` implements the visual6502/perfect6502 algorithm (conduction-group BFS; value priority vss > vcc > pulldown > pullup > "floating group is high if any member held charge") and runs the *same* 6502 program on both the original visual6502 netlist and `gen/netlist.json`, behind the same memory harness. Results: after the reset sequence flushes arbitrary initial charge (~20 half-cycles), traces (buses, rw, sync, A, X, PC) are **identical for the full run**, and a program exercising stack, JSR/RTS, ADC with carry, DEX/BNE looping, and PHA/PLA completes with correct state on both (A=$20, X=0, stores verified). Runtime ~1s. Pitfalls encoded in the code, learned the hard way:

- Group value resolution must be deterministic and prioritized (pulldown before pullup); early-returning on the first flag found in set order silently corrupts ALU results.
- A floating group reads high if *any* member was high (perfect6502 rule) — majority voting breaks DEX and friends.
- Memory harness order matters: service reads after driving clk low, capture writes after driving clk high; capturing on both halves writes garbage at transient addresses.

Extend the test by editing `TEST_PROGRAM`; any new netlist transform must keep this equivalence green.

**Analog verification with the manufacturer model** — `sim/2N7002_onsemi.lib` (onsemi BSIM3v3 subckt `F2N7002`, pins D G S; needs `set ngbehavior=psa`, provided by `sim/.spiceinit`). Testbench `sim/passpair_vendor.sp`: driver inverter → pass pair → 20pF bus → pass pair → 5pF storage node with LED-tap load → output inverter.

- **Source-driven transfers work for both levels**, even through a 4-FET series chain: stored '1' ≈ 5.1V (bootstrap-assisted, no threshold drop), stored '0' ≈ −1.6V, output inverter levels clean.
- **Writing '0' between two floating islands fails**: the clock edge injects gate-capacitance charge into the island (observed: −1.1V → +3.4V jump), starving both FETs of Vgs so the pair never conducts. Root cause: discrete gate caps (~30pF) rival node caps, inverting the die's Cnode >> Cgate hierarchy.
- Why this is acceptable: the 6502 never relies on floating-to-floating '0' transfer — buses are precharged high and conditionally discharged through driven pull-down paths, which is exactly what the golden model's "floating = high if any member high" rule encodes. The switch-level equivalence run passing under that rule is the logical-side evidence.
- Insurance for layout (M5): reserve DNP ballast-capacitor footprints (~100–220pF) on the main bus nets so the capacitance hierarchy can be restored at bring-up if edge injection misbehaves in reality.
