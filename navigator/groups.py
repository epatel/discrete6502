#!/usr/bin/env python3
"""Named part groups — the sets bring-up keeps coming back to.

One definition, used by the sidebar buttons, by `POST /api/group` and by
`navigator/show_rework.py`, so the duty figures and the red/amber meaning
cannot drift between the page and the CLI.

Membership is always *derived* from the netlist index — by role, by gate net or
by channel net — never from a list of positions.  Each resolver returns the
refs it found and the count it expected, and the server refuses a group whose
count has moved rather than drawing a map that is quietly short a site.
"""

# net -> (duty under real code, duty under a NOP free-run), tools/contention_duty.py.
# The NOP column pinned the address, so 0.3% there means "quiet at THAT
# address", not "quiet" — every one of the sixteen contends in normal use
# (2026-08-26 correction).
ADH_DUTY = {
    "adh0": (33.7, 14.3), "adh1": (35.0, 0.3), "adh2": (35.3, 48.0),
    "adh3": (35.0, 0.3), "adh4": (35.3, 48.0), "adh5": (35.0, 0.3),
    "adh6": (35.0, 0.3), "adh7": (35.0, 0.3),
    "adl0": (19.3, 24.7), "adl1": (20.0, 25.7), "adl2": (39.0, 24.0),
    "adl3": (40.7, 23.0), "adl4": (15.3, 25.3), "adl5": (37.0, 21.7),
    "adl6": (45.7, 34.3), "adl7": (45.7, 34.3),
}
# Measured at ~80 C with a FLIR on board #1, 2026-08-25.
ADH_HOT = {"adh3", "adh4", "adh5", "adh6", "adh7", "adl4", "adl5", "adl6", "adl7"}

# The eight data-out drivers, by their GATE net — the 2026-08-01 finding.
# Duty from tools/switchsim.py; all eight are reworked on board #1.
DOR_DUTY = {f"dor{i}": d for i, d in enumerate((47, 90, 85, 89, 84, 93, 88, 87))}

RED, AMBER, CYAN, YELLOW, VIOLET, GREEN = (
    "#ff4757", "#ffb02e", "#3fd0ff", "#ffd23f", "#c792ff", "#7bed9f")


def channel_net(pins):
    """Whichever of pins 2/3 is not a rail.  The two FET roles use opposite
    conventions, so asking which pin IS the rail is the only safe reading."""
    a, b = pins.get("2", ""), pins.get("3", "")
    return b if a in ("vss", "vcc") else a


def _by_role(index, role):
    return [p for p in index.values() if p["role"] == role]


# --------------------------------------------------------------- resolvers

def _rework_adh(index):
    sites = []
    for p in _by_role(index, "vcc_side"):
        net = channel_net(p["pins"])
        if net in ADH_DUTY:
            sites.append((net, p))
    sites.sort(key=lambda s: s[0])
    anns = []
    for net, p in sites:
        duty, nop = ADH_DUTY[net]
        hot = net in ADH_HOT
        anns.append(dict(
            ref=p["ref"], id=f"rw-{net}", label=f"{net} · {p['ref']}",
            color=RED if hot else AMBER, shape="circle", r=2.2,
            text=(f"{p['ref']} pin 3 -> 10k in series.\n"
                  f"duty {duty:.1f}% under real code, {nop:.1f}% at a pinned address.\n"
                  + ("measured ~80 C on board #1 (FLIR 2026-08-25)."
                     if hot else "same defect; not yet confirmed hot."))))
    note = ("10k in series with pin 3 — the operation already proven on the dor eight.\n\n"
            "RED    measured hottest on board #1 (FLIR, 2026-08-25)\n"
            "AMBER  same ratio defect, not yet confirmed hot\n\n"
            "All 16 are on the TOP face, in two clusters ~40 mm apart. adl6/adl7 are "
            "the busiest sites on the board at 45.7%.\n"
            "Source: tools/mark_rework_adh.py + tools/contention_duty.py.")
    return [p["ref"] for _, p in sites], anns, note


def _rework_dor(index):
    sites = []
    for p in _by_role(index, "vcc_side"):
        gate = p["pins"].get("1", "")
        if gate in DOR_DUTY:
            sites.append((gate, p))
    sites.sort(key=lambda s: s[0])
    anns = [dict(ref=p["ref"], id=f"rw-{net}", label=f"{net} · {p['ref']}",
                 color=RED, shape="circle", r=2.2,
                 text=(f"{p['ref']} pin 3 -> 10k in series (done on board #1).\n"
                       f"contended {DOR_DUTY[net]}% of the time — switchsim, 2026-08-01."))
            for net, p in sites]
    note = ("The eight data-out drivers found on 2026-08-01: RnWstretched holds the "
            "pull-down on through every read while a stale dor bit holds the pull-up "
            "on. 262 mA and 0.90 W per contended net before the rework, and a "
            "contended node at 1.0-1.9 V against a 1.1-1.5 V threshold — the level "
            "was always the serious half, not the heat.\n\n"
            "One column on the TOP face at x 216-219, 11-14 mm apart. All eight are "
            "already reworked on board #1.")
    return [p["ref"] for _, p in sites], anns, note


def _ballast(index):
    parts = sorted(_by_role(index, "ballast_dnp"), key=lambda p: p["ref"])
    note = ("C101-C156: one bare 0402 pad pair per bit of the six internal buses "
            "(sb 8, idb 8, adl 8, adh 8, db 8, ab 16), bit -> vss, back face.\n\n"
            "Value 100pF-DNP and no LCSC part number, so assembly could not fit them. "
            "Held in reserve: if a dynamic bus bit picks up clock-edge injection at "
            "bring-up, hand-solder 100pF on that one bit instead of respinning.\n\n"
            "Do not fit one speculatively — added C on a dynamic node slows the "
            "pass-gate rise and eats top-end clock margin, and the measured retention "
            "floor (456-871 Hz) needs no help.")
    return [p["ref"] for p in parts], [], note


def _leds(index):
    parts = [p for p in index.values() if p["type"] == "led"]
    parts.sort(key=lambda p: p["role"])
    note = ("55 register LEDs — A, X, Y, S, P flags, PCL, PCH — each buffered by its "
            "own gate-tap driver FET so the tap cannot load the node it watches.\n\n"
            "These are the only view of the CPU's internal state that needs no "
            "instrument: A/X/Y/S/P/PC are invisible from the bond-pad ring, which is "
            "why bus LEDs were rejected and these were kept.")
    return [p["ref"] for p in parts], [], note


def _bond_pads(index):
    parts = sorted(_by_role(index, "edge_pad"), key=lambda p: p["ref"])
    note = ("The 36-pad die-mimicry ring — every CPU signal, croc-clip usable.\n\n"
            "REV A DEFECT: A6, VSS, D7 and R/W sit in the wrong slot, which puts "
            "A0-A5 one slot down from where the die says they should be. Nothing is "
            "miswired or mislabelled — every pad carries the net its silk names — so "
            "locate a pad BY ITS LABEL, never by counting positions.\n"
            "See cards/bond-pad-ring.md.")
    return [p["ref"] for p in parts], [], note


def _precharge(index, bus):
    """The cclk-gated precharge devices for one internal bus.

    Same 1:1 ratio defect as every other vcc_side FET, and the same fix, but
    these were never in the adh/adl rework set -- which is why the idb column
    was found at 80+ C on 2026-08-29 AFTER that rework was done. Their gate is
    cclk, so with the clock stopped high they all conduct at once: eight of
    them at the simulated 262 mA is 2.1 A, which is the order of the whole
    board's unexplained draw.
    """
    hits = []
    for p in _by_role(index, "vcc_side"):
        if p["pins"].get("1") != "cclk":
            continue
        ch = channel_net(p["pins"])
        if ch.startswith(bus) and ch[len(bus):].isdigit():
            hits.append((int(ch[len(bus):]), ch, p))
    hits.sort()
    anns = [dict(ref=p["ref"], id=f"pc-{ch}", label=f"{ch} · {p['ref']}",
                 color=RED, shape="circle", r=2.2,
                 text=(f"{p['ref']} pin 3 -> 10k in series.\n"
                       f"cclk-gated precharge for {ch}; contends whenever cclk is "
                       f"high and the bus bit is pulled low.\n"
                       "NOT part of the adh/adl rework."))
            for _, ch, p in hits]
    note = (f"The {len(hits)} cclk-gated precharge FETs for the {bus} bus.\n\n"
            "Same ratio defect and same fix as the adh/adl sixteen -- 10k in series "
            "with pin 3 -- but they were never in that rework set. Found at 80+ C "
            "on 2026-08-29, in a column, with the adh/adl rework already done.\n\n"
            "Their gate is cclk, so a stopped clock parked high turns all of them on "
            "at once against whatever holds the bus low. Eight at the simulated "
            "262 mA is 2.1 A.")
    return [p["ref"] for _, _, p in hits], anns, note


def _vcc_side(index):
    parts = sorted(_by_role(index, "vcc_side"), key=lambda p: p["ref"])
    note = ("All 164 enhancement-mode VCC-side FETs — the ratio defect population.\n\n"
            "The transform preserved topology but not device ratios: the 1,018 "
            "depletion loads became 10k resistors, but these 164 kept the same "
            "BSS138W as their pull-down, a 1:1 ratio where the die had a deliberately "
            "weak load. Every one has exactly one pull-up FET against its pull-downs, "
            "so the defect is uniform and rev B fixes all 164 (not 142 — the "
            "has_pulldown filter missed nets pulled low through a pass-gate chain).\n\n"
            "24 of them are the rework groups above.")
    return [p["ref"] for p in parts], [], note


GROUPS = [
    dict(id="rework-adh", label="Address rework (16)", color=RED, expect=16,
         desc="adh0-7 + adl0-7 VCC-side FETs — 10k in series with pin 3",
         resolve=_rework_adh, side="F"),
    dict(id="rework-dor", label="Data-out rework (8)", color=RED, expect=8,
         desc="dor0-7 drivers — the 2026-08-01 contention find, already reworked",
         resolve=_rework_dor, side="F"),
    dict(id="precharge-idb", label="idb precharge (8)", color=RED, expect=8,
         desc="cclk-gated idb0-7 precharge — hot on 2026-08-29, NOT yet reworked",
         resolve=lambda ix: _precharge(ix, "idb"), side="F"),
    dict(id="precharge-sb", label="sb precharge (8)", color=AMBER, expect=8,
         desc="cclk-gated sb0-7 precharge — same defect, same fix, also unreworked",
         resolve=lambda ix: _precharge(ix, "sb"), side="F"),
    dict(id="vcc-side", label="VCC-side FETs (164)", color=AMBER, expect=164,
         desc="the whole ratio-defect population rev B fixes",
         resolve=_vcc_side, side="F"),
    dict(id="leds", label="Register LEDs (55)", color=VIOLET, expect=55,
         desc="A, X, Y, S, P, PCL, PCH — the only view of internal state",
         resolve=_leds, side="F"),
    dict(id="bond-pads", label="Bond pads (36)", color=YELLOW, expect=36,
         desc="the edge ring — four are in the wrong slot on rev A",
         resolve=_bond_pads, side="F"),
    dict(id="ballast-dnp", label="DNP ballast pads (56)", color=CYAN, expect=56,
         desc="empty 0402 pads on the six internal buses, bring-up insurance",
         resolve=_ballast, side="B"),
]

BY_ID = {g["id"]: g for g in GROUPS}


def resolve(gid, index):
    """Return (group, refs, annotations, note).  Raises if the count moved."""
    g = BY_ID.get(gid)
    if not g:
        raise KeyError(f"unknown group {gid}")
    refs, anns, note = g["resolve"](index)
    if len(refs) != g["expect"]:
        raise ValueError(f"group {gid}: found {len(refs)} parts, expected "
                         f"{g['expect']} — the netlist or the group table has moved")
    return g, refs, anns, note
