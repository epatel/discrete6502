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
- **Clock drive**: the pass-transistor bootstrap (see `cards/pass-pair-validation.md`)
  assumes full-rail clock swing; a 3.3 V push-pull clock into a 5 V core
  under-drives the pass gates. **The board has no pull-up on clk0**, so
  open-drain needs an external one: croc-clip a **10k from the Φ0 bond pad to
  the VCC bond pad**, then `bus_init(true)` gives a full-swing 5 V clock
  (slower edges — start slow, `p 50` = 10 kHz).
- **Recommended first bring-up**: run the whole CPU at **VCC = 3.3 V** with the
  default push-pull clock — one supply domain, no level questions; 2N7002
  threshold margins are thinner, so treat it as a logic smoke test. Then move
  to 5 V + external clk pull-up + open-drain clock for full-margin operation.
  (Worth SPICE-checking the 3.3 V pass-pair case before boards arrive —
  open item in project-plan.md.)

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

## Roadmap

- PIO-based bus engine (cycle-accurate, faster than bit-banging, frees the CPU)
- Binary image upload protocol + host-side loader script
- Lock-step co-verification against `tools/switchsim.py` traces (golden-model
  compare during bring-up — strongest possible debug tool)
- Address/data-bus LED support if the optional LEDs are ever added
