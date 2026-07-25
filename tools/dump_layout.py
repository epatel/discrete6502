#!/usr/bin/env python3
"""Dump footprint placement from the board to gen/layout.json for the HTML
layout previewer. Run with KiCad's bundled python after gen_pcb.py."""
import json
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
board = pcbnew.LoadBoard(str(ROOT / "gen" / "discrete6502.kicad_pcb"))

roles = {c["ref"]: c["role"] for c in json.loads(
    (ROOT / "gen" / "netlist.json").read_text())["components"]}

items = []
def body_size(fp):
    """true physical size: fab-layer outline if present, else pads+margin"""
    import collections
    e = [1e9, 1e9, -1e9, -1e9]
    for g in fp.GraphicalItems():
        if pcbnew.BOARD.GetStandardLayerName(g.GetLayer()) in ("F.Fab", "B.Fab"):
            bb = g.GetBoundingBox()
            e[0] = min(e[0], bb.GetLeft()); e[1] = min(e[1], bb.GetTop())
            e[2] = max(e[2], bb.GetRight()); e[3] = max(e[3], bb.GetBottom())
    for pad in fp.Pads():  # copper counts toward the visible body too
        bb = pad.GetBoundingBox()
        e[0] = min(e[0], bb.GetLeft()); e[1] = min(e[1], bb.GetTop())
        e[2] = max(e[2], bb.GetRight()); e[3] = max(e[3], bb.GetBottom())
    if e[0] > 8e8:
        return fp.GetBoundingBox(False)
    return pcbnew.BOX2I(pcbnew.VECTOR2I(int(e[0]), int(e[1])),
                        pcbnew.VECTOR2I(int(e[2] - e[0]), int(e[3] - e[1])))


for fp in board.Footprints():
    p = fp.GetPosition()
    bb = body_size(fp)
    items.append(dict(
        ref=fp.GetReference(),
        value=fp.GetValue(),
        role=roles.get(fp.GetReference(), ""),
        layer="F" if fp.GetLayer() == pcbnew.F_Cu else "B",
        x=round(p.x / 1e6, 3), y=round(p.y / 1e6, 3),
        w=round(bb.GetWidth() / 1e6, 2), h=round(bb.GetHeight() / 1e6, 2),
        rot=fp.GetOrientationDegrees(),
        dnp=fp.IsDNP()))

bbox = board.GetBoardEdgesBoundingBox()
out = dict(board_w=round(bbox.GetWidth() / 1e6, 1),
           board_h=round(bbox.GetHeight() / 1e6, 1),
           items=items)
(ROOT / "gen" / "layout.json").write_text(json.dumps(out))
print("wrote gen/layout.json:", len(items), "items")
