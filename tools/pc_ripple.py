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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clock", type=float, required=True, help="Phi0 in Hz")
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

    if args.frames:
        analyse(args.frames, args.fps, preds, args.low, hi, args.threshold, args.snr)


if __name__ == "__main__":
    main()
