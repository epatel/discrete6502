#!/usr/bin/env python3
"""Turn gen/functest/ into a C source file the Pico firmware can link.

Why this is opt-in and why the output is never committed
--------------------------------------------------------
Klaus Dormann's test suite is **GPLv3**; this repository is CC BY-NC-SA 4.0
(inherited from visual6502's segdefs.js). Those licences are incompatible --
GPLv3 specifically forbids adding a NonCommercial restriction -- so a firmware
binary with the assembled test images baked into it is a combined work we could
not distribute under either.

Keeping the images as separate files in gen/functest/ is mere aggregation and is
fine. Compiling them in is not, if the result is shipped. So:

  * this generator runs only when you ask for it (cmake -DEMBED_FUNCTEST=ON),
  * its output (common/functest_images.c) is gitignored and never committed,
  * no assembled test bytes exist anywhere in the firmware source tree,
  * the combined artifact exists only on the machine that built it.

We also deliberately do NOT embed the `source` column of the traps CSV. Those
48 kB are Klaus's actual expression; a listing line number is a pointer to it
and is all the firmware needs to tell you where to look.

Usage
-----
    python3 tools/embed_functest.py [--functest-dir gen/functest]
                                    [--out pico-controller/common/functest_images.c]
"""
import argparse
import csv
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))

MEM_SIZE = 0x4000  # the CPU sees 14 address bits; the Pico serves a 16 KB image


def load_tests():
    """Progress addresses come from build_functest.py, not a second copy here.

    Importing it keeps one definition of where each test reports its progress
    ($0200 test_case for the functional test, $0001 N2 for the decimal one).
    The module is import-safe: everything executable is behind __main__.
    """
    import build_functest

    return build_functest.TESTS


def read_ihex(path):
    """Apply an Intel hex file into a zero-filled 16 KB image.

    Addresses are masked the way the hardware mirrors them, so the suite's
    $FFFA-$FFFF vector block lands at $3FFA-$3FFF exactly as the CPU sees it.
    A full image rather than a sparse record list is deliberate: it is what the
    memory looks like after loading, so an embedded run and a pasted run start
    from provably identical state.
    """
    mem = bytearray(MEM_SIZE)
    written = 0
    lo, hi = MEM_SIZE, -1
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith(":"):
                continue
            n = int(line[1:3], 16)
            addr = int(line[3:7], 16)
            rtype = int(line[7:9], 16)
            if rtype == 1:
                break
            if rtype != 0:
                continue
            body = bytes.fromhex(line[9:9 + 2 * n])
            for i, b in enumerate(body):
                a = (addr + i) & (MEM_SIZE - 1)
                mem[a] = b
                lo, hi = min(lo, a), max(hi, a)
            written += n
    return mem, written, lo, hi


def read_traps(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "addr": int(r["address"].lstrip("$"), 16) & (MEM_SIZE - 1),
                "kind": r["kind"],
                "test_case": int(r["test_case"]) & 0xFF,
                "line": int(r["listing_line"]),
            })
    rows.sort(key=lambda r: r["addr"])
    # One address cannot be two traps; if it were, the firmware's lookup would
    # have to report both and the CSV would be describing a listing we cannot
    # trust. Fail loudly rather than silently keeping the first.
    seen = {}
    for r in rows:
        if r["addr"] in seen and seen[r["addr"]] != r:
            raise SystemExit(f"{path}: two different traps at ${r['addr']:04x}")
        seen[r["addr"]] = r
    return list(seen.values())


def c_bytes(data, indent="    "):
    out = []
    for i in range(0, len(data), 16):
        out.append(indent + ",".join(f"0x{b:02X}" for b in data[i:i + 16]) + ",")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--functest-dir", default=os.path.join(HERE, "gen", "functest"))
    ap.add_argument("--out", default=os.path.join(
        HERE, "pico-controller", "common", "functest_images.c"))
    a = ap.parse_args()

    tests = load_tests()
    built = []
    for key, test in (("f", tests["functional"]), ("d", tests["decimal"])):
        hexpath = os.path.join(a.functest_dir, test.name + ".hex")
        csvpath = os.path.join(a.functest_dir, test.name + "_traps.csv")
        if not os.path.exists(hexpath):
            raise SystemExit(
                f"missing {hexpath}\n"
                "run tools/build_functest.py first (needs the Klaus Dormann checkout)")
        mem, written, lo, hi = read_ihex(hexpath)
        traps = read_traps(csvpath)
        sha = hashlib.sha256(open(hexpath, "rb").read()).hexdigest()
        built.append({
            "key": key, "test": test, "mem": mem, "written": written,
            "lo": lo, "hi": hi, "traps": traps, "sha": sha,
        })

    kinds = sorted({t["kind"] for b in built for t in b["traps"]})
    kind_idx = {k: i for i, k in enumerate(kinds)}

    L = []
    w = L.append
    w("// GENERATED by tools/embed_functest.py -- do not edit, do not commit.")
    w("//")
    w("// Contains assembled images of Klaus Dormann's 6502 test suite, which is")
    w("// GPLv3:  https://github.com/Klaus2m5/6502_65C02_functional_tests")
    w("// This file is gitignored on purpose. See the generator's docstring and")
    w("// gen/functest/README.md for why the firmware does not ship with it.")
    w("//")
    for b in built:
        w(f"// {b['test'].name}.hex  sha256 {b['sha']}")
    w("")
    w('#include "functest_images.h"')
    w("")
    w("static const char *const kind_name[] = {")
    for k in kinds:
        w(f'    "{k}",')
    w("};")
    w("")
    w("static const bool kind_pass[] = {")
    for k in kinds:
        w(f"    {'true' if '(PASS)' in k else 'false'},  // {k}")
    w("};")
    w("")

    for b in built:
        nm = b["test"].name
        w(f"// {nm}: {b['written']} bytes of image data spanning "
          f"${b['lo']:04X}-${b['hi']:04X}, in a zero-filled {MEM_SIZE // 1024} KB image.")
        w(f"static const uint8_t image_{b['key']}[{MEM_SIZE}] = {{")
        w(c_bytes(b["mem"]))
        w("};")
        w("")
        w(f"// {len(b['traps'])} traps, sorted by address for binary search.")
        w(f"static const functest_trap_t traps_{b['key']}[] = {{")
        for t in b["traps"]:
            w(f"    {{0x{t['addr']:04X}, {t['line']}, {t['test_case']}, "
              f"{kind_idx[t['kind']]}}},")
        w("};")
        w("")

    w("static const functest_image_t images[] = {")
    for b in built:
        t = b["test"]
        addr = t.progress[0] if t.progress else 0
        mem = b["mem"]
        nmi = mem[0x3FFA] | (mem[0x3FFB] << 8)
        irq = mem[0x3FFE] | (mem[0x3FFF] << 8)
        trap_addrs = {x["addr"] for x in b["traps"]}
        w(f'    {{\'{b["key"]}\', "{t.name}", image_{b["key"]}, {MEM_SIZE},')
        w(f"     traps_{b['key']}, "
          f"(uint16_t)(sizeof traps_{b['key']} / sizeof traps_{b['key']}[0]),")
        w(f"     0x{addr:04X}, 0x{nmi:04X}, 0x{irq:04X},")
        w(f"     {'true' if nmi in trap_addrs else 'false'}, "
          f"{'true' if irq in trap_addrs else 'false'}}},")
    w("};")
    w("")
    w("bool functest_images_available(void) { return true; }")
    w("")
    w("uint8_t functest_image_count(void) "
      "{ return (uint8_t)(sizeof images / sizeof images[0]); }")
    w("")
    w("const functest_image_t *functest_image_at(uint8_t i) {")
    w("    return i < functest_image_count() ? &images[i] : 0;")
    w("}")
    w("")
    w("const functest_image_t *functest_image(char key) {")
    w("    for (uint8_t i = 0; i < functest_image_count(); i++)")
    w("        if (images[i].key == key) return &images[i];")
    w("    return 0;")
    w("}")
    w("")
    w("const functest_trap_t *functest_trap_lookup(const functest_image_t *img,")
    w("                                            uint16_t addr) {")
    w("    if (!img || !img->traps) return 0;")
    w("    uint16_t lo = 0, hi = img->trap_count;  // sorted; binary search")
    w("    while (lo < hi) {")
    w("        uint16_t mid = (uint16_t)(lo + (hi - lo) / 2);")
    w("        if (img->traps[mid].addr == addr) return &img->traps[mid];")
    w("        if (img->traps[mid].addr < addr) lo = (uint16_t)(mid + 1);")
    w("        else hi = mid;")
    w("    }")
    w("    return 0;")
    w("}")
    w("")
    w("const char *functest_kind_name(uint8_t kind) {")
    w("    return kind < (sizeof kind_name / sizeof kind_name[0]) "
      "? kind_name[kind] : \"?\";")
    w("}")
    w("")
    w("bool functest_kind_is_pass(uint8_t kind) {")
    w("    return kind < (sizeof kind_pass / sizeof kind_pass[0]) "
      "&& kind_pass[kind];")
    w("}")

    text = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as fh:
        fh.write(text)

    total_traps = sum(len(b["traps"]) for b in built)
    print(f"{a.out}: {len(built)} images, {total_traps} traps, "
          f"{len(kinds)} trap kinds, {len(text) / 1024:.0f} KB of C")
    for b in built:
        print(f"  {b['key']}  {b['test'].name}: {b['written']} bytes, "
              f"{len(b['traps'])} traps, progress $"
              f"{(b['test'].progress[0] if b['test'].progress else 0):04X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
