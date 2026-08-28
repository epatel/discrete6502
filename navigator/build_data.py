#!/usr/bin/env python3
"""Build navigator/data/board.json — everything the page needs about rev A.

Merges the placement dump (gen/layout.json) with the electrical netlist
(gen/netlist.json) and fits the two board renders to board millimetres, so a
component's position on screen is derived from the board file rather than from
a guess about the picture.

The renders are the board outline on a black field, so their non-black bounding
box IS the outline (same trick as tools/mark_leds.py:fit_mapping, and the
aspect ratio is checked before it is trusted).  board_bottom.png is drawn as
seen from the back, so its x axis runs the other way — verified by the Pico
site (board x 40, i.e. left) appearing on the right of that render.

Run:  python3 navigator/build_data.py      (plain python3; no KiCad needed)
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAV = ROOT / "navigator"
OUT = NAV / "data" / "board.json"

BOARD_W, BOARD_H = 290.7, 322.0          # gen/layout_params.json "board"

SIDES = {
    "F": dict(file="board_top.png", mirror=False),
    "B": dict(file="board_bottom.png", mirror=True),
}


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(33)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def fit_render(path):
    """Return (x0, y0, x1, y1) pixel box of the board outline in the render."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        w, h = png_size(path)
        print(f"  ! PIL/numpy missing — assuming {path.name} is edge-to-edge")
        return [0, 0, w - 1, h - 1]
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    ys, xs = np.where(a.sum(axis=2) > 60)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    aspect, want = (x1 - x0 + 1) / (y1 - y0 + 1), BOARD_W / BOARD_H
    if abs(aspect - want) / want > 0.01:
        raise SystemExit(f"{path.name}: aspect {aspect:.4f} != board {want:.4f} "
                         "— not a plain flat view, refusing to guess a mapping")
    return [x0, y0, x1, y1]


def main():
    layout = json.loads((ROOT / "gen" / "layout.json").read_text())
    net = json.loads((ROOT / "gen" / "netlist.json").read_text())

    elec = {c["ref"]: c for c in net["components"]}

    parts = []
    for it in layout["items"]:
        c = elec.get(it["ref"], {})
        parts.append([
            it["ref"],
            it["value"],
            c.get("type", ""),
            it.get("role", "") or c.get("role", ""),
            it["layer"],
            it["x"], it["y"], it["w"], it["h"], it.get("rot", 0.0),
            1 if it.get("dnp") else 0,
            c.get("origin", ""),
            c.get("pins", {}),
        ])
    parts.sort(key=lambda p: (p[0][0], int("".join(ch for ch in p[0] if ch.isdigit()) or 0)))

    images = {}
    for side, spec in SIDES.items():
        path = ROOT / "gen" / spec["file"]
        if not path.exists():
            print(f"  ! {spec['file']} missing — side {side} will render vector-only")
            continue
        w, h = png_size(path)
        images[side] = dict(file=spec["file"], w=w, h=h, mirror=spec["mirror"],
                            box=fit_render(path))
        print(f"  {spec['file']}: {w}x{h}, board box {images[side]['box']}")

    data = dict(
        schema=["ref", "value", "type", "role", "layer", "x", "y", "w", "h",
                "rot", "dnp", "origin", "pins"],
        board=dict(w=BOARD_W, h=BOARD_H),
        images=images,
        parts=parts,
        stats=net["meta"].get("stats", {}),
        rev="A",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(parts)} parts, "
          f"{OUT.stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    sys.exit(main())
