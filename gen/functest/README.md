# Acceptance-test images — third-party, GPLv3

The `.hex` and `_traps.csv` files in this directory are **build outputs of
Klaus Dormann's 6502/65C02 functional test suite**, which is not our work.

| | |
|---|---|
| Upstream | <https://github.com/Klaus2m5/6502_65C02_functional_tests> |
| Author | Klaus Dormann (the decimal test is Bruce Clark's, distributed with it) |
| Licence | **GPL v3** |
| Produced by | `tools/build_functest.py` against a checkout of the above |

The rest of this repository is CC BY-NC-SA 4.0 (see `/LICENSE`). **That licence
does not apply to these files**, and cannot: GPLv3 forbids adding a
NonCommercial restriction. The two coexist here as separate works in one
directory — aggregation, not combination.

## What we changed, and why

Both images are upstream's source assembled with documented edits, all of them
in `tools/build_functest.py` where they can be read:

- **`ram_top = $40`** on the functional test — upstream's own preset for a 16 KB
  mirrored system, which is what the Pico presents (it decodes 14 address bits).
- **The reset vector is patched** to the entry label, so the tester's
  `m 3FFC 00 04` step is no longer needed.
- **The decimal test's `end_of_test`** emitted `db $db` — a 65C02 `STP`, which
  is an *undefined opcode on NMOS* and does something unspecified rather than
  halting. Replaced with two distinct self-loops branching on `ERROR`.
- **The decimal test emitted no interrupt vectors** at all. An `int_trap` and a
  vector block were added, because `irq` and `nmi` float on this board (100R and
  clamp diodes, no pull-up) and a spurious interrupt must be identifiable rather
  than indistinguishable from a decimal-mode failure.

Validated before any hardware existed: with stock configuration the toolchain
reproduces upstream's own committed `bin_files/6502_functional_test.bin` byte
for byte, and both generated images then *execute to PASS* in an emulator
against a mirrored 16 KB memory.

## Firmware note

`pico-controller/` can compile these images in, so the acceptance test needs no
37.6 kB terminal paste — but **only when you ask for it**:

```
cmake -B build -DEMBED_FUNCTEST=ON ..
```

It is off by default, and the generated `common/functest_images.c` is
gitignored, so **no firmware binary containing GPLv3 material is ever produced
or distributed by this repository**. A binary you build with the flag on is a
combined work: fine to build and use, not something to redistribute. See
`pico-controller/common/functest_images.h`.
