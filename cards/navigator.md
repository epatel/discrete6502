# board navigator

A live map of the fabricated rev A board (`navigator/`), served locally. Reach for it whenever the
answer to a question is **a place on the board** — "where is Q2577", "what sits next to it", "which
parts are on `s0`", "show me the rework sites" — and whenever the user is at the bench with the
board in front of them, because it turns an answer they must translate into one they can look at.

It replaces nothing: `tools/mark_*.py` still bake the JPEGs that go in `docs/`, and those stay the
right output for a printed page or a commit. The navigator is the interactive version, and the
place to point *while* the user is working.

```
python3 navigator/server.py            # http://127.0.0.1:8624 ; --open launches a browser
```

Check whether it is already up (`curl -s -m2 http://127.0.0.1:8624/api/state`) before starting a
second one — the user usually has it open. Full reference: `navigator/README.md`.

## Use it to answer, not just to display

The API answers questions in one call, without loading 0.6 MB of parts into context:

```bash
python3 navigator/navctl.py find "net:s0"      # ref, value, role, side, x/y, pins
python3 navigator/navctl.py part Q2577         # one part + its 8 nearest neighbours
python3 navigator/navctl.py net s0             # every pin on a net, with positions
```

Query language (same in the search box): free text plus `net:`, `role:`, `type:`, `value:`,
`layer:`, `ref:`; filters combine. `role:` values come from `gen/netlist.json` — `pulldown`,
`pullup`, `pass_a`/`pass_b`, `vcc_side`, `led_driver`, `led_limit`, `decoupling`, `ballast_dnp`,
`edge_pad`, `pico_series`, `input_protect`.

**`part <ref>` is the one worth remembering.** In-circuit measurement reads the part *and* its
surroundings, so identifying a suspect means comparing it against its neighbours and its matched
twin on an adjacent bit — which is what the neighbour list is for. That is the method that finally
found Q2577 after three wrong calls.

## Use it to point

Everything below broadcasts to the open page over a WebSocket; no reload, and the user sees it as
you say it.

```bash
python3 navigator/navctl.py show Q2577 --label "leaky FET" --text "20k gate-drain" --zoom 20
python3 navigator/navctl.py highlight --net s0 --label "S bit 0" --goto
python3 navigator/navctl.py note "Stack fault" "Q2577 replaced from Q4050; S0 LED now dark."
python3 navigator/navctl.py clear all
python3 navigator/show_rework.py               # list named groups
python3 navigator/show_rework.py rework-adh    # apply one
```

Named groups live in `navigator/groups.py`: `rework-adh` (16), `rework-dor` (8), `vcc-side` (164),
`leds` (55), `bond-pads` (36), `ballast-dnp` (56). Adding one is a resolver function plus a
`GROUPS` entry — **derive membership** (by role, gate net or channel net) and **state the count you
expect**; a group whose count has moved is disabled in the UI showing the mismatch rather than
drawing a map that is quietly short a site. That is the `has_pulldown` failure (it missed nets
pulled low through a pass-gate chain, dropping `adl6`/`adl7`, the two busiest sites on the board)
made structurally impossible.

Etiquette: `clear all` when a topic is finished, and do not silently replace a highlight the user
is reading. `POST /api/group` replaces annotations wholesale; `navctl show` adds one pin at a time
and reuses `--id` to update in place.

## Facts about the map itself

- Coordinates are **board millimetres on both faces** — the same numbers as `gen/netlist.json`,
  `gen/layout.json` and every `tools/mark_*.py` output. Never quote a pixel.
- The bottom render is drawn as seen from the back, so its x axis is mirrored. The page handles it;
  `board_x` for a back-side part is unmirrored, and `t`/`b` at the same coordinate is the same
  place through the board.
- Alignment is fitted, not assumed: `build_data.py` takes each render's non-black bounding box as
  the outline (`tools/mark_leds.py:fit_mapping`) and refuses a render whose aspect misses
  290.7/322.0 by >1%. The mirroring was confirmed against the Pico site (board x 40, the left edge)
  appearing on the right of that image.
- Data comes from `gen/layout.json` + `gen/netlist.json`. **`gen/layout.json` is a dump of
  `gen/discrete6502.kicad_pcb`** by `tools/dump_layout.py` under KiCad's python — so after any
  placement change, re-dump it and then `python3 navigator/build_data.py`, or the map silently
  describes the old board.
- **Placement and connectivity only — no copper.** Tracks, vias and zones are not drawn and cannot
  be asked about here; `tools/check_gaps.py` and `tools/extract_netlist.py` remain the connectivity
  authorities, and `gen/board_routed_golden.kicad_pcb` the geometry one.
- `navigator/data/` is gitignored: `board.json` is generated, `state.json` is the live annotation
  state.

## What it is not evidence of

It draws the design, not the hardware. A part shown at a position is where the *fab package* put
it; whether that joint is good, that FET is healthy, or that site was reworked is a measurement,
not a lookup. Keep hardware findings in `docs/actual-bring-up.html` and the plan's decision log —
the navigator is where to *point at* a finding, never where to record one.
