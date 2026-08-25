#!/usr/bin/env python3
"""Track the PCL/PCH LEDs through a handheld clip, so their signals stay sharp.

Why this exists: the board drifts in frame. Every earlier analysis sampled fixed
pixel coordinates, so as the camera wandered each "LED" window slid off its LED
and picked up neighbouring board. That smears the very signal being measured --
it is the most likely reason the 2026-08-25 detections sat at 5-11x SNR instead
of far higher, and on a longer clip it would destroy them outright.

The fix is motion compensation, in two layers:

  1. **Automatic global drift.** The board is rigid and the camera is not, so one
     translation per frame applies to every LED at once. That is estimated by
     phase correlation against the first frame, before you click anything.
  2. **Manual keyframes for the residual.** Place markers once, step forward,
     nudge any that have wandered, and the positions in between are linearly
     interpolated. Layer 1 usually makes layer 2 almost free.

Only PCL and PCH are worth marking on a NOP free-run: the PC is the only thing
changing. A/X/Y/S sit still (on the 2026-08-25 clip only A1 and A2 were lit at
all, and they never changed -- which is itself a confirmation that NOP touches no
register).

Output is keyframes, not per-frame positions:

    {"keyframes": {"0": {"PCL7": [y, x], ...}, "120": {...}}, "drift": [[dy,dx],...]}

and tools/pc_ripple.py --labels interpolates between them.

Usage:
    python3 tools/led_picker.py --frames FRAMES/        # then open the URL
"""

import argparse
import glob
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LABELS = ["PCL%d" % i for i in range(8)] + ["PCH%d" % i for i in range(8)]

PAGE = """<!doctype html><meta charset=utf-8><title>LED tracker</title>
<style>
 body{font:14px system-ui;margin:0;background:#111;color:#eee;display:flex;height:100vh}
 #left{flex:1;overflow:auto}
 #wrap{position:relative;display:inline-block}
 img{display:block}
 #side{width:300px;padding:12px;background:#1b1b1b;overflow:auto;border-left:1px solid #333}
 .dot{position:absolute;border:2px solid #0f0;border-radius:50%%;width:20px;height:20px;
      margin:-12px 0 0 -12px;cursor:grab;box-shadow:0 0 0 1px #000}
 .dot.key{border-color:#ff0}
 .lab{position:absolute;color:#0f0;font:11px monospace;margin:-24px 0 0 11px;
      text-shadow:0 0 3px #000;pointer-events:none}
 button{padding:7px;margin:3px 0;background:#2a2a2a;color:#eee;border:1px solid #444;
        border-radius:4px;cursor:pointer}
 button.wide{width:100%%}
 select,input{width:100%%;padding:6px;background:#2a2a2a;color:#eee;border:1px solid #444;border-radius:4px}
 .hint{color:#888;font-size:12px;line-height:1.45}
 #zoom{position:fixed;width:200px;height:200px;border:2px solid #0f0;pointer-events:none;
       display:none;background-repeat:no-repeat;z-index:9}
 .row{display:flex;gap:6px} .row button{flex:1}
</style>
<div id=left><div id=wrap><img id=im width="%(w)d"><div id=marks></div></div></div>
<div id=side>
 <p class=hint><b>1.</b> Pick a label, click its LED. Repeat for every PCL/PCH bit you can see.<br>
 <b>2.</b> Jump forward. Markers move with the estimated drift &mdash; <b>drag any that are off</b>.<br>
 <b>3.</b> Repeat a few times across the clip, then Save.</p>
 <select id=sel></select>
 <div class=row><button onclick="step(-KF)">&laquo; back</button><button onclick="step(KF)">fwd &raquo;</button></div>
 <input id=slider type=range min=0 max="%(n)d" value=0 oninput="go(+this.value)">
 <p class=hint>frame <span id=fno>0</span> / %(n)d &nbsp; <span id=kfmark></span><br>
 drift here: <span id=dr>0, 0</span> px</p>
 <button class=wide onclick="markKey()">Pin these positions as a keyframe</button>
 <button class=wide onclick="undo()">Remove last marker</button>
 <button class=wide onclick="save()">Save to %(out)s</button>
 <p class=hint id=status></p>
 <ol id=list></ol>
</div>
<div id=zoom></div>
<script>
const SCALE=%(scale)f, N=%(n)d, KF=%(kf)d, DRIFT=%(drift)s;
let cur=0, marks={}, keys={};   // marks: label -> [y,x] at current frame (original px)
const sel=document.getElementById('sel');
%(labels)s.forEach(n=>{const o=document.createElement('option');o.textContent=n;sel.appendChild(o)});
const im=document.getElementById('im'), holder=document.getElementById('marks'), zoom=document.getElementById('zoom');

function nearestKeys(f){
  const ks=Object.keys(keys).map(Number).sort((a,b)=>a-b);
  let lo=null,hi=null;
  for(const k of ks){ if(k<=f) lo=k; if(k>=f && hi===null) hi=k; }
  return [lo,hi];
}
function positionsAt(f){
  const [lo,hi]=nearestKeys(f); const out={};
  if(lo===null&&hi===null) return out;
  if(lo!==null&&hi!==null&&lo!==hi){
    const t=(f-lo)/(hi-lo);
    for(const l in keys[lo]) if(keys[hi][l]){
      out[l]=[keys[lo][l][0]+t*(keys[hi][l][0]-keys[lo][l][0]),
              keys[lo][l][1]+t*(keys[hi][l][1]-keys[lo][l][1])];
    }
  } else {
    const k=(lo!==null?lo:hi);
    for(const l in keys[k]) out[l]=[keys[k][l][0]+DRIFT[f][0]-DRIFT[k][0],
                                    keys[k][l][1]+DRIFT[f][1]-DRIFT[k][1]];
  }
  return out;
}
function go(f){
  cur=Math.max(0,Math.min(N,f));
  im.src='/frame/'+cur;
  document.getElementById('fno').textContent=cur;
  document.getElementById('slider').value=cur;
  document.getElementById('dr').textContent=DRIFT[cur][1].toFixed(1)+', '+DRIFT[cur][0].toFixed(1);
  document.getElementById('kfmark').textContent = keys[cur]?'\\u2605 keyframe':'';
  marks=positionsAt(cur); draw();
}
function step(d){go(cur+d)}
function markKey(){ keys[cur]=JSON.parse(JSON.stringify(marks)); go(cur); }
function undo(){ const k=Object.keys(marks); if(k.length){delete marks[k[k.length-1]]; draw();} }
function draw(){
  holder.innerHTML='';
  for(const l in marks){
    const y=marks[l][0]*SCALE, x=marks[l][1]*SCALE;
    const d=document.createElement('div'); d.className='dot'+(keys[cur]?' key':'');
    d.style.left=x+'px'; d.style.top=y+'px'; d.dataset.l=l;
    d.onmousedown=ev=>{ev.preventDefault();drag(l,ev)};
    holder.appendChild(d);
    const t=document.createElement('div'); t.className='lab'; t.textContent=l;
    t.style.left=x+'px'; t.style.top=y+'px'; holder.appendChild(t);
  }
  document.getElementById('list').innerHTML=Object.keys(marks).sort().map(
    l=>'<li>'+l+' y='+marks[l][0].toFixed(0)+' x='+marks[l][1].toFixed(0)+'</li>').join('');
}
function drag(l,ev){
  const move=e=>{ const r=im.getBoundingClientRect();
    marks[l]=[(e.clientY-r.top)/SCALE,(e.clientX-r.left)/SCALE]; draw(); showZoom(e); };
  const up=()=>{ document.removeEventListener('mousemove',move);
    document.removeEventListener('mouseup',up); zoom.style.display='none';
    keys[cur]=JSON.parse(JSON.stringify(marks)); go(cur); };
  document.addEventListener('mousemove',move); document.addEventListener('mouseup',up);
}
function showZoom(e){
  const r=im.getBoundingClientRect();
  zoom.style.display='block';
  zoom.style.left=(e.clientX+20)+'px'; zoom.style.top=(e.clientY+20)+'px';
  zoom.style.backgroundImage="url('/frame/"+cur+"')";
  zoom.style.backgroundSize=(im.width*5)+'px auto';
  zoom.style.backgroundPosition=(-(e.clientX-r.left)*5+100)+'px '+(-(e.clientY-r.top)*5+100)+'px';
}
im.addEventListener('mousemove',showZoom);
im.addEventListener('mouseleave',()=>zoom.style.display='none');
im.addEventListener('click',e=>{
  const r=im.getBoundingClientRect();
  marks[sel.value]=[(e.clientY-r.top)/SCALE,(e.clientX-r.left)/SCALE];
  if(sel.selectedIndex<sel.options.length-1) sel.selectedIndex++;
  keys[cur]=JSON.parse(JSON.stringify(marks)); go(cur);
});
function save(){
  if(!Object.keys(keys).length){document.getElementById('status').textContent='nothing to save';return;}
  fetch('/save',{method:'POST',body:JSON.stringify({keyframes:keys,drift:DRIFT})})
    .then(r=>r.text()).then(t=>{document.getElementById('status').textContent=t});
}
go(0);
</script>
"""


def estimate_drift(files, work=480):
    """Per-frame (dy, dx) of the whole scene, by phase correlation against frame 0.

    The board is rigid; the camera is what moves. One translation per frame
    therefore applies to every LED, which is why this is worth doing before any
    hand-marking: it removes most of the motion for free.
    """
    import numpy as np
    from PIL import Image

    def prep(p):
        im = Image.open(p).convert("L")
        s = work / float(max(im.size))
        im = im.resize((max(8, int(im.width * s)), max(8, int(im.height * s))))
        a = np.asarray(im).astype(np.float32)
        a -= a.mean()
        w = np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]
        return a * w, 1.0 / s

    ref, inv = prep(files[0])
    R = np.fft.rfft2(ref)
    H, W = ref.shape
    out = []
    for p in files:
        cur, _ = prep(p)
        C = np.fft.rfft2(cur)
        X = R * np.conj(C)
        m = np.abs(X)
        X = np.divide(X, m, out=np.zeros_like(X), where=m > 1e-9)
        r = np.fft.irfft2(X, s=ref.shape)
        dy, dx = np.unravel_index(int(np.argmax(r)), r.shape)
        if dy > H // 2:
            dy -= H
        if dx > W // 2:
            dx -= W
        out.append([-dy * inv, -dx * inv])   # shift to ADD to frame-0 coordinates
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", default="gen/led_labels.json")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--width", type=int, default=1100)
    ap.add_argument("--keystep", type=int, default=60, help="frames the fwd/back buttons jump")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.frames, "*.png")) +
                   glob.glob(os.path.join(args.frames, "*.jpg")))
    if not files:
        sys.exit("no frames in %s" % args.frames)

    from PIL import Image
    w0, h0 = Image.open(files[0]).size
    scale = args.width / float(w0)

    print("estimating global drift over %d frames..." % len(files))
    drift = estimate_drift(files)
    mag = max(abs(d[0]) for d in drift), max(abs(d[1]) for d in drift)
    print("peak drift: %.1f px vertical, %.1f px horizontal" % mag)
    if max(mag) < 2:
        print("  (negligible -- fixed coordinates would have been fine)")
    else:
        print("  (significant -- this is what was smearing the fixed-window analysis)")

    page = (PAGE % {"w": args.width, "scale": scale, "n": len(files) - 1,
                    "kf": args.keystep, "out": args.out,
                    "labels": json.dumps(LABELS),
                    "drift": json.dumps([[round(a, 2), round(b, 2)] for a, b in drift])}).encode()
    cache = {}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/frame/"):
                i = max(0, min(len(files) - 1, int(self.path.rsplit("/", 1)[1])))
                if i not in cache:
                    im = Image.open(files[i]).convert("RGB")
                    im = im.resize((args.width, int(im.height * scale)))
                    b = io.BytesIO()
                    im.save(b, "JPEG", quality=88)
                    if len(cache) > 400:
                        cache.clear()
                    cache[i] = b.getvalue()
                body, ctype = cache[i], "image/jpeg"
            else:
                body, ctype = page, "text/html"
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
                json.dump(data, fh, indent=1, sort_keys=True)
            k = data.get("keyframes", {})
            msg = ("saved %d keyframes, %d labels to %s"
                   % (len(k), len(next(iter(k.values()), {})), args.out)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    print("open  http://127.0.0.1:%d/   (ctrl-c to stop)" % args.port)
    HTTPServer(("127.0.0.1", args.port), H).serve_forever()


if __name__ == "__main__":
    main()
