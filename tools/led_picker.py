#!/usr/bin/env python3
"""Serve a clip's LED positions in a browser so a human can name them.

The statistical test in tools/pc_ripple.py proves the program counter is running
without knowing which LED is which -- it only asks whether the predicted set of
frequencies is present. That is deliberately weak on purpose: it cannot be fooled
by mislabelling, but it also cannot say "this LED is PCL7".

This tool closes that gap. It builds a max-projection of the clip, so every LED
that ever lit shows up in one image, serves it in a browser, and lets you click
each one and name it. Feed the result back:

    python3 tools/pc_ripple.py --clock 2250 --frames DIR --labels leds.json

which then reports, per named bit, the measured frequency against the one
arithmetic demands -- and whether each bit is half the rate of the one above it.
That ladder is a far stronger claim than "some LEDs matched some frequencies".

Only bits with enough cycles inside the clip can be checked. At 2250 Hz over
14.7 s that is PCL2 and slower through PCH3; PCH4..PCH7 have periods of 7 to 58
seconds and simply are not in the recording.

Usage:
    python3 tools/led_picker.py --frames FRAMES/          # then open the URL
    python3 tools/led_picker.py --frames FRAMES/ --out my_leds.json --port 8099
"""

import argparse
import glob
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LABELS = (["PCL%d" % i for i in range(8)] + ["PCH%d" % i for i in range(8)] +
          ["A%d" % i for i in range(8)] + ["X%d" % i for i in range(8)] +
          ["Y%d" % i for i in range(8)] + ["S%d" % i for i in range(8)] +
          ["P.C", "P.Z", "P.I", "P.D", "P.B", "P.V", "P.N"] + ["other"])

PAGE = """<!doctype html><meta charset=utf-8><title>LED picker</title>
<style>
 body{font:14px system-ui;margin:0;background:#111;color:#eee;display:flex;height:100vh}
 #left{flex:1;overflow:auto;position:relative}
 #wrap{position:relative;display:inline-block}
 img{display:block;image-rendering:pixelated}
 #side{width:280px;padding:12px;background:#1b1b1b;overflow:auto;border-left:1px solid #333}
 .dot{position:absolute;border:2px solid #0f0;border-radius:50%%;width:22px;height:22px;
      margin:-13px 0 0 -13px;pointer-events:none;box-shadow:0 0 0 1px #000}
 .lab{position:absolute;color:#0f0;font:11px monospace;margin:-26px 0 0 12px;
      text-shadow:0 0 3px #000;pointer-events:none}
 button{width:100%%;padding:8px;margin:4px 0;background:#2a2a2a;color:#eee;border:1px solid #444;
        border-radius:4px;cursor:pointer}
 button:hover{background:#333}
 select{width:100%%;padding:6px;background:#2a2a2a;color:#eee;border:1px solid #444;border-radius:4px}
 li{font:12px monospace;margin:2px 0}
 #zoom{position:fixed;width:180px;height:180px;border:2px solid #0f0;pointer-events:none;
       display:none;background-repeat:no-repeat;z-index:9}
 .hint{color:#888;font-size:12px;line-height:1.45}
</style>
<div id=left><div id=wrap><img id=im src="/image" width="%(w)d"><div id=marks></div></div></div>
<div id=side>
 <p class=hint>Max projection: every LED that lit at any point in the clip.
 Pick a name, click the LED. Right-click a marker area to undo the last one.</p>
 <select id=sel></select>
 <button onclick="undo()">Undo last</button>
 <button onclick="save()">Save to %(out)s</button>
 <p class=hint id=status></p>
 <ol id=list></ol>
</div>
<div id=zoom></div>
<script>
const SCALE=%(scale)f, W=%(w)d;
const sel=document.getElementById('sel');
%(labels)s.forEach(n=>{const o=document.createElement('option');o.textContent=n;sel.appendChild(o)});
let pts=[];
const im=document.getElementById('im'), marks=document.getElementById('marks'), zoom=document.getElementById('zoom');
im.addEventListener('mousemove',e=>{
  const r=im.getBoundingClientRect();
  zoom.style.display='block';
  zoom.style.left=(e.clientX+18)+'px'; zoom.style.top=(e.clientY+18)+'px';
  zoom.style.backgroundImage="url('/image')";
  zoom.style.backgroundSize=(im.width*4)+'px auto';
  zoom.style.backgroundPosition=(-(e.clientX-r.left)*4+90)+'px '+(-(e.clientY-r.top)*4+90)+'px';
});
im.addEventListener('mouseleave',()=>zoom.style.display='none');
im.addEventListener('click',e=>{
  const r=im.getBoundingClientRect();
  const dx=e.clientX-r.left, dy=e.clientY-r.top;
  pts.push({label:sel.value, x:Math.round(dx/SCALE), y:Math.round(dy/SCALE), dx:dx, dy:dy});
  if(sel.selectedIndex<sel.options.length-1) sel.selectedIndex++;
  draw();
});
function draw(){
  marks.innerHTML='';
  pts.forEach(p=>{
    const d=document.createElement('div'); d.className='dot';
    d.style.left=p.dx+'px'; d.style.top=p.dy+'px'; marks.appendChild(d);
    const l=document.createElement('div'); l.className='lab'; l.textContent=p.label;
    l.style.left=p.dx+'px'; l.style.top=p.dy+'px'; marks.appendChild(l);
  });
  document.getElementById('list').innerHTML=pts.map(p=>'<li>'+p.label+' &nbsp; y='+p.y+' x='+p.x+'</li>').join('');
}
function undo(){pts.pop();draw();}
function save(){
  const o={}; pts.forEach(p=>{o[p.label]=[p.y,p.x]});
  fetch('/save',{method:'POST',body:JSON.stringify(o)}).then(r=>r.text()).then(t=>{
    document.getElementById('status').textContent=t;});
}
</script>
"""


def build_projection(frame_dir, gain):
    import numpy as np
    from PIL import Image
    fs = sorted(glob.glob(os.path.join(frame_dir, "*.png")) +
                glob.glob(os.path.join(frame_dir, "*.jpg")))
    if not fs:
        sys.exit("no frames in %s" % frame_dir)
    mx = None
    for f in fs[::2]:
        a = np.asarray(Image.open(f).convert("RGB")).astype(np.float32)
        s = np.clip(a[..., 0] - np.maximum(a[..., 1], a[..., 2]), 0, None)
        mx = s if mx is None else np.maximum(mx, s)
    # base image: a real frame, dimmed, with the projection burned in as red
    base = np.asarray(Image.open(fs[len(fs) // 2]).convert("RGB")).astype(np.float32) * 0.35
    hot = np.clip(mx * gain, 0, 255)
    base[..., 0] = np.clip(base[..., 0] + hot, 0, 255)
    base[..., 1] = np.clip(base[..., 1] + hot * 0.35, 0, 255)
    base[..., 2] = np.clip(base[..., 2] + hot * 0.35, 0, 255)
    return Image.fromarray(base.astype("uint8")), len(fs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", default="gen/led_labels.json")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--width", type=int, default=1100, help="display width in the browser")
    ap.add_argument("--gain", type=float, default=2.2, help="brightness boost for lit LEDs")
    args = ap.parse_args()

    img, nframes = build_projection(args.frames, args.gain)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    png = buf.getvalue()
    scale = args.width / float(img.width)
    page = (PAGE % {"w": args.width, "scale": scale, "out": args.out,
                    "labels": json.dumps(LABELS)}).encode()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body, ctype = (png, "image/png") if self.path.startswith("/image") else (page, "text/html")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            with open(args.out, "w") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
            msg = ("saved %d labels to %s" % (len(data), args.out)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    print("projection built from %d frames, %dx%d" % (nframes, img.width, img.height))
    print("open  http://127.0.0.1:%d/   (ctrl-c to stop)" % args.port)
    print("labels will be written to %s" % args.out)
    HTTPServer(("127.0.0.1", args.port), H).serve_forever()


if __name__ == "__main__":
    main()
