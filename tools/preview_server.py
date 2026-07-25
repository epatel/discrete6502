#!/usr/bin/env python3
"""Local layout-preview server for iteration.

Serves tools/preview/index.html at /, gen/layout.json at /gen/layout.json,
accepts POST /comment (JSON {text, side}) -> appends to gen/preview_comments.jsonl,
GET /comments -> the collected list. Run: python3 tools/preview_server.py [port]
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMENTS = ROOT / "gen" / "preview_comments.jsonl"


class H(BaseHTTPRequestHandler):
    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body if isinstance(body, bytes) else body.encode())

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send((ROOT / "tools/preview/index.html").read_bytes(), "text/html")
        elif self.path == "/gen/layout.json":
            self._send((ROOT / "gen/layout.json").read_bytes())
        elif self.path == "/comments":
            items = []
            if COMMENTS.exists():
                items = [json.loads(l) for l in COMMENTS.read_text().splitlines() if l]
            self._send(json.dumps(items))
        else:
            self._send("not found", "text/plain", 404)

    def do_POST(self):
        if self.path != "/comment":
            self._send("not found", "text/plain", 404)
            return
        n = int(self.headers.get("Content-Length", 0))
        d = json.loads(self.rfile.read(n))
        d["time"] = time.strftime("%H:%M:%S")
        with open(COMMENTS, "a") as f:
            f.write(json.dumps(d) + "\n")
        self._send('{"ok":true}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8623
    print("preview at http://localhost:%d" % port, flush=True)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
