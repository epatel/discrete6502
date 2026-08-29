# Board navigator (rev A)

An interactive map of the **fabricated rev A board**: the KiCad renders of both
faces with all **5,425 placed parts** overlaid at their true positions,
searchable by reference, net, role or value — and annotatable live over an HTTP
API, so an agent (or a second terminal) can point at a component while you are
looking at the board with a magnifier.

It exists because bring-up keeps asking the same question — *where on this
300 × 322 mm board is the thing I just found in the netlist?* — and the answer
used to be a one-off `tools/mark_*.py` script that baked a JPEG.  Those stay
useful for a printed page; this is the live version.

```
python3 navigator/server.py --open          # http://127.0.0.1:8624
```

First run builds `navigator/data/board.json` from `gen/layout.json` +
`gen/netlist.json` (about a second; needs PIL + numpy for the render fit).
Rebuild it by hand after any placement change:

```
python3 navigator/build_data.py
```

## The page

- **Top (F) / Bottom (B)** — the bottom render is drawn as seen from the back,
  so its x axis is mirrored; the navigator handles that, and the coordinate
  readout is always in **board** millimetres, matching `gen/netlist.json` and
  every `tools/mark_*.py` output.
- **Search** (`/` focuses it) — `Q2577`, `net:s0`, `role:vcc_side`,
  `type:led`, `value:10k`, `layer:b`, or free text; filters combine.
  A single match flies straight to the part.
- **Click a part** for value, role, position and every pin with its net; click
  a net name to list everything else on it.  *nearby parts* lists the twelve
  closest neighbours on the same face, which is what you can actually read
  under a magnifier when identifying a site.
- **Groups** — one click applies a named part set: highlight, a labelled pin per
  part where that helps, a note explaining what the set is, and the viewport
  framed to the set's own bounding box (and flipped to the right face).  Click
  the same group again to drop it.

  | group | | |
  |---|---|---|
  | `rework-adh` | 16 | adh0-7 + adl0-7 VCC-side FETs — 10k in series with pin 3 |
  | `rework-dor` | 8 | the 2026-08-01 data-out contention find, already reworked |
  | `vcc-side` | 164 | the whole ratio-defect population rev B fixes |
  | `leds` | 55 | register LEDs — A, X, Y, S, P, PCL, PCH |
  | `bond-pads` | 36 | the edge ring (four are in the wrong slot on rev A) |
  | `ballast-dnp` | 56 | empty 0402 pads on the six internal buses, back face |

  Membership is derived in `navigator/groups.py` — by role, gate net or channel
  net — never from a list of positions, and every group states the count it
  expects.  A group whose count has moved is disabled in the sidebar with the
  mismatch as its subtitle, rather than drawing a map that is quietly short a
  site.  The same definitions serve `POST /api/group` and the CLI, so the page
  and the shell cannot disagree.

- **+ pin** (or `p`) then click the board to drop an annotation.
- Keys: `f` fit · `t`/`b` side · `p` pin mode · `Esc` deselect.

Annotations, highlight and the note survive a restart (`navigator/data/state.json`).

## Driving it from an agent or a shell

`navctl.py` wraps the API; everything it does appears in the open page
immediately over the WebSocket, with no reload.

```bash
python3 navigator/show_rework.py                 # list the groups
python3 navigator/show_rework.py rework-adh      # apply one
python3 navigator/show_rework.py ballast-dnp --no-pins

python3 navigator/navctl.py find "net:s0"
python3 navigator/navctl.py part Q2577              # + its 8 neighbours
python3 navigator/navctl.py net s0

# point at something and fly there in one call
python3 navigator/navctl.py show Q2577 --label "leaky FET" \
        --text "20k gate-drain vs 177k on its twin" --color red --zoom 20

python3 navigator/navctl.py highlight --net s0 --label "S bit 0" --goto
python3 navigator/navctl.py highlight --query "role:vcc_side" --label "164 VCC-side FETs"
python3 navigator/navctl.py view --ref U1 --zoom 6
python3 navigator/navctl.py note "Stack fault" "Q2577 replaced from Q4050; S0 LED now dark."
python3 navigator/navctl.py clear all
```

### HTTP API

| Method | Path | Body / query |
|---|---|---|
| GET | `/api/board` | the whole part index (0.6 MB, what the page loads) |
| GET | `/api/state` | annotations, highlight, note, last view |
| GET | `/api/groups` | the named sets, with live counts and any mismatch |
| POST | `/api/group` | `{id, annotate:true, goto:true, zoom}` |
| GET | `/api/find?q=&limit=` | same query language as the search box |
| GET | `/api/part/<ref>` | one part plus its nearest neighbours |
| GET | `/api/net/<net>` | every pin on a net, with positions |
| POST | `/api/annotate` | `{ref|x,y, side, label, text, color, shape, r, w, h, id, goto, zoom}` |
| POST | `/api/annotations` | `{annotations:[…], replace:true}` — bulk |
| POST | `/api/highlight` | `{refs:[], nets:[], query, label, color, goto}` |
| POST | `/api/view` | `{ref|x,y, side, zoom}` |
| POST | `/api/note` | `{title, text}` |
| POST | `/api/clear` | `{what:"annotations"\|"highlight"\|"note"\|"all"}` |
| DELETE | `/api/annotation/<id>` | |
| WS | `/ws` | pushes `{type:"state", state:{…}}` on every change |

`shape` is `pin` (circle, default), `rect` (`w`/`h` mm) or `cross`; passing the
same `id` again updates a marker in place rather than adding a second one.

## How the picture is aligned

`build_data.py` fits each render to board millimetres by taking its non-black
bounding box as the board outline — the same method as
`tools/mark_leds.py:fit_mapping`, and it refuses the render if the aspect ratio
misses 290.7 / 322.0 by more than 1%.  The bottom render's mirroring is not
assumed: it was confirmed by the Pico site (board x 40, i.e. the left edge)
appearing on the right of that image.  Spot-checked against the render at high
zoom, part rectangles land on their footprints.

## Scope

Placement and connectivity only — this draws no copper.  Tracks, vias and zones
live in `gen/board_routed_golden.kicad_pcb`; for connectivity questions the
authorities remain `tools/check_gaps.py` and `tools/extract_netlist.py`.
Positions come from `gen/layout.json`, which is dumped from
`gen/discrete6502.kicad_pcb` by `tools/dump_layout.py` under KiCad's python.

## Deployment

A public copy runs at **https://ai.memention.net/d6502navigator/** — the same
page and the same API, served by nginx from a systemd unit on the `ai` host.

```
navigator/deploy.sh          # rsync + restart; HOST=ai by default
```

It ships `data/board.json` and the two renders as prebuilt artifacts, so the
server needs nothing but python3 stdlib — no KiCad, no PIL, no numpy.  Rebuild
`board.json` with `build_data.py` after any placement change, then redeploy.

**Reads are public; writes need a token.**  Anyone can pan, search, click parts
and open groups' read side, but `POST`/`DELETE` return 401 without the token,
which lives only on the server in `/etc/d6502navigator.env` (root, 0600) and is
passed to the service by systemd — never on a command line, where `ps` would
show it.  Drive the deployment the same way as a local one:

```
export NAV_URL=https://ai.memention.net/d6502navigator NAV_TOKEN=...
python3 navigator/navctl.py show Q2577 --label "leaky FET"
```

In a browser, `?key=<token>` turns the page from a read-only map into a full
controller; without it, an attempted annotation says so rather than failing
silently.

Serving under a prefix is handled by `--base /d6502navigator`: the server strips
it from every request and injects it into the page as `<body data-base>`, which
is where `app.js` gets the prefix for its own fetches and the WebSocket.  With
no `--base` the navigator is exactly what it was, at the root of its own port.
