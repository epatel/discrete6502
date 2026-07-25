# visual6502-netlist

The visual6502 transistor-level 6502 netlist: where it lives in this repo, its format, measured statistics, and licensing caveats.

Data lives in `data/visual6502/` (fetched 2026-07-18 from github.com/trebonian/visual6502, master):

- `transdefs.js` — the transistor list. Entries: `['t<N>', gate, c1, c2, [bbox], [geometry]]` where gate/c1/c2 are node numbers. This is the primary design input.
- `segdefs.js` — polygon segments per node; the only field we need is the per-node pull-up flag: entries `[node, '+' , ...]` mark nodes with a depletion-load pull-up. License: **CC BY-NC-SA 3.0 (NonCommercial)** — see licensing note below.
- `nodenames.js` — maps ~421 signal names (ab0–ab15, db0–db7, clk0, res, rdy, registers, etc.) to node numbers. Needed for the external bus interface and for verification probes.

Measured statistics (parsed 2026-07-18; parsing regex needs `\s*` around commas — entries have spaces):

- 3,510 transistors total; **271 are exact parallel duplicates** (same gate + channel pair), so 3,239 unique transistors suffice.
- 1,704 distinct nodes; **1,018 have depletion pull-ups** → each becomes one resistor in a discrete build (matches the MOnSter's 1,019 resistors).
- 2,493 transistors have a channel terminal on vss (ordinary logic pull-downs) — these work fine as plain 3-terminal N-MOSFETs, body tied to source.
- **783 are pass transistors** (neither channel terminal on vss/vcc) — bidirectional, so a 3-terminal MOSFET's internal body-source diode shorts one direction. These need special treatment (4-terminal FET, back-to-back FET pair, or conversion to static logic). 380 transistors are gated directly by clock nodes.
- Key node numbers: vss=558, vcc=657.

Verification reference: the visual6502 JS simulator (or perfect6502, a C port of the same netlist) executes this data cycle-accurately — use it as the golden model when checking any transformed/simplified netlist.

Licensing caveat: `segdefs.js` is CC BY-NC-SA 3.0 (noncommercial); `transdefs.js` has no license header in the file and `nodenames.js` is permissive. A derived commercial product would need licensing clarification; for a personal/hobby build this is fine. Flag before ever selling boards.
