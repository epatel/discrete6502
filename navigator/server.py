#!/usr/bin/env python3
"""Board navigator — a local map of the fabricated rev A board.

Serves an interactive top/bottom view of gen/board_{top,bottom}.png with every
one of the 5,425 placed parts overlaid at its true position, searchable by
reference, net, role or value, and annotatable live over an HTTP API so an
agent can point at a component while you are looking at the board.

    python3 navigator/server.py            # http://127.0.0.1:8624
    python3 navigator/server.py 9000 --open

API (all JSON; see navigator/README.md for the full list and navctl.py for a
CLI wrapper).  Every mutation is broadcast to open pages over the /ws
WebSocket, so the browser updates without a reload.

    POST /api/annotate     add or update one marker
    POST /api/highlight    light up parts by ref or by net
    POST /api/view         fly the viewport to a part or a coordinate
    POST /api/note         set the side-panel note
    POST /api/clear        drop annotations / highlight / note
    GET  /api/find?q=...   query the part index without a browser
"""
import base64
import hashlib
import json
import os
import re
import struct
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import groups as GROUPS  # noqa: E402  (named part sets — see groups.py)

ROOT = Path(__file__).resolve().parent.parent
NAV = Path(__file__).resolve().parent
STATIC = NAV / "static"
DATA = NAV / "data" / "board.json"
STATE_FILE = NAV / "data" / "state.json"

# Set by main() when the navigator is served under a URL prefix (a reverse
# proxy that preserves the path, e.g. nginx `proxy_pass .../d6502navigator/`).
# Empty means "served at the root", which is the local default.
BASE = ""
# When set, POST/DELETE require it in X-Nav-Token or ?key=.  Reads stay open,
# so a public deployment is a live map for everyone and writable only by us.
TOKEN = ""

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# ---------------------------------------------------------------- board data

_board = None
_index = {}          # ref -> part dict
_nets = {}           # net -> [(ref, pin), ...]


def load_board():
    global _board, _index, _nets
    if not DATA.exists():
        print("data/board.json missing — running build_data.py")
        os.system(f'"{sys.executable}" "{NAV / "build_data.py"}"')
    _board = json.loads(DATA.read_text())
    keys = _board["schema"]
    _index, _nets = {}, {}
    for row in _board["parts"]:
        p = dict(zip(keys, row))
        _index[p["ref"]] = p
        for pin, net in (p["pins"] or {}).items():
            _nets.setdefault(net, []).append((p["ref"], pin))
    print(f"loaded {len(_index)} parts, {len(_nets)} nets")


# --------------------------------------------------------------- live state

DEFAULT_STATE = dict(annotations=[], highlight=dict(refs=[], label="", color="#ffd23f"),
                     note=dict(title="", text=""), view=None, side="F", seq=0)
state = dict(DEFAULT_STATE)
state_lock = threading.Lock()
clients = []             # list of connected websocket sockets
clients_lock = threading.Lock()


def save_state():
    try:
        STATE_FILE.write_text(json.dumps(state))
    except OSError as e:
        print("state save failed:", e)


def load_state():
    global state
    if STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text())
            merged = dict(DEFAULT_STATE)
            merged.update(s)
            state = merged
        except (OSError, ValueError):
            pass


def bump_and_broadcast():
    """Call with state_lock held."""
    state["seq"] += 1
    save_state()
    payload = json.dumps(dict(type="state", state=state))
    broadcast(payload)


# ---------------------------------------------------------------- websocket

def ws_frame(text):
    data = text.encode()
    n = len(data)
    if n < 126:
        head = struct.pack("!BB", 0x81, n)
    elif n < (1 << 16):
        head = struct.pack("!BBH", 0x81, 126, n)
    else:
        head = struct.pack("!BBQ", 0x81, 127, n)
    return head + data


def broadcast(text):
    frame = ws_frame(text)
    with clients_lock:
        dead = []
        for c in clients:
            try:
                c.sendall(frame)
            except OSError:
                dead.append(c)
        for c in dead:
            clients.remove(c)
            try:
                c.close()
            except OSError:
                pass


def ws_read_loop(conn):
    """Consume client frames so pings and closes are handled; ignore payloads."""
    conn.settimeout(None)
    f = conn.makefile("rb")
    while True:
        head = f.read(2)
        if len(head) < 2:
            return
        b1, b2 = head[0], head[1]
        opcode, masked, ln = b1 & 0x0F, b2 & 0x80, b2 & 0x7F
        if ln == 126:
            ln = struct.unpack("!H", f.read(2))[0]
        elif ln == 127:
            ln = struct.unpack("!Q", f.read(8))[0]
        mask = f.read(4) if masked else b""
        payload = f.read(ln) if ln else b""
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:                      # close
            return
        if opcode == 0x9:                      # ping -> pong
            try:
                conn.sendall(struct.pack("!BB", 0x8A, len(payload)) + payload)
            except OSError:
                return


# ------------------------------------------------------------------ queries

QUERY_RE = re.compile(r"(\w+):(\S+)")


def find(q, limit=200):
    """Query the part index.  Supports free text plus key:value filters —
    net:, role:, type:, value:, layer:, ref:.  Free text matches ref, value,
    role, origin and any attached net name."""
    q = (q or "").strip()
    filters = {k.lower(): v.lower() for k, v in QUERY_RE.findall(q)}
    text = QUERY_RE.sub("", q).strip().lower()

    hits = []
    for p in _index.values():
        nets = list((p["pins"] or {}).values())
        low_nets = [n.lower() for n in nets]
        if "net" in filters and filters["net"] not in low_nets:
            continue
        if "role" in filters and filters["role"] not in p["role"].lower():
            continue
        if "type" in filters and filters["type"] != p["type"].lower():
            continue
        if "value" in filters and filters["value"] not in p["value"].lower():
            continue
        if "layer" in filters and filters["layer"] != p["layer"].lower():
            continue
        if "ref" in filters and filters["ref"] not in p["ref"].lower():
            continue
        if text:
            hay = " ".join([p["ref"], p["value"], p["role"], p["type"],
                            p["origin"]] + nets).lower()
            if text not in hay:
                continue
        hits.append(p)
        if len(hits) > 5000:
            break

    def rank(p):
        exact = 0 if p["ref"].lower() == text else 1
        return (exact, len(p["ref"]), p["ref"])

    hits.sort(key=rank)
    return hits[:limit]


def slim(p):
    return {k: p[k] for k in ("ref", "value", "type", "role", "layer",
                              "x", "y", "rot", "dnp", "origin", "pins")}


# --------------------------------------------------------------- annotation

def resolve_point(d):
    """Accept {ref:...} or {x:..,y:..[,side:..]} and return (x, y, side)."""
    if d.get("ref"):
        p = _index.get(d["ref"])
        if not p:
            raise ValueError(f"unknown ref {d['ref']}")
        return p["x"], p["y"], d.get("side") or p["layer"]
    if "x" in d and "y" in d:
        return float(d["x"]), float(d["y"]), d.get("side", "F")
    raise ValueError("need ref, or x and y")


def make_annotation(d):
    x, y, side = resolve_point(d)
    aid = d.get("id") or f"a{int(time.time()*1000)%100000000}"
    return dict(
        id=str(aid), x=x, y=y, side=side,
        ref=d.get("ref", ""),
        label=str(d.get("label", "")),
        text=str(d.get("text", "")),
        color=d.get("color", "#ff4757"),
        shape=d.get("shape", "pin"),      # pin | circle | rect | cross
        r=float(d.get("r", 3.0)),
        w=float(d.get("w", 4.0)),
        h=float(d.get("h", 4.0)),
        created=time.strftime("%H:%M:%S"),
    )


# ------------------------------------------------------------------- server

def strip_base(path):
    """The request path with the deployment prefix removed, or None if the
    request fell outside it (which a correctly configured proxy never does)."""
    if not BASE:
        return path
    if path == BASE:
        return "/"
    if path.startswith(BASE + "/"):
        return path[len(BASE):]
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "boardnav"

    # -- plumbing ---------------------------------------------------------
    def _send(self, body, ctype="application/json", code=200, extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj), "application/json", code)

    def _file(self, path, ctype):
        if not path.exists():
            return self._send("not found", "text/plain", 404)
        self._send(path.read_bytes(), ctype)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n) or b"{}")

    def _authorized(self):
        """Reads are public; mutations need the token when one is configured."""
        if not TOKEN:
            return True
        given = self.headers.get("X-Nav-Token") or \
            (parse_qs(urlparse(self.path).query).get("key") or [""])[0]
        return given == TOKEN

    def log_message(self, fmt, *args):
        if os.environ.get("NAV_VERBOSE"):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # -- GET --------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        path, qs = strip_base(u.path), parse_qs(u.query)
        if path is None:
            return self._send("not found", "text/plain", 404)

        if path == "/ws":
            return self.do_websocket()
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text(encoding="utf-8")
            html = html.replace('data-base=""', f'data-base="{BASE}"')
            return self._send(html, "text/html; charset=utf-8")
        if path == "/app.js":
            return self._file(STATIC / "app.js", "text/javascript")
        if path == "/style.css":
            return self._file(STATIC / "style.css", "text/css")
        if path == "/api/board":
            return self._file(DATA, "application/json")
        if path == "/api/state":
            with state_lock:
                return self._json(state)
        if path.startswith("/img/"):
            name = os.path.basename(path)
            allowed = {v["file"] for v in _board["images"].values()}
            if name not in allowed:
                return self._send("not found", "text/plain", 404)
            # In a checkout the renders live in ../gen; a deployment ships
            # them beside the app instead, so accept either.
            p = ROOT / "gen" / name
            if not p.exists():
                p = NAV / "gen" / name
            if not p.exists():
                return self._send("render missing", "text/plain", 404)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(p.stat().st_size))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1 << 16)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            return
        if path == "/api/groups":
            out = []
            for g in GROUPS.GROUPS:
                try:
                    _, refs, anns, _ = GROUPS.resolve(g["id"], _index)
                    err = ""
                except (ValueError, KeyError) as e:
                    refs, anns, err = [], [], str(e)
                out.append(dict(id=g["id"], label=g["label"], desc=g["desc"],
                                color=g["color"], side=g["side"],
                                count=len(refs), pins=len(anns), error=err))
            return self._json(dict(groups=out))
        if path == "/api/find":
            q = (qs.get("q") or [""])[0]
            limit = int((qs.get("limit") or ["50"])[0])
            hits = find(q, limit)
            return self._json(dict(query=q, count=len(hits),
                                   parts=[slim(p) for p in hits]))
        if path.startswith("/api/part/"):
            ref = unquote(path[len("/api/part/"):])
            p = _index.get(ref)
            if not p:
                return self._json(dict(error=f"unknown ref {ref}"), 404)
            out = slim(p)
            out["neighbours"] = [slim(q) for q in nearest(p, 8)]
            return self._json(out)
        if path.startswith("/api/net/"):
            net = unquote(path[len("/api/net/"):])
            members = _nets.get(net)
            if members is None:
                return self._json(dict(error=f"unknown net {net}"), 404)
            return self._json(dict(net=net, count=len(members),
                                   members=[dict(ref=r, pin=pin,
                                                 **{k: _index[r][k] for k in
                                                    ("x", "y", "layer", "role", "value")})
                                            for r, pin in members[:500]]))
        return self._send("not found", "text/plain", 404)

    # -- POST / DELETE ----------------------------------------------------
    def do_POST(self):
        path = strip_base(urlparse(self.path).path)
        if path is None:
            return self._send("not found", "text/plain", 404)
        if not self._authorized():
            return self._json(dict(error="a token is required to change the board"), 401)
        try:
            d = self._body()
        except ValueError as e:
            return self._json(dict(error=f"bad JSON: {e}"), 400)

        try:
            if path == "/api/annotate":
                a = make_annotation(d)
                with state_lock:
                    state["annotations"] = [x for x in state["annotations"]
                                            if x["id"] != a["id"]]
                    state["annotations"].append(a)
                    if d.get("goto"):
                        state["view"] = dict(x=a["x"], y=a["y"], side=a["side"],
                                             zoom=d.get("zoom"), ts=time.time())
                        state["side"] = a["side"]
                    bump_and_broadcast()
                return self._json(dict(ok=True, annotation=a))

            if path == "/api/annotations":
                anns = [make_annotation(x) for x in d.get("annotations", [])]
                with state_lock:
                    if d.get("replace", True):
                        state["annotations"] = anns
                    else:
                        keep = {a["id"] for a in anns}
                        state["annotations"] = [x for x in state["annotations"]
                                                if x["id"] not in keep] + anns
                    bump_and_broadcast()
                return self._json(dict(ok=True, count=len(state["annotations"])))

            if path == "/api/highlight":
                refs = list(d.get("refs") or [])
                for net in (d.get("nets") or []):
                    refs += [r for r, _ in _nets.get(net, [])]
                if d.get("query"):
                    refs += [p["ref"] for p in find(d["query"], int(d.get("limit", 500)))]
                unknown = [r for r in refs if r not in _index]
                refs = [r for r in refs if r in _index]
                seen, uniq = set(), []
                for r in refs:
                    if r not in seen:
                        seen.add(r)
                        uniq.append(r)
                with state_lock:
                    state["highlight"] = dict(refs=uniq,
                                              label=str(d.get("label", "")),
                                              color=d.get("color", "#ffd23f"))
                    if d.get("goto") and uniq:
                        p = _index[uniq[0]]
                        state["view"] = dict(x=p["x"], y=p["y"], side=p["layer"],
                                             zoom=d.get("zoom"), ts=time.time())
                        state["side"] = p["layer"]
                    bump_and_broadcast()
                return self._json(dict(ok=True, count=len(uniq), unknown=unknown))

            if path == "/api/group":
                g, refs, anns, note = GROUPS.resolve(d.get("id", ""), _index)
                want_pins = d.get("annotate", True) and anns
                with state_lock:
                    state["highlight"] = dict(refs=refs, color=g["color"],
                                              label=f"{g['label']} — {g['desc']}")
                    state["annotations"] = ([make_annotation(a) for a in anns]
                                            if want_pins else [])
                    state["note"] = dict(title=g["label"], text=note)
                    if d.get("goto", True):
                        xs = [_index[r]["x"] for r in refs]
                        ys = [_index[r]["y"] for r in refs]
                        # span lets the page frame the whole group; it knows the
                        # canvas size and the server does not
                        state["view"] = dict(x=(min(xs) + max(xs)) / 2,
                                             y=(min(ys) + max(ys)) / 2,
                                             w=max(max(xs) - min(xs), 4.0),
                                             h=max(max(ys) - min(ys), 4.0),
                                             side=g["side"],
                                             zoom=d.get("zoom"), ts=time.time())
                        state["side"] = g["side"]
                    bump_and_broadcast()
                return self._json(dict(ok=True, id=g["id"], count=len(refs),
                                       pins=len(state["annotations"]), refs=refs))

            if path == "/api/view":
                x, y, side = resolve_point(d) if (d.get("ref") or "x" in d) else \
                    (_board["board"]["w"] / 2, _board["board"]["h"] / 2, d.get("side", "F"))
                with state_lock:
                    state["view"] = dict(x=x, y=y, side=side,
                                         zoom=d.get("zoom"), ts=time.time())
                    state["side"] = side
                    bump_and_broadcast()
                return self._json(dict(ok=True, x=x, y=y, side=side))

            if path == "/api/note":
                with state_lock:
                    state["note"] = dict(title=str(d.get("title", "")),
                                         text=str(d.get("text", "")))
                    bump_and_broadcast()
                return self._json(dict(ok=True))

            if path == "/api/clear":
                what = d.get("what", "all")
                with state_lock:
                    if what in ("all", "annotations"):
                        state["annotations"] = []
                    if what in ("all", "highlight"):
                        state["highlight"] = dict(refs=[], label="", color="#ffd23f")
                    if what in ("all", "note"):
                        state["note"] = dict(title="", text="")
                    bump_and_broadcast()
                return self._json(dict(ok=True, cleared=what))

        except (ValueError, KeyError, TypeError) as e:
            return self._json(dict(error=str(e)), 400)

        return self._send("not found", "text/plain", 404)

    def do_DELETE(self):
        path = strip_base(urlparse(self.path).path)
        if path is None:
            return self._send("not found", "text/plain", 404)
        if not self._authorized():
            return self._json(dict(error="a token is required to change the board"), 401)
        if path.startswith("/api/annotation/"):
            aid = unquote(path[len("/api/annotation/"):])
            with state_lock:
                before = len(state["annotations"])
                state["annotations"] = [a for a in state["annotations"] if a["id"] != aid]
                bump_and_broadcast()
            return self._json(dict(ok=True, removed=before - len(state["annotations"])))
        return self._send("not found", "text/plain", 404)

    # -- websocket upgrade ------------------------------------------------
    def do_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            return self._send("expected websocket", "text/plain", 400)
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        conn = self.connection
        with clients_lock:
            clients.append(conn)
        with state_lock:
            snapshot = json.dumps(dict(type="state", state=state))
        try:
            conn.sendall(ws_frame(snapshot))
            ws_read_loop(conn)
        except (OSError, struct.error):
            pass
        finally:
            with clients_lock:
                if conn in clients:
                    clients.remove(conn)
        self.close_connection = True


def nearest(p, n):
    """The n nearest parts on the same side — handy when identifying a site
    under a magnifier, where the neighbours are what you can actually read."""
    same = [q for q in _index.values() if q["layer"] == p["layer"] and q["ref"] != p["ref"]]
    same.sort(key=lambda q: (q["x"] - p["x"]) ** 2 + (q["y"] - p["y"]) ** 2)
    return same[:n]


def main():
    global BASE, TOKEN
    args = [a for a in sys.argv[1:]]
    port = 8624
    host = "127.0.0.1"
    for i, a in enumerate(args):
        if a.isdigit():
            port = int(a)
        elif a == "--base" and i + 1 < len(args):
            BASE = "/" + args[i + 1].strip("/")
        elif a == "--host" and i + 1 < len(args):
            host = args[i + 1]
    # The token never appears on a command line (ps is world-readable).
    TOKEN = os.environ.get("NAV_TOKEN", "")
    load_board()
    load_state()
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    url = f"http://{host}:{port}{BASE}/"
    print(f"board navigator (rev A) on {url}")
    print(f"  {len(_index)} parts, {len(_nets)} nets — API: {url}api/find?q=Q2577")
    print("  writes are token-gated" if TOKEN else "  writes are open (no NAV_TOKEN set)")
    if "--open" in args:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
