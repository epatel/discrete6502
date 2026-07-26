# pico-controller — firmware for the discrete6502 bring-up Pico

The board carries an unpopulated **Raspberry Pi Pico 2 W** site wired (through
factory-fitted 1k series resistors) to the CPU's data bus, 14 address bits,
clock, reset, R/W and SYNC. With a Pico soldered on and one of these firmwares
flashed, the Pico is **clock master and memory emulator**: the 6502 runs real
programs with no other hardware attached.

## Projects

| Folder | Purpose |
|---|---|
| `common/` | Shared bus engine (`bus6502.c/h`): pin map, clocking, memory serving, trace ring, reset — plus `functest.c/h` (functional-test watcher) and the SDK import cmake |
| `tester/` | **Bring-up harness.** USB serial CLI: reset, run/trace N cycles, single-step instructions, peek/poke memory, clock speed control, Intel-hex image load, and the functional-test runner. Default image: an A-register counter loop (watch the A LEDs count). |
| `general/` | **Free-runner.** Boots the CPU and lets it run; memory-mapped char-out port at `$3F00` prints to USB serial. Default image prints `HELLO 6502` forever. |

Add new projects as sibling folders (`pico-controller/<name>/`) reusing `common/`.

## Pin map (fixed by the board — do not change)

| Pico GPIO | Signal | Direction (Pico view) |
|---|---|---|
| GP0–7 | db0–7 | bidirectional |
| GP8–21 | ab0–13 | in |
| GP22 | clk0 | out (clock master) |
| GP26 | /res | out, open-drain |
| GP27 | r/w | in |
| GP28 | sync | in |

The CPU sees only 14 address bits: memory is a **16 KB image, mirrored** across
the 64 KB space. The reset vector `$FFFC/D` is offset `0x3FFC/D` in the image.

## Logic levels — read before first power-up

The Pico is a 3.3 V device; the CPU core is designed for 5 V. This is the one
**unresolved hardware question** for bring-up (it does not affect the PCB):

- **Inputs to the Pico** (db on writes, ab, rw, sync at 5 V): the 1k series
  resistors limit clamp current to ~1.4 mA per pin — the common practical
  arrangement, though formally out of RP2350 spec. Acceptable for bring-up;
  don't leave the CPU powered at 5 V with the Pico unpowered.
- **Clock drive**: **the board has no pull-up on clk0.** It is a pure input --
  two FET gates, a 100R series resistor and the clamp diodes, nothing that
  holds a level -- so the clock source must drive it *push-pull*. An
  open-drain driver would pull it low and then leave it floating, which a
  dynamic CPU cannot survive. `bus_init(false)` (the default) is therefore the
  correct mode; `bus_init(true)` is only usable if you first croc-clip an
  external **10k from the Φ0 bond pad to the VCC bond pad**.
- **A 3.3 V clock into a 5 V core is fine**, and needs no such pull-up.
  clk0 does not gate the pass transistors: it drives two pull-down gates, and
  the internal clock phases (`cclk`, 482 gates; `cp1`, 198 gates) are
  regenerated on-board at full VCC swing. Simulated, a 3.3 V clk0 into a 5 V
  core gives an input-inverter low of 1.7 mV and 17 ns of delay, against
  1.4 mV / 7 ns for a 5 V clock -- no functional difference.
- **Recommended first bring-up**: run the whole CPU at **VCC = 3.3 V** with the
  default push-pull clock — one supply domain, no level questions. This is
  **simulation-cleared**: `sim/passpair_33v.sp` (2026-07-25) shows the dynamic
  latches still work at 3.3 V and even 3.0 V — the clock-edge bootstrap keeps
  the stored '1' at or above the rail. Expect the register LEDs to be dim
  (0.67 mA vs 1.42 mA at 5 V — `sim/led_tap.sp`) — cosmetic, not a fault. Then
  move to 5 V for full margin, brighter LEDs and a faster usable clock,
  keeping the same push-pull 3.3 V clock drive.

## Powering

The Pico's VSYS (pin 39) is tied to board VCC; GNDs are shared.

- **Bench supply** on the VCC/VSS bond pads (croc clips) powers board *and*
  Pico. USB may be connected simultaneously for serial.
- **USB-only demo mode**: with pin 39 soldered, the Pico's USB powers the
  whole board — ~0.35 A at ~4.8 V typical, up to ~0.65 A worst case (every
  pull-up low and every LED lit). Fine from USB-3 or a charger; a legacy
  500 mA port may not be.
- **For the 3.3 V bring-up: leave the pin-39 castellation UNSOLDERED at
  first.** With it soldered + USB plugged, VSYS drags board VCC to ~4.8 V
  and a 3.3 V bench setting cannot win. Unsoldered: USB powers the Pico,
  the bench powers the board at any voltage, grounds stay shared. Solder
  pin 39 once you move to 5 V operation.

## Build

Requires the [pico-sdk](https://github.com/raspberrypi/pico-sdk) (2.x for RP2350)
and the ARM GCC toolchain. **Verified to build 2026-07-26** with pico-sdk 2.1.1
and arm-none-eabi-gcc: `tester` 37 KB text / 32 KB bss, `general` similar — the
16 KB memory image and the 1024-entry trace ring dominate bss and fit RP2350's
520 KB with room to spare. Only the `lib/tinyusb` submodule is needed; the
btstack / cyw43 / lwip warnings are expected, as neither firmware uses the radio.

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
cd pico-controller/tester        # or general/
cmake -B build && cmake --build build -j
```

Flash: hold BOOTSEL while plugging USB, then copy `build/tester.uf2` to the
mass-storage device (or `picotool load -f build/tester.uf2`).

## Using the tester

Connect a serial terminal to the Pico's USB port (any baud), then:

```
R          # reset sequence
t 32       # run 32 cycles, watch the bus: cycle addr data r/W SYNC
s 5        # step 5 instructions
x 300 10   # hexdump $0300.. — the counter byte lives here
p 100      # slow the clock to 5 kHz (half-period 100 us)
L          # load an Intel hex image pasted into the terminal
k on       # arm the functional-test watcher (see below)
g          # free-run with the watcher until a self-loop
```

A healthy CPU after `R` shows the 7-cycle reset sequence, a vector fetch at
`3FFC/3FFD`, then the program's fetch/execute rhythm with SYNC marking each
opcode. The default image increments A forever — the A-register LEDs count in
binary and `$0300` follows.

## Running the 6502 functional test suite

[Klaus Dormann's `6502_65C02_functional_tests`](https://github.com/Klaus2m5/6502_65C02_functional_tests)
(GPLv3) is the standard acceptance test for 6502 *re-implementations* — which
is what this board is, rather than an emulator. It fits our hardware: with the
stock configuration (`zero_page = $0A`, `data_segment = $200`,
`code_segment = $400`, 13.1 kB of code) the image ends around `$3800`, inside
the 16 KB mirrored window, leaving the reset vector at `$3FFC` clear. Its own
`ram_top` option even offers `$40 = 16k` as a preset for mirrored systems, so
**the ab14/ab15 sacrifice does not block it.**

Assemble it with `as65 -l -m -s2 -w -h0` (the `-s2` gives Intel hex), then:

```
p 50          # start at the conservative default clock
L             # then paste the .hex file into the terminal
m 3FFC 00 04  # start at $0400: the suite's own RES vector points at res_trap
k on          # watcher on (test_case defaults to $0200)
R             # reset
g             # go — runs until a self-loop, printing progress
```

The suite has no I/O, so the watcher reads its two side channels off the bus:

- **Progress** — every write to `test_case` is a "sub-test passed" marker,
  printed as `[functest] test $NN at cycle N (+delta)`. `$F0` means all opcode
  tests are done and the final RAM-integrity check has started.
- **Verdict** — pass *and* fail are both branch-to-self loops, so the watcher
  reports any address whose opcode fetch repeats 4 times and stops the run.
  Match it against your assembly listing: the `success` address means **PASS**;
  anything else is the trap for the opcode immediately above it.

Budget the time. The full pass is order 10⁷–10⁸ cycles, so at 10–20 kHz it is
an **hours-long, ideally overnight run** — the printed cycle counts will give
the exact figure the first time. Run the much shorter `6502_decimal_test.a65`
first: decimal mode comes free from the visual6502 netlist and is the thing
emulators most often get wrong.

`g` takes an optional cycle cap (`g 500000`) and any keypress interrupts it.

## Reading the LEDs

The 55 register LEDs sit at their die-true positions inside the transistor
field — there is no room for per-LED silk labels (measured: only 3 of 55 have
a pad-free spot even at 1.0 mm text), so use `gen/led_map.svg` as the
reference. Layout:

| Register | Column | Order |
|---|---|---|
| Y | x ≈ 60 mm | bit 0 top → bit 7 bottom |
| X | x ≈ 64 mm | bit 0 top → bit 7 bottom |
| S | x ≈ 75 mm | bit 0 top → bit 7 bottom |
| A | x ≈ 145 mm | bit 0 top → bit 7 bottom |
| PCH | x ≈ 164 mm | bit 0 top → bit 7 bottom |
| PCL | x ≈ 190 mm | bit 0 top → bit 7 bottom |

All six register columns span y ≈ 183–270 mm. The 7 **P status flags** are not
in a row — they sit where the die puts them, in the control-logic band:
`I(197,116) B(212,161) C(216,144) D(223,147) V(238,153) Z(242,161) N(264,144)`
(x, y in mm from the top-left of the front view).

The tester's default image increments A forever, so the A column at x ≈ 145 mm
should count in binary — the quickest visual proof the CPU is alive.

## Clock speed — start slow

The firmware default is a **50 µs half-period (10 kHz)**, not the 50 kHz the
project originally targeted. `sim/fanout_speed.sp` found the real ceiling: the
decode-PLA input lines drive up to 71 discrete gates (≈ 1.9 nF) behind a single
10k pull-up, so after the pull-down releases, the receiving stage needs ~7 µs at
5 V (~11 µs at 3.3 V) just to flip, and ~25 µs for the line to reach a
comfortable level. A 50 kHz clock leaves only a 10 µs half-cycle — marginal at
5 V, too short at 3.3 V.

At bring-up: start at the default, confirm correct execution, then walk the
clock up with `p` (`p 25` = 20 kHz, `p 10` = 50 kHz) and find where it breaks.
The failure mode should be instructive — expect decode errors first, since the
PLA input lines are the slowest nets on the board.

## Roadmap

- PIO-based bus engine (cycle-accurate, faster than bit-banging, frees the CPU)
- Host-side loader script (the `L` command already takes Intel hex by paste;
  a script would make overnight functional-test runs unattended)
- Lock-step co-verification against `tools/switchsim.py` traces (golden-model
  compare during bring-up — strongest possible debug tool)
- Address/data-bus LED support if the optional LEDs are ever added
