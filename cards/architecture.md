# architecture

What the discrete6502 board is, as built, and why it is built that way.

The deliverable is a single PCB implementing the MOS 6502 CPU out of discrete surface-mount
transistors (no microcontroller, no FPGA, no 6502 die). It is a functional re-creation in the
spirit of the MOnSter 6502 by Eric Schlaepfer / Evil Mad Scientist, but targeting a smaller
board and JLCPCB pick-and-place assembly instead of the original's hand-designed board.

## As built

- **Transistor-level netlist** derived from the visual6502 project's reverse-engineered 6502
  netlist (transistor + node lists extracted from die photos). This is the ground truth for
  logic correctness, and switch-level equivalence against it is the project's gate
  (`tools/switchsim.py`).
- **Dynamic NMOS logic, faithfully** — settled in M2, not converted to static. The original is
  enhancement-mode NMOS with depletion-load pull-ups and pass-transistor latches storing state
  as charge; we keep all of that. 4,051 BSS138W FETs (3,996 CPU logic + 55 LED gate-taps),
  1,018 depletion pull-ups replaced by 10 kΩ resistors (plus 5 on external inputs), and the
  778 bidirectional pass transistors implemented as back-to-back 3-terminal FET pairs — a
  3-terminal MOSFET alone would short one direction through its body diode. See
  `cards/pass-pair-validation.md` for why the pairs work: the clock edge bootstraps the stored
  '1' above the rail, cancelling the threshold drop.
- **Clocking**: two-phase, regenerated on-board from the Φ0 input (`cclk`, `cp1` and friends are
  driven by FET pull-ups, not resistors, so they swing the full rail). Speed is limited by
  discrete gate capacitance against 10 kΩ pull-ups — realistically **~20 kHz at 5 V, ~10 kHz at
  3.3 V** (`sim/fanout_speed.sp`), set by the decode-PLA input lines rather than the pass pairs.
- **External interface**: **no connector.** A ring of 36 die-scaled square THT bond pads
  (11.6 mm, 2.5 mm holes) sits at the original die's bond-pad positions and carries the full
  6502 signal set for crocodile clips — the die-mimicry directive made the pads the interface.
  For actual operation, an unpopulated **Raspberry Pi Pico 2 W site** on the back is wired
  through factory-fitted 1 kΩ series resistors to db0–7, ab0–13, clk0, res, r/w and sync; the
  Pico is clock master and memory emulator (`pico-controller/`). Only 14 address bits reach it,
  so its memory image is 16 KB mirrored across the 64 KB space.
- **Scale**: 5,421 netlist components, 5,328 of them factory placements — which is exactly why
  everything is generated. There is no schematic and never will be: `tools/gen_netlist.py` is
  the single source of truth, `tools/gen_pcb.py` places at die-true coordinates, and
  `tools/route_nc.*` routes.

## Repo layout

`data/visual6502/` source data → `tools/` generation pipeline → `gen/` artifacts (netlist,
board, renders, and the `gen/fab/` fabrication package). `sim/` holds the ngspice testbenches,
`cards/` these notes, `pico-controller/` the bring-up firmware.
