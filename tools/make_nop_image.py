#!/usr/bin/env python3
"""Emit a 16 KB all-$EA image as Intel hex: the NOP free-run, for thermal work.

WHY. tools/contention_duty.py measures each VCC-side FET's contention duty under
two workloads. An earlier version of this comment claimed those workloads differ
enormously for the adh sites and that this reconciled the 2026-08-24 thermal
image (no hot spots) with the 2026-08-25 one (80 C spots). THAT WAS WRONG: the
difference was an artifact of a short simulation pinning the address, and on
2026-08-26 a real NOP free-run ran every adh site hot. Why the 2026-08-24 sweep
saw nothing is unexplained.

Loading this image reproduces the 2026-08-24 condition through the Pico rather
than through a resistor tie-off, so the two thermal images differ in workload and
nothing else -- same board, same camera, same clock, same supply.

Every byte is $EA, the reset vector included: $3FFC/D reads EA EA, so the CPU
starts at $EAEA, which the board's 14 address bits fold to $2AEA, which is also
$EA. It fetches and increments and does nothing else, which is the point.

Usage:  python3 tools/make_nop_image.py [--out gen/nopfill.hex]
        then upload it from the panel's Program section.
"""
import argparse

SIZE = 0x4000
FILL = 0xEA  # NOP


def record(rtype, addr, data):
    body = [len(data), (addr >> 8) & 0xFF, addr & 0xFF, rtype] + list(data)
    return ":" + "".join("%02X" % b for b in body) + "%02X" % ((-sum(body)) & 0xFF)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="gen/nopfill.hex")
    args = ap.parse_args()

    lines = []
    for addr in range(0, SIZE, 32):
        lines.append(record(0x00, addr, [FILL] * 32))
    lines.append(record(0x01, 0, []))          # EOF
    text = "\n".join(lines) + "\n"
    with open(args.out, "w") as f:
        f.write(text)

    # Verify by parsing it back, rather than trusting the writer.
    mem = bytearray(SIZE)
    seen = bytearray(SIZE)
    for ln in text.strip().split("\n"):
        b = bytes.fromhex(ln[1:])
        assert (sum(b) & 0xFF) == 0, "bad checksum: " + ln
        n, hi, lo, t = b[0], b[1], b[2], b[3]
        if t == 0x01:
            break
        a = (hi << 8) | lo
        mem[a:a + n] = b[4:4 + n]
        seen[a:a + n] = b"\x01" * n
    assert all(seen), "gaps in the image"
    assert set(mem) == {FILL}, "not uniformly $%02X" % FILL
    print("wrote %s  (%d bytes of $%02X, %d records, %d bytes of hex)"
          % (args.out, SIZE, FILL, len(lines) - 1, len(text)))
    print("reset vector at $3FFC reads $%02X%02X -> PC $%04X -> folds to $%04X"
          % (mem[0x3FFD], mem[0x3FFC],
             mem[0x3FFC] | (mem[0x3FFD] << 8),
             (mem[0x3FFC] | (mem[0x3FFD] << 8)) & 0x3FFF))


if __name__ == "__main__":
    main()
