# discrete6502

A working **MOS 6502 CPU built from 4,051 discrete surface-mount transistors**, laid out as a
291 × 322 mm six-layer PCB that visually reproduces the original 6502 die — every FET sits at
its transistor's die-true position, 55 LEDs blink the register bits in place, and a ring of
die-scaled bond pads around the edge takes crocodile clips.

Inspired by the [MOnSter 6502](https://monster6502.com/) (concept only — independently designed
and simplified). Logic ground truth is the [visual6502](http://visual6502.org) reverse-engineered
netlist, captured from photographs of a real decapped 6502.

| Front (the die) | Back (passives + Pico site) |
|---|---|
| ![front](gen/board_top.png) | ![back](gen/board_bottom.png) |

## Status

Design complete and verified; ready to order (fab package in `gen/fab/`, checklist in
`gen/fab/ordering.html`). Bring-up (M6) starts when boards arrive.

| Milestone | State |
|---|---|
| M1 Research (visual6502 data, MOnSter lessons) | ✅ |
| M2 Feasibility (dynamic NMOS, pass-FET pairs, SPICE) | ✅ |
| M3 Toolchain (KiCad, scripted netlist pipeline) | ✅ |
| M4 Verification (switch-level equivalence, vendor-model SPICE) | ✅ |
| M5 Layout (placement, routing, DRC-clean, fab outputs) | ✅ |
| M6 Fab & bring-up | ⏳ |

## Highlights

- **Faithful dynamic NMOS logic** — not a static re-design: the visual6502 netlist's 3,239 unique
  transistors, with the 783 pass transistors implemented as back-to-back FET pairs (BSS138K)
  (clock-edge bootstrap validated in SPICE with the manufacturer's model) and 1,018 pull-up
  resistors standing in for the depletion loads. Target clock ≥ 50 kHz.
- **Machine-checked correctness**: a switch-level simulator proves the transformed netlist
  produces bit-identical traces to the original visual6502 netlist while running real 6502
  code; board-vs-netlist parity and independent copper-connectivity checks close the chain.
  Final DRC: zero electrical violations.
- **Custom autorouter** (`tools/route_nc.c/.py`): a PathFinder-style negotiated-congestion router
  — nets route through conflicts, shared cells get iteratively penalized, conflicted nets
  rip-up and retry — on a 0.13 mm grid over 4 routing layers, with warm-start checkpoints.
  8,421 signal connections routed; the C core does a full negotiation iteration in seconds.
- **Bring-up harness built in**: an unpopulated Raspberry Pi Pico 2 W site on the back acts as
  clock master and memory emulator (data bus, 14 address bits with 16 KB mirroring, reset,
  R/W, SYNC via factory-fitted series resistors). Solder a Pico on, flash firmware, and the
  CPU runs programs with full bus tracing — no other computer needed.

## Power budget

Dominated by the NMOS pull-up current, not switching (estimate from M2, at VCC = 5 V):

| Contribution | Calculation | Power |
|---|---|---|
| Pull-up static current | 1,018 × 10 kΩ pull-ups; on average ~half the nodes are pulled low → ~509 × 0.5 mA | **~1.3 W** (0.25 A) |
| Register LEDs | ≤55 × ~1.4 mA through 2.2 kΩ (worst case all lit) | ~75 mW |
| Dynamic (gate-cap switching) | ~50 nF of total gate capacitance × V² × f at ≤50 kHz | ~60 mW |
| **Total** | | **≈ 1.4–1.5 W @ 5 V (~0.3 A)** |

A 5 V / 1 A bench supply is comfortable. At the recommended 3.3 V first
bring-up the same math gives ~0.17 A / ~0.6 W. Spread over the 900 cm² board
the heat is imperceptible — compare the original MOnSter 6502 at ~10 W.
The interesting electrical moments are the clock edges (~25 nF of pass-gate
capacitance per phase charged in a few µs → ~50 mA peaks), which is what the
96 distributed 100 nF decouplers are for.

## Repository layout

- `project-plan.md` — goals, milestones, decision log, current handoff (start here)
- `cards/` — deep-dive notes per topic (architecture, layout, verification, …)
- `data/visual6502/` — the reverse-engineered netlist source data
- `tools/` — the entire generation pipeline: netlist transform, die placement, power routing,
  the negotiated-congestion signal router, finishing passes, silkscreen, verification
- `sim/` — ngspice testbenches for the dynamic pass-pair structures
- `gen/` — generated artifacts: netlist, boards (`board_routed_golden.kicad_pcb`), renders,
  and the JLCPCB fabrication package (`gen/fab/`)

## Regenerating the board

The full pipeline, in order (KiCad 10's bundled python for board steps):

```
python3 tools/gen_netlist.py         # visual6502 data -> netlist (+ invariant checks)
python3 tools/switchsim.py           # equivalence gate: must stay green
<kicad-python> tools/gen_pcb.py      # die-true placement, board setup
<kicad-python> tools/route_power.py  # planes + ~3,700 stitch vias
<kicad-python> tools/route_power_finish.py   # (on the presignal snapshot)
<kicad-python> tools/route_nc.py     # signal routing (hours; checkpointed)
<kicad-python> tools/fix_same_net_vias.py
<kicad-python> tools/fix_via_pairs.py
<kicad-python> tools/add_silk.py
<kicad-python> tools/check_parity.py && tools/check_gaps.py + kicad-cli drc
```

See `cards/layout.md` for the rules and hard-won caveats behind each step.

## License & attribution

The design derives from the visual6502 project's netlist data (`segdefs.js` is
**CC BY-NC-SA** — noncommercial). This project is a hobby build and inherits that spirit:
**non-commercial use only**, attribution to [visual6502.org](http://visual6502.org).
The MOnSter 6502 by Eric Schlaepfer & Evil Mad Scientist Laboratories proved a discrete
6502 is possible and is gratefully acknowledged as inspiration.
