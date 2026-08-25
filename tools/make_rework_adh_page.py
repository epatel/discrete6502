#!/usr/bin/env python3
"""Generate the address-path rework instructions, from the board rather than a drawing.

The eight dor sites were reworked by hand and it worked. A thermal camera then
found sixteen more carrying the identical 1:1 ratio defect -- the adh/adl
precharge drivers -- with nine of them measured at about 80 C on board #1 while
it executes real code. This emits the page for repairing them.

Everything on that page is derived here: positions from
gen/board_routed_golden.kicad_pcb, roles and gate loads from gen/netlist.json,
resistor value from the same series_r_for() rule the rev B generator uses, and
contention duty from tools/contention_duty.py. The per-site contact sheet is
cropped from the real top render at true relative scale.

Outputs:
  docs/img/rework-adh-sites.jpg   contact sheet, 16 crops with designators
  docs/rework-adh-series-r.html   the instructions

Usage:  python3 tools/make_rework_adh_page.py
"""
import json
import math
import os
import re
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mark_leds import fit_mapping, load_font  # noqa: E402

PCB = "gen/board_routed_golden.kicad_pcb"
NETLIST = "gen/netlist.json"
RENDER = "gen/board_top.png"
SHEET = "docs/img/rework-adh-sites.jpg"
PAGE = "docs/rework-adh-series-r.html"

# from tools/contention_duty.py: net -> (duty under real code, duty under NOPs)
DUTY = {
    "adh0": (33.7, 14.3), "adh1": (35.0, 0.3), "adh2": (35.3, 48.0),
    "adh3": (35.0, 0.3), "adh4": (35.3, 48.0), "adh5": (35.0, 0.3),
    "adh6": (35.0, 0.3), "adh7": (35.0, 0.3),
    "adl0": (19.3, 24.7), "adl1": (20.0, 25.7), "adl2": (39.0, 24.0),
    "adl3": (40.7, 23.0), "adl4": (15.3, 25.3), "adl5": (37.0, 21.7),
    "adl6": (45.7, 34.3), "adl7": (45.7, 34.3),
}
HOT = {"adh3", "adh4", "adh5", "adh6", "adh7", "adl4", "adl5", "adl6", "adl7"}

CISS_F = 27e-12
RISE_BUDGET = 5e-6
CHOICES = ((10000.0, "10k", "C25744"), (1000.0, "1k", "C11702"), (100.0, "100R", "C25076"))


def series_r_for(gate_count):
    """The same rule tools/gen_netlist.py uses, so the hand fix and a future
    rev B agree on the value instead of drifting apart."""
    cap = gate_count * CISS_F
    limit = RISE_BUDGET / (2.2 * cap) if cap else float("inf")
    for ohms, value, lcsc in CHOICES:
        if ohms <= limit:
            return value, lcsc
    return CHOICES[-1][1], CHOICES[-1][2]


def channel_net(c):
    a, b = c["pins"]["2"], c["pins"]["3"]
    return b if a in ("vss", "vcc") else a


def load_board():
    pos = {}
    txt = open(PCB, errors="ignore").read()
    for b in txt.split("(footprint ")[1:]:
        a = re.search(r"\(at ([-\d.]+) ([-\d.]+)", b)
        r = re.search(r'"Reference"\s+"([^"]+)"', b)
        l = re.search(r'\(layer "([^"]+)"', b)
        if a and r:
            pos[r.group(1)] = (float(a.group(1)), float(a.group(2)),
                               l.group(1) if l else "?")
    return pos


def collect(pos):
    nl = json.load(open(NETLIST))
    comps = nl["components"]
    gate_load = {}
    direct_pd = set()
    for c in comps:
        if c["type"] != "fet":
            continue
        gate_load[c["pins"]["1"]] = gate_load.get(c["pins"]["1"], 0) + 1
        if c.get("role") == "pulldown":
            direct_pd.add(channel_net(c))

    front = [(r, p) for r, p in pos.items() if p[2] == "F.Cu"]
    sites = []
    for c in comps:
        if c.get("role") != "vcc_side":
            continue
        net = channel_net(c)
        if net not in DUTY:
            continue
        ref = c["ref"]
        x, y, layer = pos[ref]
        nn = min(math.hypot(x - b[0], y - b[1]) for q, b in front if q != ref)
        gl = gate_load.get(net, 0)
        val, lcsc = series_r_for(gl)
        sites.append(dict(net=net, ref=ref, x=x, y=y, layer=layer, gates=gl,
                          value=val, lcsc=lcsc, nn=nn, duty=DUTY[net],
                          pin3=c["pins"]["3"], revb=net in direct_pd))
    sites.sort(key=lambda s: s["net"])
    assert len(sites) == len(DUTY), "found %d of %d" % (len(sites), len(DUTY))
    for s in sites:
        assert s["layer"] == "F.Cu", "%s is on %s" % (s["ref"], s["layer"])
        assert s["pin3"] == "vcc", "%s pin 3 is %s, not vcc" % (s["ref"], s["pin3"])
    return sites


def contact_sheet(sites):
    img = Image.open(RENDER).convert("RGB")
    (X0, Y0, sx, sy), _ = fit_mapping(img)
    HALF = 5.0          # mm each side of the part -> a 10 mm square view
    CELL = 340
    COLS = 4
    rows = (len(sites) + COLS - 1) // COLS
    pad, cap = 10, 46
    sheet = Image.new("RGB", (COLS * (CELL + pad) + pad,
                              rows * (CELL + cap + pad) + pad), (12, 14, 16))
    d0 = ImageDraw.Draw(sheet)
    f = load_font(23)
    fs = load_font(16)
    for i, s in enumerate(sites):
        cx, cy = X0 + s["x"] * sx, Y0 + s["y"] * sy
        dx, dy = HALF * sx, HALF * sy
        crop = img.crop((int(cx - dx), int(cy - dy), int(cx + dx), int(cy + dy)))
        crop = crop.resize((CELL, CELL), Image.LANCZOS)
        dd = ImageDraw.Draw(crop)
        # the part sits dead centre by construction; ring it
        r = int(CELL * 1.15 / (2 * HALF))
        col = (255, 70, 70) if s["net"] in HOT else (255, 176, 46)
        dd.ellipse([CELL // 2 - r, CELL // 2 - r, CELL // 2 + r, CELL // 2 + r],
                   outline=col, width=4)
        # Mark PIN 3 -- the leg to lift, and the only thing you need to identify
        # at the bench. SOT-323 pads are at (-0.8875, -0.65), (-0.8875, +0.65)
        # and (+0.8875, 0), read out of the board file; every FET is at 0
        # rotation, so pin 3 is always the lone pad on the RIGHT.
        ppx = CELL // 2 + int(0.8875 * CELL / (2 * HALF))
        ppy = CELL // 2
        a = int(CELL * 0.055)
        dd.line([ppx + 3 * a, ppy, ppx + a, ppy], fill=(255, 255, 255), width=4)
        dd.polygon([(ppx + a, ppy), (ppx + 2 * a, ppy - a // 2),
                    (ppx + 2 * a, ppy + a // 2)], fill=(255, 255, 255))
        dd.text((ppx + 3 * a + 5, ppy - 11), "pin 3", font=load_font(19),
                fill=(255, 255, 255))
        gx, gy = i % COLS, i // COLS
        px = pad + gx * (CELL + pad)
        py = pad + gy * (CELL + cap + pad)
        sheet.paste(crop, (px, py))
        d0.text((px + 2, py + CELL + 4), "%s   %s" % (s["net"], s["ref"]), font=f, fill=col)
        d0.text((px + 2, py + CELL + 26),
                "x %.1f  y %.1f   duty %.0f%%" % (s["x"], s["y"], s["duty"][0]),
                font=fs, fill=(170, 178, 188))
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    sheet.save(SHEET, quality=88, optimize=True)
    return sheet.size


CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin:0; font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
       background:#fff; color:#1a1a1c; }
.wrap { max-width: 54rem; margin: 0 auto; padding: 2rem 1.2rem 5rem; }
h1 { font-size:1.7rem; line-height:1.25; margin:0 0 .4rem; }
h2 { font-size:1.25rem; margin:2.4rem 0 .6rem; }
h3 { font-size:1.05rem; margin:1.6rem 0 .4rem; }
.sub { color:#666; margin:0 0 2rem; }
code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em;
       background:#f1f2f4; padding:.1em .35em; border-radius:3px; }
pre { background:#f1f2f4; padding:.9rem 1rem; border-radius:6px; overflow-x:auto; }
pre code { background:none; padding:0; }
table { border-collapse:collapse; width:100%; margin:1rem 0; font-size:.94rem; }
th,td { text-align:left; padding:.42rem .6rem; border-bottom:1px solid #e3e5e8; }
th { font-weight:600; color:#555; }
td.num { font-variant-numeric:tabular-nums; }
.hot { color:#c0392b; font-weight:600; }
.tw { overflow-x:auto; }
figure { margin:1.6rem 0; }
figure img { width:100%; height:auto; border-radius:6px; display:block; }
figcaption { color:#666; font-size:.9rem; margin-top:.45rem; }
.ok, .warn { border-left:3px solid #2e7d5b; background:#f3f8f6; padding:.9rem 1.1rem;
             border-radius:0 6px 6px 0; margin:1.4rem 0; }
.warn { border-left-color:#c0392b; background:#fdf4f3; }
ol li, ul li { margin:.45rem 0; }
a { color:#1668b8; }
@media (prefers-color-scheme: dark) {
  body { background:#151719; color:#e6e8ea; }
  .sub, figcaption, th { color:#9aa0a6; }
  code, pre { background:#20242a; }
  th,td { border-bottom-color:#2b3036; }
  .ok { background:#16211d; } .warn { background:#231719; }
  a { color:#6fb3f2; }
}
"""


def build_page(sites, sheet_size):
    hot = [s for s in sites if s["net"] in HOT]
    skipped = [s for s in sites if not s["revb"]]
    vals = sorted({s["value"] for s in sites})
    nn = min(s["nn"] for s in sites)

    rows = []
    for s in sites:
        cls = ' class="hot"' if s["net"] in HOT else ""
        rows.append(
            "<tr><td%s>%s</td><td>%s</td><td class=num>%.2f</td><td class=num>%.2f</td>"
            "<td class=num>%.1f%%</td><td class=num>%.1f%%</td><td>%s</td><td>%s</td></tr>"
            % (cls, s["net"], s["ref"], s["x"], s["y"], s["duty"][0], s["duty"][1],
               s["value"], "measured hot" if s["net"] in HOT else "—"))

    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rev A rework: the sixteen address-path drivers</title>
<meta name="description" content="Adding 10 k series resistors to the sixteen adh/adl precharge
drivers on the discrete6502 board: why, which parts, and the procedure.">
<style>%(css)s</style></head><body><div class="wrap">

<h1>Rev A rework: 10&nbsp;k&ohm; in series with the sixteen address-path drivers</h1>
<p class="sub">The same operation as
<a href="rework-dor-series-r.html">the eight data-bus drivers</a>, sixteen more times, on parts that
run hotter and are easier to reach. Generated from the board by
<code>tools/make_rework_adh_page.py</code>.</p>

<h2>Why</h2>
<p>The transform that turned the die's netlist into a board preserved every <em>connection</em> but
not every device <em>ratio</em>. Ratioed NMOS needs a weak load against a strong pull-down; the
1,018 depletion loads correctly became 10&nbsp;k&ohm; resistors, but <strong>164 VCC-side
transistors kept the same BSS138W as the transistor pulling against them</strong> &mdash; a fair
fight where the design needs a rigged one. A contended pair burns about 0.9&nbsp;W in a package
rated for 0.3&nbsp;W, and leaves a logic &ldquo;low&rdquo; at 1&ndash;1.9&nbsp;V against a
1.1&ndash;1.5&nbsp;V switching threshold.</p>

<p>Eight of those were repaired by hand and that repair is confirmed working. These sixteen are the
<strong>address-path precharge drivers</strong>, and they are worse: they are gated by
<code>cclk</code>, so they contend for a fixed fraction of <em>every</em> cycle rather than a
program-dependent one. <strong>Nine of them measured about 80&nbsp;&deg;C</strong> on board&nbsp;#1
with a thermal camera while it executed real code.</p>

<div class="warn">
<strong>They hid for a reason worth knowing.</strong> Contention here is workload-dependent. Five of
these contend 35%% of the time under a real program and <strong>0.3%% under a free-run of
NOPs</strong> &mdash; and a NOP free-run is exactly the condition an earlier thermal sweep was run
under, which is why that sweep found nothing and briefly retracted the whole model. Measure with the
CPU doing real work, not idling.
</div>

<h2>The sixteen sites</h2>
<p>Duty is measured by <code>tools/contention_duty.py</code>, which simulates the board under two
workloads and reports how often each VCC-side device is fighting its pull-down. All sixteen are on
the <strong>front face</strong>, all are SOT-323, and on all sixteen <strong>pin&nbsp;3 is the VCC
side</strong> &mdash; the same pin lifted on the data-bus eight.</p>

<div class="tw"><table>
<tr><th>net</th><th>ref</th><th>x&nbsp;(mm)</th><th>y&nbsp;(mm)</th>
    <th>duty, running</th><th>duty, NOPs</th><th>R</th><th>thermal</th></tr>
%(rows)s
</table></div>

<figure>
  <img src="img/rework-adh-sites.jpg" alt="Contact sheet of sixteen board crops, each 10 mm square,
       one per rework site, with the target transistor ringed and labelled by net and designator.">
  <figcaption>Each panel is a 10&nbsp;mm square of the real top-face render, centred on the part, with an arrow on <strong>pin&nbsp;3 &mdash; the leg to lift</strong>. Every FET on this board is at 0&deg; rotation, so pin&nbsp;3 is always the lone pad on the right.
  Red = measured hot; amber = same defect, not yet confirmed. The wider view with neighbouring
  designators is <a href="rework-adh-marked.jpg">here</a>.</figcaption>
</figure>

<h2>Same method, and slightly easier</h2>
<p>Identical to the data-bus eight: <strong>lift pin&nbsp;3 and bridge it back to its pad with a
10&nbsp;k&ohm; resistor.</strong> Pin&nbsp;3 is the lone pin on its side of the SOT-323,
1.78&nbsp;mm from the other two, so neither neighbour is at risk.</p>
<ul>
  <li><strong>Value: 10&nbsp;k&ohm; on all sixteen</strong> (%(vals)s). Each of these nets drives
      exactly <strong>one</strong> gate &mdash; 27&nbsp;pF &mdash; so the RC rise is about
      0.6&nbsp;&micro;s against a 25&nbsp;&micro;s half-cycle. This is computed with the same
      <code>series_r_for()</code> rule the rev&nbsp;B generator uses, so the hand fix and a future
      respin cannot drift apart. Do <em>not</em> generalise it: <code>cclk</code> drives 482 gates
      and needs 100&nbsp;&ohm;.</li>
  <li><strong>More room than last time.</strong> The nearest neighbouring part is
      <strong>%(nn).2f&nbsp;mm</strong> away, against 1.94&nbsp;mm at the data-bus sites.</li>
  <li><strong>0402 is what the board uses</strong> (LCSC C25744), but <strong>0603 is easier to
      handle</strong> and there is room for it.</li>
</ul>

<h2>Procedure, per site</h2>
<p>Tools: fine-tip iron or hot air, fine tweezers, flux, magnification, a multimeter, and Kapton
tape.</p>
<ol>
  <li><strong>Locate the part.</strong> Check the designator against the table and the contact sheet
      before touching anything &mdash; every neighbour is an identical SOT-323. Note the two
      clusters: <code>adh0&ndash;2</code> and <code>adl0&ndash;3</code> sit around
      x&nbsp;156&ndash;171&nbsp;mm, the rest around x&nbsp;200&ndash;205&nbsp;mm.</li>
  <li><strong>Measure first.</strong> Pin&nbsp;3 to a VCC bond pad should read ~0&nbsp;&ohm;. Record
      it; that is your &ldquo;before&rdquo;.</li>
  <li><strong>Lift pin&nbsp;3.</strong> Flux the joint, heat pad&nbsp;3, lift the leg clear with
      tweezers and bend it slightly upward. Do not disturb the body.</li>
  <li><strong>Verify the break.</strong> The lifted lead to VCC should now read open. If it still
      reads ~0&nbsp;&ohm; the leg is still touching &mdash; re-lift.</li>
  <li><strong>Fit the resistor.</strong> Tin pad&nbsp;3, stand the 10&nbsp;k&ohm; on end with its
      lower termination on the pad, solder it, then solder the lifted leg to the upper termination.
      <strong>Put a slip of Kapton tape between the resistor body and the lifted leg</strong>, as on
      the data-bus eight. The leg is springy and a leg that relaxes back shorts the resistor out
      <em>silently</em> &mdash; the board keeps working and simply runs hot again, which is the worst
      way for a repair to fail.</li>
  <li><strong>Verify the fix.</strong> The lifted lead to a VCC bond pad should now read
      <strong>10&nbsp;k&ohm; &plusmn; tolerance</strong>; pad&nbsp;3 itself to VCC should still read
      ~0&nbsp;&ohm;.</li>
  <li><strong>Inspect.</strong> Resistor clear of pins 1 and 2 and of every neighbour; lifted leg not
      touching the pad it came from.</li>
</ol>

<h2>Checking it worked</h2>
<div class="ok">
<p><strong>Thermal, not electrical, and take the &ldquo;before&rdquo; picture first.</strong> Run the
CPU on a real program &mdash; not NOPs, for the reason above &mdash; let it settle two or three
minutes, and photograph the two clusters. Repeat after the rework from the same camera position. The
nine hot sites should go cold.</p>
<p><strong>The supply current is the blunt version of the same test.</strong> Board&nbsp;#1 drew
2.3&nbsp;A executing before this rework. Note it before you start; a drop of several hundred mA is
what success looks like. Do not expect the few-hundred-mA figure early versions of these pages
predicted &mdash; there are 164 sites with this defect and this fixes sixteen.</p>
<p><strong>Whole-board check.</strong> VCC to VSS at the bond pads, read the <em>range-aware</em>
way: there is no resistor-only path between the rails, so a few hundred ohms that <em>changes with
the meter range</em> is correct and healthy. A fault is under 1&nbsp;&ohm;, or a reading that does
not move between ranges.</p>
</div>

<h2>If you are generating a rev&nbsp;B board instead</h2>
<div class="warn">
<p><strong><code>tools/gen_netlist.py</code> would currently skip %(nskip)d of these sixteen:
%(skipped)s.</strong> Its <code>has_pulldown</code> test only counts a transistor with vss directly
on a channel pin, and these nets are pulled low <em>through a pass-gate chain</em> instead. They
contend exactly the same way &mdash; <code>adl6</code> and <code>adl7</code> are the two busiest
sites on the whole board at 45.7%% &mdash; so a rev&nbsp;B respin generated today would leave the
hottest parts unfixed.</p>
<p>The same flawed test also excluded them from the first duty measurement, until a thermal camera
put them back. Fix <code>has_pulldown</code> to follow conduction paths before trusting rev&nbsp;B's
142-site count.</p>
</div>

</div></body></html>
""" % dict(css=CSS, rows="\n".join(rows), vals=", ".join(vals), nn=nn,
           nskip=len(skipped), skipped=", ".join("<code>%s</code>" % s["net"] for s in skipped))


def main():
    pos = load_board()
    sites = collect(pos)
    size = contact_sheet(sites)
    html = build_page(sites, size)
    open(PAGE, "w").write(html)
    print("wrote %s (%dx%d)" % (SHEET, size[0], size[1]))
    print("wrote %s (%d bytes)" % (PAGE, len(html)))
    print("\n%-5s %-7s %8s %8s %6s %-5s %s" % ("net", "ref", "x", "y", "duty", "R", "revB"))
    for s in sites:
        print("%-5s %-7s %8.2f %8.2f %5.1f%% %-5s %s%s"
              % (s["net"], s["ref"], s["x"], s["y"], s["duty"][0], s["value"],
                 "yes" if s["revb"] else "SKIPPED",
                 "   HOT" if s["net"] in HOT else ""))


if __name__ == "__main__":
    main()
