#!/usr/bin/env python3
"""navctl — drive the board navigator from a shell (or from an agent).

Every command talks to a running `navigator/server.py` and the open page
updates immediately over its WebSocket.

    navctl find "net:s0"                        list matching parts
    navctl part Q2577                           one part plus its neighbours
    navctl net s0                               everything on a net
    navctl show Q2577 --label "leaky FET" \
                      --text "20k gate-drain" --color red
    navctl highlight --net s0 --label "S bit 0" --goto
    navctl highlight --query "role:vcc_side layer:f" --label "VCC-side FETs"
    navctl view --ref Q2577 --zoom 14
    navctl note "Stack fault" "Q2577 replaced from Q4050; S0 LED now dark."
    navctl clear [annotations|highlight|note|all]

`show` is the one to reach for while talking someone through the board: it
drops a labelled pin on the part and flies the viewport there in one call.
"""
import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COLORS = dict(red="#ff4757", yellow="#ffd23f", cyan="#3fd0ff",
              green="#7bed9f", violet="#c792ff", orange="#e2653f")


def call(base, path, data=None, method=None):
    url = base.rstrip("/") + path
    if isinstance(data, dict):                     # None means "not supplied"
        data = {k: v for k, v in data.items() if v is not None}
    body = json.dumps(data).encode() if data is not None else None
    req = Request(url, data=body, method=method or ("POST" if data is not None else "GET"),
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b"{}")
    except HTTPError as e:
        return json.loads(e.read() or b'{"error":"http error"}')
    except URLError as e:
        raise SystemExit(f"navigator not reachable at {base} ({e.reason}).\n"
                         f"Start it with:  python3 navigator/server.py")


def color(c):
    return COLORS.get(c, c)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8624")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("find"); p.add_argument("query"); p.add_argument("--limit", type=int, default=25)
    p = sub.add_parser("part"); p.add_argument("ref")
    p = sub.add_parser("net"); p.add_argument("net")

    p = sub.add_parser("show", help="pin a part and fly there")
    p.add_argument("ref"); p.add_argument("--label", default=""); p.add_argument("--text", default="")
    p.add_argument("--color", default="red"); p.add_argument("--shape", default="pin")
    p.add_argument("--zoom", type=float); p.add_argument("--id")
    p.add_argument("--no-goto", action="store_true")

    p = sub.add_parser("pin", help="pin a bare coordinate")
    p.add_argument("x", type=float); p.add_argument("y", type=float)
    p.add_argument("--side", default="F"); p.add_argument("--label", default="")
    p.add_argument("--text", default=""); p.add_argument("--color", default="red")

    p = sub.add_parser("highlight")
    p.add_argument("--refs", default=""); p.add_argument("--net", action="append", default=[])
    p.add_argument("--query", default=""); p.add_argument("--label", default="")
    p.add_argument("--color", default="yellow"); p.add_argument("--goto", action="store_true")
    p.add_argument("--zoom", type=float)

    p = sub.add_parser("view")
    p.add_argument("--ref"); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p.add_argument("--side"); p.add_argument("--zoom", type=float)

    p = sub.add_parser("note"); p.add_argument("title"); p.add_argument("text")
    p = sub.add_parser("clear"); p.add_argument("what", nargs="?", default="all")
    sub.add_parser("state")

    a = ap.parse_args()
    u = a.url

    if a.cmd == "find":
        r = call(u, f"/api/find?limit={a.limit}&q=" + a.query.replace(" ", "%20"))
        print(f"{r['count']} match(es) for {r['query']!r}")
        for p in r["parts"]:
            nets = " ".join(f"{k}={v}" for k, v in (p["pins"] or {}).items())
            print(f"  {p['ref']:<8} {p['value']:<12} {p['role']:<12} "
                  f"{p['layer']} x{p['x']:7.2f} y{p['y']:7.2f}  {nets}")
        return

    if a.cmd == "part":
        r = call(u, "/api/part/" + a.ref)
        if r.get("error"):
            raise SystemExit(r["error"])
        print(json.dumps(r, indent=2))
        return

    if a.cmd == "net":
        r = call(u, "/api/net/" + a.net)
        if r.get("error"):
            raise SystemExit(r["error"])
        print(f"net {r['net']}: {r['count']} pin(s)")
        for m in r["members"][:60]:
            print(f"  {m['ref']:<8} pin {m['pin']}  {m['role']:<12} {m['layer']} "
                  f"x{m['x']:7.2f} y{m['y']:7.2f}")
        if r["count"] > 60:
            print(f"  … {r['count'] - 60} more")
        return

    if a.cmd == "show":
        r = call(u, "/api/annotate", dict(
            ref=a.ref, label=a.label or a.ref, text=a.text, color=color(a.color),
            shape=a.shape, id=a.id, goto=not a.no_goto, zoom=a.zoom))
    elif a.cmd == "pin":
        r = call(u, "/api/annotate", dict(
            x=a.x, y=a.y, side=a.side, label=a.label, text=a.text,
            color=color(a.color), goto=True))
    elif a.cmd == "highlight":
        r = call(u, "/api/highlight", dict(
            refs=[s for s in a.refs.replace(",", " ").split() if s],
            nets=a.net, query=a.query, label=a.label, color=color(a.color),
            goto=a.goto, zoom=a.zoom))
    elif a.cmd == "view":
        r = call(u, "/api/view", dict(ref=a.ref, x=a.x, y=a.y, side=a.side, zoom=a.zoom)
                 if (a.ref or a.x is not None) else dict(side=a.side or "F", zoom=a.zoom))
    elif a.cmd == "note":
        r = call(u, "/api/note", dict(title=a.title, text=a.text))
    elif a.cmd == "clear":
        r = call(u, "/api/clear", dict(what=a.what))
    elif a.cmd == "state":
        r = call(u, "/api/state")
    print(json.dumps(r, indent=2)[:2000])


if __name__ == "__main__":
    sys.exit(main())
