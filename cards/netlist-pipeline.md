# netlist-pipeline

The scripted flow that turns the visual6502 transistor data into the discrete-parts netlist — toolchain decision, how to run it, what it emits, and its invariants.

Toolchain decision (2026-07-18): **KiCad** is the EDA target. No hand-drawn schematic exists or ever will — `tools/gen_netlist.py` is the single source of truth. Its KiCad netlist is imported directly into pcbnew; placement will be scripted via KiCad's Python API (M5). KiCad only needs to be installed when layout starts.

Run: `python3 tools/gen_netlist.py` (from repo root). Reads `data/visual6502/`, writes:

- `gen/netlist.json` — canonical netlist: components (ref, type, value, LCSC, footprint, role, origin transistor/node) + nets (net → list of ref/pad). Downstream scripts (SPICE export, placement, BOM) should consume this, not the KiCad file.
- `gen/discrete6502.net` — KiCad s-expression netlist with footprints and LCSC fields, for pcbnew "update from netlist".

Transform rules (all decided 2026-07-18):

1. Drop always-off transistors (gate=vss; 17 — ESD clamps and die dummies) and no-ops (c1=c2; 3).
2. Merge exact parallel duplicates (270).
3. Channel touching vss → single FET, source on vss (2,276). Channel touching vcc → single FET, source on the non-vcc side (165).
   *(Counts here are at this step; rule 7 later drops 3 FETs, so the final netlist has 164 vcc-side and 778 pass pairs.)*
4. Pass transistors (779 after dedup) → back-to-back FET pair, common source node `t<N>_mid`, gates on the original gate net.
5. Every '+'-flagged node (1,018) → 10k pull-up to vcc.
6. LED taps (55): A/X/Y/S/PCL/PCH bits + P flags (p0–p4,p6,p7) each get a gate-tap FET sinking LED+2.2k from vcc — capacitive load only on the monitored node.
7. Iterative cleanup: drop FETs whose drain/source net is floating and non-external (3 spare die structures).

Resulting totals (final, as ordered): **5,421 components / 2,624 nets**, of which 5,328 are factory placements (the rest are the 36 THT bond pads, 56 DNP ballast caps and the unpopulated Pico site).

| Qty | Part | LCSC | Package |
|---|---|---|---|
| 4,051 | BSS138K (core FET) | C504052 | SOT-323 |
| 1,023 | 10k pull-up | C25744 | 0402 |
| 96 | 100nF decoupler | C1525 | 0402 |
| 55 | red LED | C2286 | 0603 |
| 55 | 2.2k LED ballast | C25879 | 0402 |
| 26 | 1k Pico series R | C11702 | 0402 |
| 12 | 1N4148WS protection | C2128 | SOD-323 |
| 6 | 100R input series | C25076 | 0402 |
| 4 | 10µF bulk | C15850 | 0805 |
| 56 | 100pF ballast — **DNP**, bring-up insurance | — | 0402 |

The core FET was 2N7002 (C8545, SOT-23) at M2, then 2N7002W (SOT-323) for the die-texture layout, and finally **BSS138K C504052** at order time (2026-07-25) because JLC had no 2N7002W stock — same package and pinout, lower Vth, SPICE-validated as the M2 fallback.

Invariants the script checks (fails loudly if broken): all 36 external 6502 interface nets exist (ab0–15, db0–7, clk0/1out/2out, res, rdy, irq, nmi, rw, sync, so, vss, vcc); all LED nodes resolve; the only singleton nets are res/irq/nmi (each lost only its on-die ESD clamp — the discrete board adds its own input protection — 100R series + dual 1N4148WS clamps on res/irq/nmi/rdy/so/clk0).

Verification status: **behavioral equivalence proven** (M4) — `tools/switchsim.py` runs this netlist and the original visual6502 netlist side by side and gets bit-identical traces on a real test program. Re-run it after any netlist change; it is the project's equivalence gate. The `origin` field on every component is what makes that mapping back to original transistor IDs possible.
