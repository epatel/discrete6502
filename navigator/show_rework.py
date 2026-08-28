#!/usr/bin/env python3
"""Apply a named part group to the running navigator from the shell.

The same thing the sidebar's Groups buttons do — both go through
`POST /api/group`, and both take their membership, colours and notes from
`navigator/groups.py`, so the page and the CLI cannot disagree.

    python3 navigator/show_rework.py                 # list the groups
    python3 navigator/show_rework.py rework-adh      # the 16 address sites
    python3 navigator/show_rework.py rework-dor      # the 8 data-out drivers
    python3 navigator/show_rework.py ballast-dnp --no-pins
    python3 navigator/show_rework.py --clear
"""
import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def api(base, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(base.rstrip("/") + path, data=body,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read() or b"{}")
    except HTTPError as e:
        return json.loads(e.read() or b'{"error":"http error"}')
    except URLError as e:
        raise SystemExit(f"navigator not reachable at {base} ({e.reason}).\n"
                         "Start it with:  python3 navigator/server.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("group", nargs="?")
    ap.add_argument("--url", default="http://127.0.0.1:8624")
    ap.add_argument("--no-pins", action="store_true",
                    help="highlight only, no per-part annotation markers")
    ap.add_argument("--no-goto", action="store_true")
    ap.add_argument("--zoom", type=float)
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()

    if a.clear:
        print(api(a.url, "/api/clear", dict(what="all")))
        return

    groups = api(a.url, "/api/groups")["groups"]
    if not a.group:
        for g in groups:
            flag = f"  !! {g['error']}" if g["error"] else ""
            print(f"  {g['id']:<14} {g['count']:>4} parts  {g['side']}  {g['desc']}{flag}")
        return

    if a.group not in {g["id"] for g in groups}:
        raise SystemExit(f"unknown group {a.group!r}; run with no argument to list them")

    r = api(a.url, "/api/group", dict(id=a.group, annotate=not a.no_pins,
                                      goto=not a.no_goto, zoom=a.zoom))
    if r.get("error"):
        raise SystemExit(r["error"])
    print(f"{r['id']}: {r['count']} parts highlighted, {r['pins']} pins")
    print("  " + " ".join(r["refs"]))


if __name__ == "__main__":
    main()
