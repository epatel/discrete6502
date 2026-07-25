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
4. Pass transistors (779 after dedup) → back-to-back FET pair, common source node `t<N>_mid`, gates on the original gate net.
5. Every '+'-flagged node (1,018) → 10k pull-up to vcc.
6. LED taps (55): A/X/Y/S/PCL/PCH bits + P flags (p0–p4,p6,p7) each get a gate-tap FET sinking LED+2.2k from vcc — capacitive load only on the monitored node.
7. Iterative cleanup: drop FETs whose drain/source net is floating and non-external (3 spare die structures).

Resulting totals: **5,179 components** (4,054 × 2N7002, 1,073 resistors, 55 LEDs — 5 distinct part numbers), 2,587 nets. Parts: 2N7002=C8545 (SOT-23), 10k=C25744, 2.2k=C25879 (0402), red LED=C2286 (0603) — all JLCPCB basic class.

Invariants the script checks (fails loudly if broken): all 36 external 6502 interface nets exist (ab0–15, db0–7, clk0/1out/2out, res, rdy, irq, nmi, rw, sync, so, vss, vcc); all LED nodes resolve; the only singleton nets are res/irq/nmi (each lost only its on-die ESD clamp — the discrete board should add its own input protection, e.g. series R + clamp diodes at the connector; open item for M5).

Verification status: structural only so far. Behavioral equivalence (this netlist vs. the visual6502/perfect6502 golden model) is M4's job — the `origin` field on every component exists precisely to map back to original transistor IDs for that comparison.
