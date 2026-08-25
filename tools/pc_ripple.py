#!/usr/bin/env python3
"""Prove the CPU is executing, by finding the program counter in a video of the LEDs.

On a NOP free-run ($EA on the data bus) the 6502 does nothing but fetch and
increment, so the PC becomes a pure binary counter and every PCL/PCH LED must
blink at an exactly predictable rate:

    instructions/s = clock / cycles_per_instruction      (NOP = 2 cycles)
    PC bit b toggles at  instructions/s / 2**(b+1)

That is the whole test. If those frequencies are present, the CPU sequences; if
they are not, it does not. No LED needs to be identified by name.

**The aliased bits are what make this conclusive.** A phone films at ~30 fps, so
the fast PCL bits fold back into the visible band at frequencies that are not
"natural" for anything -- PCL4 at 35.16 Hz appears at 5.26 Hz, PCL2 at 140.6 Hz
appears at 8.87 Hz. Those numbers fall out of the clock rate and the frame rate
and nothing else, so finding LEDs sitting on them cannot be drift, mains flicker,
camera exposure hunting or a browning-out clock source. That is the argument the
earlier attempts lacked: they looked only for the direct low-frequency bits,
which live in the same part of the spectrum as every slow artifact.

Two traps this tool avoids, both of which produced false negatives in August 2026:

  - **Aggregating across LEDs.** Only 16 of the 55 register LEDs are PC bits, so
    averaging spectra over every visible LED buries them under the other 39.
    Count LEDs whose *own* dominant peak matches instead.
  - **The record's own envelope.** A run that starts and stops inside the clip
    puts a large peak at 1/duration, which masquerades as a low-frequency PC bit.
    Each series is detrended with a cubic before transforming, and the lowest
    bins are reported but should not be trusted on a short record.

Usage:
    python3 tools/pc_ripple.py --clock 2250                 # just the predictions
    python3 tools/pc_ripple.py --clock 2250 --frames DIR    # analyse extracted frames

Extract frames first with, e.g.:
    ffmpeg -i clip.mp4 frames/f%04d.png
"""

import argparse
import glob
import json
import os
import sys


def predictions(clock, fps, cyc):
    """PC bit -> (true toggle rate, the frequency it aliases to at this fps)."""
    inst = clock / float(cyc)
    out = []
    for b in range(16):
        f = inst / 2 ** (b + 1)
        k = round(f / fps)
        out.append((b, f, abs(f - k * fps)))
    return inst, out


def name(b):
    return "PCL%d" % b if b < 8 else "PCH%d" % (b - 8)


def analyse(frame_dir, fps, preds, lo, hi, thr, snr_min):
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    fs = sorted(glob.glob(os.path.join(frame_dir, "*.png")) +
                glob.glob(os.path.join(frame_dir, "*.jpg")))
    if len(fs) < 60:
        sys.exit("need at least 60 frames, found %d" % len(fs))
    n = len(fs)

    def redness(path):
        a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
        return np.clip(a[..., 0] - np.maximum(a[..., 1], a[..., 2]), 0, None)

    # locate LED-sized spots from a max projection over a subsample
    mx = None
    for f in fs[::3]:
        s = redness(f)
        mx = s if mx is None else np.maximum(mx, s)
    lab, k = ndimage.label(mx > thr)
    sz = np.array(ndimage.sum(mx > thr, lab, range(1, k + 1))) if k else np.array([])
    spots = []
    for j in range(k):
        if not (8 <= sz[j] <= 500):
            continue
        ys, xs = np.where(lab == j + 1)
        spots.append((int(ys.mean()), int(xs.mean())))
    if not spots:
        sys.exit("no LED-sized red spots found; try a lower --threshold")

    T = np.empty((n, len(spots)), np.float32)
    for i, f in enumerate(fs):
        s = redness(f)
        for j, (y, x) in enumerate(spots):
            T[i, j] = s[max(0, y - 3):y + 4, max(0, x - 3):x + 4].max()

    on = (T > thr * 0.75).astype(float)
    duty = on.mean(0)
    sel = np.where((duty > 0.05) & (duty < 0.95))[0]

    fr = np.fft.rfftfreq(n, 1 / fps)
    w = np.hanning(n)
    t = np.arange(n)
    band = (fr > lo) & (fr < hi)
    peaks = []
    for j in sel:
        x = on[:, j] - on[:, j].mean()
        x = x - np.polyval(np.polyfit(t, x, 3), t)   # kill the record's envelope
        X = np.abs(np.fft.rfft(x * w))
        floor = np.median(X[band])
        i = int(np.argmax(X[band]))
        peaks.append((fr[band][i], X[band][i] / (floor or 1)))

    res = fps / n
    print("\n%d frames at %.2f fps = %.1f s;  resolution %.3f Hz, tolerance %.3f Hz"
          % (n, fps, n / fps, res, 2 * res))
    print("%d red spots, %d of them blinking\n" % (len(spots), len(sel)))
    print("  predicted   from                       LEDs on it (SNR>%g)" % snr_min)
    matched = 0
    for b, f, fo in preds:
        if not (lo < fo < hi):
            continue
        hits = [p for p in peaks if abs(p[0] - fo) <= 2 * res and p[1] > snr_min]
        matched += len(hits)
        tag = "  (aliased from %.1f Hz)" % f if abs(f - fo) > 0.01 else "  (direct)"
        print("  %7.3f Hz  %-6s%-26s %2d  %s"
              % (fo, name(b), tag, len(hits), "#" * len(hits)))
    unmatched = [p for p in peaks if p[1] > snr_min and
                 not any(abs(p[0] - fo) <= 2 * res for _, _, fo in preds if lo < fo < hi)]
    print("\n  LEDs on a predicted PC frequency : %d" % matched)
    print("  strong peaks matching nothing     : %d" % len(unmatched))
    if unmatched:
        print("   ", sorted(round(p[0], 2) for p in unmatched)[:12])
    print("\n  VERDICT: %s" % ("the program counter is counting -- the CPU executes"
                               if matched and not unmatched else
                               "inconclusive; see the traps in this file's docstring"))


def analyse_labelled(frame_dir, fps, label_file, clock, cyc, thr):
    """Check named LEDs one at a time: does PCL7 really toggle at PCL7's rate?

    Stronger than the anonymous test, because it can be WRONG. The anonymous test
    asks only whether a set of frequencies exists somewhere; this asks whether a
    specific LED a human pointed at carries the specific bit they named, and
    whether each bit runs at half the rate of the one above it.
    """
    import numpy as np
    from PIL import Image

    raw = json.load(open(label_file))
    fs = sorted(glob.glob(os.path.join(frame_dir, "*.png")) +
                glob.glob(os.path.join(frame_dir, "*.jpg")))
    n = len(fs)

    # Two accepted shapes: flat {label: [y,x]} (fixed coordinates), or the
    # tracked form from led_picker.py with keyframes plus a global drift curve.
    # Tracking matters: the board wanders in a handheld clip, and a fixed window
    # slides off its LED, smearing exactly the signal being measured.
    if "keyframes" in raw:
        kf = {int(k): v for k, v in raw["keyframes"].items()}
        drift = raw.get("drift") or [[0.0, 0.0]] * n
        names = sorted({nm for d in kf.values() for nm in d})
        ks = sorted(kf)
        track = np.zeros((n, len(names), 2), np.float32)
        for j, nm in enumerate(names):
            have = [k for k in ks if nm in kf[k]]
            for i in range(n):
                lo = max([k for k in have if k <= i], default=None)
                hi = min([k for k in have if k >= i], default=None)
                if lo is not None and hi is not None and lo != hi:
                    t = (i - lo) / float(hi - lo)
                    a0, a1 = kf[lo][nm], kf[hi][nm]
                    track[i, j] = [a0[0] + t * (a1[0] - a0[0]), a0[1] + t * (a1[1] - a0[1])]
                else:
                    k = lo if lo is not None else hi
                    d0, d1 = drift[min(k, n - 1)], drift[i]
                    track[i, j] = [kf[k][nm][0] + d1[0] - d0[0],
                                   kf[k][nm][1] + d1[1] - d0[1]]
        span = float(np.abs(track - track[0]).max())
        print("tracked %d LEDs across %d keyframes; markers move up to %.1f px"
              % (len(names), len(ks), span))
    else:
        names = list(raw)
        track = np.zeros((n, len(names), 2), np.float32)
        for j, nm in enumerate(names):
            track[:, j] = raw[nm]
        print("fixed coordinates for %d LEDs (no tracking)" % len(names))

    series = np.empty((n, len(names)), np.float32)
    for i, f in enumerate(fs):
        a = np.asarray(Image.open(f).convert("RGB")).astype(np.float32)
        s = np.clip(a[..., 0] - np.maximum(a[..., 1], a[..., 2]), 0, None)
        for j in range(len(names)):
            y, x = int(round(track[i, j, 0])), int(round(track[i, j, 1]))
            series[i, j] = s[max(0, y - 3):y + 4, max(0, x - 3):x + 4].max()

    inst = clock / float(cyc)
    fr = np.fft.rfftfreq(n, 1 / fps)
    w = np.hanning(n)
    t = np.arange(n)
    res = fps / n
    print("\n=== named-LED check: %d labels, %.1f s at %.2f fps (resolution %.3f Hz)"
          % (len(names), n / fps, fps, res))
    print("\n  LED     predicted        measured      err     SNR   verdict")
    rows = {}
    for j, nm in enumerate(names):
        b = None
        if nm.startswith("PCL"):
            b = int(nm[3])
        elif nm.startswith("PCH"):
            b = 8 + int(nm[3])
        x = (series[:, j] > thr).astype(float)
        x = x - x.mean()
        x = x - np.polyval(np.polyfit(t, x, 3), t)
        X = np.abs(np.fft.rfft(x * w))
        band = (fr > 0.22) & (fr < fps / 2)
        if not band.any() or X[band].max() == 0:
            print("  %-6s  (no signal)" % nm)
            continue
        floor = np.median(X[band])
        i = int(np.argmax(X[band]))
        fmeas, snr = fr[band][i], X[band][i] / (floor or 1)
        if b is None:
            print("  %-6s  %-14s  %7.3f Hz          %5.1fx  (not a PC bit)" % (nm, "-", fmeas, snr))
            continue
        ftrue = inst / 2 ** (b + 1)
        k = round(ftrue / fps)
        fpred = abs(ftrue - k * fps)
        rows[nm] = (b, ftrue, fmeas, snr)
        if not (0.22 < fpred < fps / 2):
            print("  %-6s  %7.3f Hz too slow/fast to appear in this clip" % (nm, ftrue))
            continue
        err = abs(fmeas - fpred) / fpred * 100
        ok = "MATCH" if (abs(fmeas - fpred) <= 2 * res and snr > 4) else "no"
        alias = "" if abs(ftrue - fpred) < 0.01 else " (alias of %.1f Hz)" % ftrue
        print("  %-6s  %7.3f Hz%-18s %7.3f Hz  %5.1f%%  %5.1fx  %s"
              % (nm, fpred, alias, fmeas, err, snr, ok))

    # the ladder: every bit must run at half the rate of the one above it
    order = [nm for nm in ("PCL%d" % i for i in range(8)) if nm in rows] + \
            [nm for nm in ("PCH%d" % i for i in range(8)) if nm in rows]
    if len(order) >= 2:
        print("\n  ladder check -- consecutive bits halve; a skipped bit doubles the step:")
        for a, bnm in zip(order, order[1:]):
            ba, ra = rows[a][0], rows[a][1]
            bb, rb = rows[bnm][0], rows[bnm][1]
            want = 2.0 ** (bb - ba)
            gap = "" if bb - ba == 1 else "  (%d bits not labelled between)" % (bb - ba - 1)
            print("    %-6s -> %-6s  ratio %6.3f, expected %6.3f  %s%s"
                  % (a, bnm, ra / rb, want,
                     "ok" if abs(ra / rb - want) < 0.01 * want else "MISMATCH", gap))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clock", type=float, required=True, help="Phi0 in Hz")
    ap.add_argument("--labels", help="JSON from tools/led_picker.py: {name: [y,x]}")
    ap.add_argument("--fps", type=float, default=29.9, help="video frame rate")
    ap.add_argument("--cycles", type=float, default=2, help="cycles per instruction (NOP=2)")
    ap.add_argument("--frames", help="directory of extracted frames; omit for predictions only")
    ap.add_argument("--low", type=float, default=0.22, help="lowest trusted frequency")
    ap.add_argument("--threshold", type=float, default=80, help="redness threshold for an LED")
    ap.add_argument("--snr", type=float, default=5.0)
    args = ap.parse_args()

    inst, preds = predictions(args.clock, args.fps, args.cycles)
    hi = args.fps / 2
    print("clock %g Hz / %g cycles = %g instructions/s" % (args.clock, args.cycles, inst))
    print("filmed at %g fps, so anything above %.2f Hz folds back\n" % (args.fps, hi))
    print("  PC bit   toggles at      appears at")
    for b, f, fo in preds:
        vis = "" if args.low < fo < hi else "   (outside usable band)"
        print("  %-6s %10.2f Hz  %8.3f Hz%s" % (name(b), f, fo, vis))

    if args.frames and not args.labels:
        analyse(args.frames, args.fps, preds, args.low, hi, args.threshold, args.snr)
    if args.frames and args.labels:
        analyse_labelled(args.frames, args.fps, args.labels, args.clock,
                         args.cycles, args.threshold * 0.75)


if __name__ == "__main__":
    main()
