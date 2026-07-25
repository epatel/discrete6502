# pico-controller — firmware for the discrete6502 bring-up Pico

The board carries an unpopulated **Raspberry Pi Pico 2 W** site wired (through
factory-fitted 1k series resistors) to the CPU's data bus, 14 address bits,
clock, reset, R/W and SYNC. With a Pico soldered on and one of these firmwares
flashed, the Pico is **clock master and memory emulator**: the 6502 runs real
programs with no other hardware attached.

## Projects

| Folder | Purpose |
|---|---|
| `common/` | Shared bus engine (`bus6502.c/h`): pin map, clocking, memory serving, trace ring, reset — plus the SDK import cmake |
| `tester/` | **Bring-up harness.** USB serial CLI: reset, run/trace N cycles, single-step instructions, peek/poke memory, clock speed control. Default image: an A-register counter loop (watch the A LEDs count). |
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
and the ARM GCC toolchain:

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
```

A healthy CPU after `R` shows the 7-cycle reset sequence, a vector fetch at
`3FFC/3FFD`, then the program's fetch/execute rhythm with SYNC marking each
opcode. The default image increments A forever — the A-register LEDs count in
binary and `$0300` follows.

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
- Binary image upload protocol + host-side loader script
- Lock-step co-verification against `tools/switchsim.py` traces (golden-model
  compare during bring-up — strongest possible debug tool)
- Address/data-bus LED support if the optional LEDs are ever added
