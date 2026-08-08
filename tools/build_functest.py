#!/usr/bin/env python3
"""Build Klaus Dormann's 6502 test suites into images this board can run.

The suite lives in a sibling checkout (default ../6502_65C02_functional_tests)
and assembles only with AS65 1.42, an i386 binary; that repo's BUILDING.md
establishes the working recipe on Apple Silicon (docker --platform linux/386).
This script drives that recipe and then does the four board-specific things it
does not cover:

  1. Configures the source for our memory: ram_top = $40, because the Pico
     serves a 16 KB image mirrored across the 64 KB space (only ab0..ab13 reach
     the connector -- see project-plan.md 2026-07-22).
  2. Folds the image into 16 KB the same way the hardware does, and *fails* if
     two different bytes land on one 14-bit address. The suite's vectors at
     $fffa..$ffff alias onto $3ffa..$3fff, so this is a real risk, not a
     theoretical one.
  3. Patches the reset vector. The suite points RES at res_trap on purpose, so
     an unpatched image traps immediately instead of running.
  4. Extracts the verdict map from the listing. Pass and fail are both PC
     self-loops and are told apart only by address, so an address -> source-line
     table is what makes a failed run diagnosable.

Outputs land in gen/functest/. Usage:

    python3 tools/build_functest.py             # both tests
    python3 tools/build_functest.py functional
    python3 tools/build_functest.py decimal --suite /path/to/checkout
"""

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys

# The Pico sees 14 address bits, so the image is 16 KB mirrored (bus6502.h).
IMAGE_SIZE = 0x4000
IMAGE_MASK = IMAGE_SIZE - 1
# $3ffa..$3fff are where the mirrored NMI/RES/IRQ vectors land.
VECTOR_BASE = 0x3FFA
RESET_VECTOR = 0x3FFC

DOCKER_IMAGE = "i386/debian:bullseye-slim"
AS65_SWITCHES = ["-l", "-m", "-s2", "-w", "-h0"]

# Self-loop encodings. A trap is an instruction whose target is itself: either
# JMP to its own address, or a conditional branch with displacement -2.
BRANCH_OPCODES = {
    0x10: "bpl", 0x30: "bmi", 0x50: "bvc", 0x70: "bvs",
    0x90: "bcc", 0xB0: "bcs", 0xD0: "bne", 0xF0: "beq",
}


class Test:
    """One buildable test: its source, config edits, and entry point."""

    def __init__(self, name, source, entry_label, edits, progress, notes):
        self.name = name
        self.source = source
        self.entry_label = entry_label
        self.edits = edits          # list of (old, new, required_count)
        self.progress = progress    # (address, description) or None
        self.notes = notes


# The decimal test ends on `db $db` -- a 65C02 STP, which is an undefined
# opcode on NMOS and does something unspecified rather than halting. It also
# reports its result in a variable rather than by where it stops. Both are
# replaced by the convention our firmware detects: two distinct self-loops.
DECIMAL_END = """end_of_test macro
                lda ERROR       ;discrete6502: ERROR is 0 on pass, 1 on fail
                bne dec_fail
dec_pass        jmp dec_pass    ;PASS  -- self-loop, distinct address
dec_fail        jmp dec_fail    ;FAIL  -- self-loop, distinct address
            endm"""

# The decimal test emits no interrupt vectors, so NMI and IRQ would be $ffff and
# a spurious interrupt would execute whatever the mirrored image holds there.
# That is not hypothetical on this board: irq and nmi carry only a 100R and the
# clamp diodes -- no pull-up (unlike rdy and so, which have 10k) -- and the Pico
# does not drive either. Both float unless tied high at the bond pads. Give them
# a self-loop of their own so a spurious interrupt is identifiable rather than
# indistinguishable from a decimal-mode failure.
DECIMAL_VECTORS = """int_trap    jmp int_trap    ;discrete6502: spurious NMI or IRQ landed here

            org $fffa       ;mirrors to $3ffa in the 16 KB image
            dw  int_trap    ;NMI
            dw  TEST        ;RES
            dw  int_trap    ;IRQ

        end TEST"""

TESTS = {
    "functional": Test(
        name="6502_functional_test",
        source="6502_functional_test.a65",
        entry_label="start",
        edits=[
            # RAM integrity checking, set to our 16 KB mirrored map. The suite
            # documents $40 as exactly this case.
            ("\nram_top = -1", "\nram_top = $40", 1),
        ],
        progress=(0x0200, "test_case -- the current test number, 1..N"),
        notes="report=0 is forced: report=1 needs 3.5 kB we do not have "
              "(measured: it ends at $466b, past the $3ffa ceiling).",
    ),
    "decimal": Test(
        name="6502_decimal_test",
        source="6502_decimal_test.a65",
        entry_label="TEST",
        edits=[
            ("""end_of_test macro
                db  $db     ;execute 65C02 stop instruction
            endm""", DECIMAL_END, 1),
            ("        end TEST", DECIMAL_VECTORS, 1),
        ],
        progress=(0x0001, "N2 -- the outer loop counter, 0..255 twice"),
        notes="Bruce Clark's decimal test. ~1 minute at 1 MHz, so roughly "
              "100 minutes at 10 kHz and 50 at 20 kHz.",
    ),
}


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def unpack_assembler(suite, build):
    """Unpack AS65 from the suite's own zip. Idempotent."""
    as65 = os.path.join(build, "as65", "as65")
    if not os.path.exists(as65):
        run(["unzip", "-o", "-q", os.path.join(suite, "as65_142.zip"),
             "-d", os.path.join(build, "as65")])
    os.chmod(as65, 0o755)
    return as65


def apply_edits(text, edits, source_name):
    """Apply configuration edits, refusing to guess if the source has moved."""
    for old, new, want in edits:
        got = text.count(old)
        if got != want:
            raise SystemExit(
                f"{source_name}: expected {want} occurrence(s) of\n"
                f"  {old!r}\nbut found {got}. The suite source has changed; "
                f"re-check the config block before trusting this build.")
        text = text.replace(old, new)
    return text


def assemble(build, stem):
    """Assemble <stem>.a65 in build/ via the i386 AS65 under docker."""
    cwd = os.path.abspath(build)
    proc = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/386",
         "-v", f"{cwd}/as65:/as65", "-v", f"{cwd}:/out", "-w", "/out",
         DOCKER_IMAGE, "/as65/as65", *AS65_SWITCHES, f"{stem}.a65"],
        capture_output=True, text=True)
    lst = os.path.join(build, f"{stem}.lst")
    # AS65 reports errors in the listing, and sprays progress on stderr.
    if not os.path.exists(lst):
        raise SystemExit(f"assembly produced no listing.\n{proc.stderr[-2000:]}")
    tail = open(lst, errors="replace").read()[-4000:]
    m = re.search(r"(\d+|No) errors? in pass 2", tail)
    if not m:
        raise SystemExit("could not find the pass-2 error count in the listing")
    if m.group(1) != "No":
        raise SystemExit(f"assembly failed: {m.group(0)}")
    return lst


def parse_ihex(path):
    """Return {address: byte} from an Intel HEX file, checksums verified."""
    out = {}
    for lineno, line in enumerate(open(path), 1):
        line = line.strip()
        if not line.startswith(":"):
            continue
        d = bytes.fromhex(line[1:])
        if (sum(d) & 0xFF) != 0:
            raise SystemExit(f"{path}:{lineno}: bad Intel HEX checksum")
        count, addr, rectype = d[0], (d[1] << 8) | d[2], d[3]
        if rectype == 0:
            for i in range(count):
                out[addr + i] = d[4 + i]
        elif rectype == 1:
            break
        else:
            raise SystemExit(f"{path}:{lineno}: unsupported record type {rectype}")
    return out


def fold_to_image(emitted):
    """Fold a 64 KB address map into our mirrored 16 KB image.

    Aliasing is the point of the exercise, so a genuine collision -- two
    different values on one 14-bit address -- is a hard error rather than a
    last-writer-wins.
    """
    image = bytearray(b"\xff" * IMAGE_SIZE)
    written = {}
    for addr, val in sorted(emitted.items()):
        folded = addr & IMAGE_MASK
        if folded in written and written[folded] != (addr, val) and \
           image[folded] != val:
            raise SystemExit(
                f"aliasing collision at ${folded:04x}: ${written[folded][0]:04x}"
                f"=${image[folded]:02x} vs ${addr:04x}=${val:02x}. The image "
                f"does not fit a 16 KB mirrored map.")
        image[folded] = val
        written[folded] = (addr, val)
    return image, written


def find_label(lst_path, label):
    """Find the address AS65 assigned to a label, from the pass-2 listing."""
    # Listing lines look like "0400 : d8               start   cld"
    pat = re.compile(r"^([0-9a-f]{4}) [:=].*?(?<![\w.])" + re.escape(label) +
                     r"(?![\w.])", re.IGNORECASE)
    for line in open(lst_path, errors="replace"):
        if ">" in line[:40]:      # macro expansion, not a definition
            continue
        m = pat.match(line)
        if m:
            return int(m.group(1), 16)
    return None


def scan_traps(lst_path):
    """Extract every PC self-loop, with source line and current test number.

    Returns (traps, progress_writes) where traps is a list of dicts. This is
    the table you consult when a run stops: the address alone says pass or
    fail, and the source line says which test.
    """
    line_re = re.compile(r"^([0-9a-f]{4}) : ([0-9a-f]+)\s*(.*)$", re.IGNORECASE)
    traps = []
    test_num = 0
    pending_imm = None
    for lineno, raw in enumerate(open(lst_path, errors="replace"), 1):
        m = line_re.match(raw)
        if not m:
            continue
        addr = int(m.group(1), 16)
        hexbytes = m.group(2)
        if len(hexbytes) % 2:
            continue
        code = bytes.fromhex(hexbytes)
        text = m.group(3).replace(">", " ").strip()

        # Track test_case progress: `lda #NN` then `sta $0200`.
        if len(code) == 2 and code[0] == 0xA9:
            pending_imm = code[1]
        elif len(code) == 3 and code[0] == 0x8D and \
                (code[2] << 8 | code[1]) == 0x0200:
            if pending_imm is not None:
                test_num = pending_imm
        else:
            if not (len(code) == 2 and code[0] == 0xA9):
                pending_imm = None

        kind = None
        if len(code) == 3 and code[0] == 0x4C and \
                (code[2] << 8 | code[1]) == addr:
            kind = "jmp *"
        elif len(code) == 2 and code[0] in BRANCH_OPCODES and code[1] == 0xFE:
            kind = BRANCH_OPCODES[code[0]] + " *"
        if kind:
            traps.append({
                "address": f"${addr:04x}",
                "kind": kind,
                "test_case": test_num,
                "listing_line": lineno,
                "source": text[:100],
            })
    return traps


def write_ihex(path, image, skip_ff=True):
    """Write the 16 KB image as Intel HEX for the tester's `L` command."""
    recs = []
    runs = []
    start = None
    for a in range(IMAGE_SIZE + 1):
        present = a < IMAGE_SIZE and not (skip_ff and image[a] == 0xFF)
        if present and start is None:
            start = a
        elif not present and start is not None:
            runs.append((start, a))
            start = None
    for lo, hi in runs:
        a = lo
        while a < hi:
            n = min(16, hi - a)
            body = bytes([n, (a >> 8) & 0xFF, a & 0xFF, 0]) + image[a:a + n]
            recs.append(":" + body.hex().upper() +
                        f"{(-sum(body)) & 0xFF:02X}")
            a += n
    recs.append(":00000001FF")
    open(path, "w").write("\n".join(recs) + "\n")
    return sum(hi - lo for lo, hi in runs)


def build(test, suite, outdir):
    build_dir = os.path.join(suite, "build")
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    unpack_assembler(suite, build_dir)

    src_path = os.path.join(suite, test.source)
    text = apply_edits(open(src_path).read(), test.edits, test.source)
    stem = test.name + "_d6502"
    open(os.path.join(build_dir, f"{stem}.a65"), "w").write(text)
    # report.i65 is included by name when report=1; harmless to stage always.
    for inc in ("report.i65",):
        s = os.path.join(suite, inc)
        if os.path.exists(s):
            shutil.copy(s, build_dir)

    lst = assemble(build_dir, stem)
    emitted = parse_ihex(os.path.join(build_dir, f"{stem}.hex"))
    image, written = fold_to_image(emitted)

    entry = find_label(lst, test.entry_label)
    if entry is None:
        raise SystemExit(f"could not locate entry label {test.entry_label!r}")

    # The suite aims RES at res_trap deliberately; point it at the entry.
    before = image[RESET_VECTOR] | (image[RESET_VECTOR + 1] << 8)
    image[RESET_VECTOR] = entry & 0xFF
    image[RESET_VECTOR + 1] = (entry >> 8) & 0xFF

    highest = max(a & IMAGE_MASK for a in emitted if (a & IMAGE_MASK) < VECTOR_BASE)
    traps = scan_traps(lst)

    # Identify the one self-loop that means success. Both suites reach it via a
    # comment we control or that upstream writes: the functional test's success
    # macro emits ";test passed", and our decimal end_of_test emits ";PASS".
    pass_addr = None
    for tr in traps:
        if "test passed" in tr["source"].lower() or ";PASS" in tr["source"]:
            if pass_addr is not None:
                raise SystemExit("more than one self-loop looks like PASS; "
                                 "the marker comment is ambiguous")
            pass_addr = int(tr["address"].lstrip("$"), 16)
            tr["kind"] += " (PASS)"

    hex_path = os.path.join(outdir, f"{test.name}.hex")
    nbytes = write_ihex(hex_path, image)
    csv_path = os.path.join(outdir, f"{test.name}_traps.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["address", "kind", "test_case",
                                          "listing_line", "source"])
        w.writeheader()
        w.writerows(traps)

    return {
        "test": test, "entry": entry, "reset_was": before, "highest": highest,
        "traps": traps, "hex": hex_path, "csv": csv_path, "bytes": nbytes,
        "lst": lst, "headroom": VECTOR_BASE - highest, "pass_addr": pass_addr,
    }


def report(r):
    t = r["test"]
    print(f"\n=== {t.name} ===")
    print(f"  entry point        ${r['entry']:04x} ({t.entry_label})")
    print(f"  reset vector       $3ffc patched ${r['reset_was']:04x} "
          f"-> ${r['entry']:04x}")
    print(f"  highest code byte  ${r['highest']:04x}  "
          f"({r['headroom']} bytes free below the $3ffa vectors)")
    print(f"  image bytes        {r['bytes']} of {IMAGE_SIZE}")
    if t.progress:
        addr, desc = t.progress
        print(f"  progress address   ${addr:04x}  {desc}")
        print(f"                     tester: k {addr:04X}")
    print(f"  self-loops found   {len(r['traps'])}"
          f"  ({len(r['traps']) - 1} of them are failure traps)")
    if r["pass_addr"] is not None:
        print(f"  PASS address       ${r['pass_addr']:04x}   <-- stopping here "
              f"means the suite passed")
        print(f"  FAIL addresses     every other self-loop; look it up in the "
              f"verdict map")
    else:
        print("  PASS address       NOT IDENTIFIED -- inspect the listing")
    print(f"  image              {r['hex']}")
    print(f"  verdict map        {r['csv']}")
    print(f"  listing            {r['lst']}")
    if t.notes:
        print(f"  note               {t.notes}")


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # default left as None: argparse validates a list default against `choices`
    # as a single value and rejects it.
    ap.add_argument("tests", nargs="*", choices=list(TESTS),
                    help="which tests to build (default: all)")
    ap.add_argument("--suite",
                    default=os.path.join(os.path.dirname(here),
                                         "6502_65C02_functional_tests"),
                    help="path to the Klaus Dormann checkout")
    ap.add_argument("--outdir", default=os.path.join(here, "gen", "functest"))
    args = ap.parse_args()

    suite = os.path.abspath(args.suite)
    if not os.path.exists(os.path.join(suite, "as65_142.zip")):
        raise SystemExit(f"no test suite at {suite} (expected as65_142.zip)")

    names = args.tests or list(TESTS)
    results = [build(TESTS[name], suite, args.outdir) for name in names]
    for r in results:
        report(r)
    print("\nLoad with the tester's `L` command, then `R` and `g`. The reset "
          "vector is already patched, so the `m 3FFC ..` step is not needed.")


if __name__ == "__main__":
    sys.exit(main())
