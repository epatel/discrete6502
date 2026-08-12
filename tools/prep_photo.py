#!/usr/bin/env python3
"""Make a phone photo fit to publish: downscale, strip metadata, re-encode.

The docs site is public, so photos straight off a phone are wrong twice over —
they are several megabytes each, and their EXIF carries a capture timestamp and
usually GPS coordinates. This rebuilds the image from pixel data alone, so no
metadata block survives into the output.

    python3 tools/prep_photo.py <src> <dst> [--max 1600] [--quality 82]

1600 px on the long edge is the convention for docs/img (see the LED map and the
rework renders).
"""
import argparse
import sys
from pathlib import Path

from PIL import Image


def prep(src: Path, dst: Path, max_edge: int, quality: int) -> None:
    im = Image.open(src)
    had_exif = bool(im.getexif())
    im = im.convert("RGB")

    scale = min(1.0, max_edge / max(im.size))
    if scale < 1.0:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)

    # Rebuild from raw pixels so nothing in .info (EXIF, ICC, XMP) rides along.
    clean = Image.new("RGB", im.size)
    clean.putdata(list(im.getdata()))
    clean.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)

    check = Image.open(dst)
    assert not check.getexif(), f"{dst}: metadata survived"
    print(
        f"{src.name} -> {dst.name}  "
        f"{im.width}x{im.height}  "
        f"{src.stat().st_size / 1e6:.1f} MB -> {dst.stat().st_size / 1024:.0f} KB"
        f"  (exif {'stripped' if had_exif else 'none'})"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--max", type=int, default=1600)
    ap.add_argument("--quality", type=int, default=82)
    a = ap.parse_args()
    if not a.src.is_file():
        print(f"no such file: {a.src}", file=sys.stderr)
        return 1
    prep(a.src, a.dst, a.max, a.quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
