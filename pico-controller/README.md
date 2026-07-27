# pico-controller: firmware for the discrete6502 bring-up Pico

The board carries an unpopulated **Raspberry Pi Pico 2 W** site. Factory-fitted
1k series resistors wire it to the CPU data bus, 14 address bits, clock, reset,
R/W and SYNC. Solder a Pico on and flash one of these firmwares. The Pico then
becomes the **clock master and memory emulator**, and the 6502 runs real
programs with no other hardware attached.

## Projects

| Folder | Purpose |
|---|---|
| `common/` | Shared bus engine (`bus6502.c/h`): pin map, clocking, memory serving, trace ring, reset. Also `functest.c/h` (functional-test watcher), `ihex.c/h` (streaming Intel hex loader), `retention.c/h` (charge-retention measurement) and the SDK import cmake. |
| `tester/` | **Bring-up harness.** A USB serial CLI. It resets the CPU, runs or traces N cycles, steps instructions, reads and writes memory, sets the clock speed, loads an Intel hex image, and runs the functional test. The default image is an A-register counter loop. Watch the A LEDs count. |
| `general/` | **Free-runner.** It boots the CPU and lets it run. A memory-mapped character-output port at `$3F00` prints to USB serial. The default image prints `HELLO 6502` forever. |
| `wifi/` | **Browser control panel.** The same bus engine runs on core 1. WiFi and a small HTTP server run on core 0. Upload an Intel hex, run, stop, step, reset, set the clock, and watch the bus and the functional-test progress live. It is built for unattended overnight test runs. |

Add a new project as a sibling folder (`pico-controller/<name>/`). Reuse
`common/`.

## Pin map (fixed by the board, do not change)

| Pico GPIO | Signal | Direction (Pico view) |
|---|---|---|
| GP0–7 | db0–7 | bidirectional |
| GP8–21 | ab0–13 | in |
| GP22 | clk0 | out (clock master) |
| GP26 | /res | out, open-drain |
| GP27 | r/w | in |
| GP28 | sync | in |

The CPU sees only 14 address bits. Memory is a **16 KB image**, mirrored across
the 64 KB space. The reset vector `$FFFC/D` is at offset `0x3FFC/D` in the
image.

## Logic levels: read before first power-up

The Pico is a 3.3 V device. The CPU core runs at 5 V. This is the one
**unresolved hardware question** for bring-up. It does not affect the PCB.

- **Inputs to the Pico** (db on writes, ab, rw and sync at 5 V). The 1k series
  resistors limit the clamp current to about 1.4 mA per pin. This is the common
  practical arrangement, but it is formally outside the RP2350 specification.
  It is acceptable for bring-up. Do not leave the CPU powered at 5 V while the
  Pico has no power.
- **Clock drive.** The board has no pull-up on clk0. clk0 is a pure input: two
  FET gates, a 100R series resistor and the clamp diodes. Nothing holds a
  level. The clock source must therefore drive clk0 push-pull. An open-drain
  driver pulls clk0 low and then leaves it floating, and a dynamic CPU cannot
  survive that. `bus_init(false)` is the default and the correct mode.
  `bus_init(true)` works only if you first croc-clip an external **10k resistor
  from the Φ0 bond pad to the VCC bond pad**.
- **A 3.3 V clock into a 5 V core is safe**, and needs no pull-up. clk0 does
  not gate the pass transistors. It drives two pull-down gates, and the board
  regenerates the internal clock phases (`cclk`, 482 gates, and `cp1`, 198
  gates) at full VCC swing. In simulation, a 3.3 V clk0 into a 5 V core gives
  an input-inverter low of 1.7 mV and 17 ns of delay. A 5 V clock gives 1.4 mV
  and 7 ns. There is no functional difference.
- **Recommended first bring-up.** Run the whole CPU at **VCC = 3.3 V** with the
  default push-pull clock. This gives one supply domain and no level questions.
  Simulation clears it: `sim/passpair_33v.sp` (2026-07-25) shows that the
  dynamic latches still work at 3.3 V and at 3.0 V. The clock-edge bootstrap
  keeps the stored '1' at or above the rail. Expect dim register LEDs, 0.67 mA
  against 1.42 mA at 5 V (`sim/led_tap.sp`). The dim LEDs are cosmetic, not a
  fault. Then move to 5 V for full margin, brighter LEDs and a faster usable
  clock. Keep the same push-pull 3.3 V clock drive.

## Powering

Board VCC feeds the Pico VSYS pin (pin 39). The two grounds are common.

- **Bench supply.** Croc clips on the VCC and VSS bond pads power both the
  board and the Pico. You can connect USB at the same time for serial.
- **USB-only demo mode.** With pin 39 soldered, Pico USB power runs the whole
  board. This draws about 0.35 A at about 4.8 V typical, and up to 0.65 A worst
  case with every pull-up low and every LED lit. A USB-3 port or a charger
  supplies this. A legacy 500 mA port may not.
- **For the 3.3 V bring-up, leave the pin-39 castellation UNSOLDERED at
  first.** If pin 39 is soldered and USB is plugged in, VSYS pulls board VCC to
  about 4.8 V. A 3.3 V bench setting cannot win against it. Leave pin 39
  unsoldered. USB then powers the Pico, the bench supply powers the board at
  any voltage, and the grounds stay common. Solder pin 39 when you move to 5 V
  operation.

## Build

The build needs the [pico-sdk](https://github.com/raspberrypi/pico-sdk) (2.x
for RP2350) and the ARM GCC toolchain. The build was **verified on 2026-07-26**
with pico-sdk 2.1.1 and arm-none-eabi-gcc. `tester` is 37 KB text and 32 KB
bss, and `general` is similar. The 16 KB memory image and the 1024-entry trace
ring dominate bss. Both fit the 520 KB of the RP2350 with room to spare. The
build needs only the `lib/tinyusb` submodule. Expect btstack, cyw43 and lwip
warnings, because neither firmware uses the radio.

A `Makefile` here wraps the cmake commands:

```sh
make                 # tester + general
make wifi WIFI_SSID=yournet WIFI_PASSWORD=secret
make all-wifi        # all three
make size            # flash/RAM use of whatever is built
make flash-tester    # hold BOOTSEL while plugging USB first
make clean
```

Put the credentials in `pico-controller/wifi.local.mk`. Git ignores this file,
so the credentials stay out of your shell history:

```make
WIFI_SSID := yournet
WIFI_PASSWORD := secret
```

You can also run cmake directly:

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
cd pico-controller/tester        # or general/
cmake -B build && cmake --build build -j
```

The development machine is already set up. The SDK is at
**`~/Development/pico-sdk`**, version 2.1.1, with the `tinyusb`, `cyw43-driver`
and `lwip` submodules fetched. `btstack` and `mbedtls` are not needed.
`~/.zshrc` exports `PICO_SDK_PATH`, so `cmake -B build` works without more
setup. On another machine, clone the SDK and set the variable yourself. Nothing
in this repository depends on that path.

To flash a firmware:

1. Hold BOOTSEL and plug in the USB cable.
2. Copy `build/tester.uf2` to the mass-storage device.

You can also run `picotool load -f build/tester.uf2`.

The `wifi/` build also needs the `lib/cyw43-driver` and `lib/lwip` SDK
submodules. It needs credentials as well. The credentials have no defaults, so
nobody can commit them by accident:

```sh
cd pico-controller/wifi
cmake -B build -DWIFI_SSID=yournet -DWIFI_PASSWORD=secret && cmake --build build -j
```

Measured on 2026-07-26, `wifi` uses 342 KB of flash and 92 KB of RAM. This is
8% of the 4 MB flash and 18% of the 520 KB SRAM, and about 430 KB of RAM stays
free. The fixed `w43439A0` radio firmware blob is two thirds of the flash, not
code.

## The wifi control panel

Flash the firmware. Watch the USB serial output for `[wifi] http://<address>/`.
Open that address in a browser. The firmware serves the page from flash with no
external dependencies. There is no CDN and no framework. The page therefore
works on a bench network with no internet, and on a phone next to the board.

The controls are reset, run, stop, step-instruction, clock half-period,
functional-test watcher on and off, `vector→$0400`, and Intel hex upload. The
page shows the live bus cycle and the last 24 cycles. It also builds a log of
`test_case` progress and the final verdict.

**Why the firmware has this structure.** The bus engine runs on **core 1** and
touches nothing else. WiFi, lwIP and HTTP run on **core 0**. This split is not
tidiness. The board uses dynamic logic, so a stretched clock phase is a
correctness bug. Association and DHCP block for milliseconds at a time. Inside
the clock loop that is fatal. On another core it is invisible. Two consequences
matter before you edit the firmware:

- The firmware puts the watcher in **quiet mode** (`functest_set_quiet`). Pico
  `stdio_usb` blocks for up to 500 ms when a terminal is attached but does not
  read. A `printf` on core 1 would stretch a 50 µs clock phase ten thousand
  times. Progress reaches the browser through the shared snapshot instead.
- Both cores share the memory image. The firmware therefore returns `409` for a
  hex upload or a vector patch while the CPU runs. Stop the CPU first. The page
  buttons follow this order.

The per-cycle snapshot that core 0 reads is lock-free on purpose. Every field
is word-sized and atomic on ARM. The worst case is a display that mixes two
adjacent cycles for one 500 ms refresh. A lock inside the clock loop would cost
more than this cosmetic race.

Two physical limits apply:

- **The range is short.** The module sits on the underside of a 291 × 322 mm
  board, between the GND and VCC planes. The antenna strip has an all-layer
  keepout, so the radio works. The antenna still radiates at the edge of a
  large ground structure. Expect same-room range, not whole-house range.
- **Power.** WiFi adds about 50 mA average, with transmit bursts of 200 mA to
  300 mA. Added to the typical board current of about 0.35 A, a bench supply
  covers this. USB-only demo mode reaches about 0.9 A worst case. A legacy
  500 mA port cannot supply that.

## Using the tester

Connect a serial terminal to the Pico USB port at any baud rate, then:

```
R          # reset sequence
t 32       # run 32 cycles, watch the bus: cycle addr data r/W SYNC
s 5        # step 5 instructions
x 300 10   # hexdump $0300.. (the counter byte lives here)
p 100      # slow the clock to 5 kHz (half-period 100 us)
L          # load an Intel hex image pasted into the terminal
k on       # arm the functional-test watcher (see below)
g          # free-run with the watcher until a self-loop
```

After `R`, a healthy CPU shows the 7-cycle reset sequence and a vector fetch at
`3FFC/3FFD`. The fetch and execute rhythm follows, with SYNC on each opcode.
The default image increments A forever. The A-register LEDs count in binary and
`$0300` follows them.

## Running the 6502 functional test suite

[Klaus Dormann's `6502_65C02_functional_tests`](https://github.com/Klaus2m5/6502_65C02_functional_tests)
(GPLv3) is the standard acceptance test for a 6502 *re-implementation*. This
board is a re-implementation, not an emulator. The suite fits this hardware.
With the stock configuration (`zero_page = $0A`, `data_segment = $200`,
`code_segment = $400`, 13.1 kB of code) the image ends near `$3800`. That is
inside the 16 KB mirrored window, and it leaves the reset vector at `$3FFC`
clear. The `ram_top` option of the suite even offers `$40 = 16k` as a preset
for mirrored systems. **The loss of ab14 and ab15 does not block the suite.**

Assemble the suite with `as65 -l -m -s2 -w -h0`. The `-s2` option writes Intel
hex. Then run these commands:

```
p 50          # start at the conservative default clock
L             # then paste the .hex file into the terminal
m 3FFC 00 04  # start at $0400: the suite's own RES vector points at res_trap
k on          # watcher on (test_case defaults to $0200)
R             # reset
g             # go: run until a self-loop, print progress
```

The suite has no I/O. The watcher therefore reads two side channels from the
bus:

- **Progress.** Every write to `test_case` marks a passed sub-test. The tester
  prints `[functest] test $NN at cycle N (+delta)`. The value `$F0` means the
  opcode tests are complete and the final RAM-integrity check has started.
- **Verdict.** A pass and a failure are both branch-to-self loops. The watcher
  reports any address whose opcode fetch repeats 4 times, and it stops the run.
  Compare that address against your assembly listing. The `success` address
  means **PASS**. Any other address is the trap for the opcode above it.

Plan the time. A full pass takes 10⁷ to 10⁸ cycles. At 10 kHz to 20 kHz that is
an **overnight run**. The printed cycle counts give the exact figure on the
first run. Run the shorter `6502_decimal_test.a65` first. Decimal mode comes
free from the visual6502 netlist, and emulators get it wrong more often than
any other feature. For a run of that length the **`wifi/` firmware is the
better harness**. It uses the same watcher, but you upload the hex over HTTP
and read the progress in a browser instead of a tethered terminal.

`g` accepts an optional cycle cap, for example `g 500000`. Any keypress stops
it.

## Charge retention: measuring the clock's *lower* bound

This CPU uses dynamic NMOS logic. A bit is charge on the capacitance of a wire,
so the clock has a floor as well as a ceiling. If you stop the clock for too
long, the machine forgets its state mid-instruction.

**Nobody knows this number, and simulation cannot supply it.**
`tools/dynamic_nodes.py` finds the weakest node: the special-bus bits, 32 pF
against twelve leaking FET channels. Its retention spans three orders of
magnitude with part leakage. A typical 1 nA per FET gives 2.6 ms. The 500 nA
datasheet guardband gives 5.3 µs. `sim/retention.sp` records why ngspice cannot
resolve leakage at that level. Its answer moves 3.5 orders of magnitude with
the solver tolerances, and its leakage falls with temperature when it must
rise. You must therefore measure the number on real copper:

```
w 5        # freeze the clock for 5 ms. Did the CPU survive?
W          # bisect for the boundary (default up to 4000 ms)
W 20000    # if it survives 4 s, search further
```

`W` prints output like this:

```
control passed (0 ms survives). searching...
       1 ms -> survived
       2 ms -> survived
       ...
     512 ms -> lost
retention boundary: survives 256 ms, fails at 512 ms
```

The counter image stores an incrementing A to `$0300` on every pass. The test
records one stored value. It then freezes the clock and requires the next store
to be exactly one greater. A forgotten register breaks the sequence. A
forgotten PC stops the stores. `W` runs a **0 ms control first**. If the CPU
cannot survive a stall of zero, the harness is broken and every later number is
meaningless. `W` then stops and reports the fault.

Two limits apply:

- **Both commands reload the counter image**, because they need a known
  program. Upload your own hex again afterwards.
- The clock rests **low** between cycles, so the test measures retention during
  φ1. Retention in the other phase can differ. A test for it needs a half-step
  stall, which the firmware does not implement.

The result has a practical use. It is the hard limit on a single-step pause,
before the step corrupts the state you want to observe.

The **wifi firmware has the same test** in its own panel, with *one shot* and
*find the boundary* buttons. It logs each trial live and gives a stop button.
The measurement runs on core 1 with the bus engine, like everything else that
touches the clock. Core 0 only starts it and reports the result. A scan can
take minutes, so core 1 checks for a stop command between trials.
`common/retention.c` holds the shared implementation.

## Reading the LEDs

The 55 register LEDs sit at their die-true positions inside the transistor
field. There is no room for a silk label at each LED. A measurement found a
pad-free spot for only 3 of the 55, even at 1.0 mm text. Use `gen/led_map.svg`
as the reference. The layout is:

| Register | Column | Order |
|---|---|---|
| Y | x ≈ 60 mm | bit 0 top → bit 7 bottom |
| X | x ≈ 64 mm | bit 0 top → bit 7 bottom |
| S | x ≈ 75 mm | bit 0 top → bit 7 bottom |
| A | x ≈ 145 mm | bit 0 top → bit 7 bottom |
| PCH | x ≈ 164 mm | bit 0 top → bit 7 bottom |
| PCL | x ≈ 190 mm | bit 0 top → bit 7 bottom |

All six register columns span y ≈ 183 mm to 270 mm. The 7 **P status flags** are
not in a row. They sit where the die puts them, in the control-logic band:
`I(197,116) B(212,161) C(216,144) D(223,147) V(238,153) Z(242,161) N(264,144)`.
The two values are x and y in mm from the top-left of the front view.

The default tester image increments A forever. The A column at x ≈ 145 mm must
therefore count in binary. This is the fastest visual proof that the CPU is
alive.

## Clock speed: start slow

The firmware default is a **50 µs half-period**, which is 10 kHz. The project
first targeted 50 kHz. `sim/fanout_speed.sp` found the real ceiling. The
decode-PLA input lines drive up to 71 discrete gates, about 1.9 nF, behind one
10k pull-up. After the pull-down releases, the receiving stage needs about 7 µs
at 5 V to change state, and about 11 µs at 3.3 V. The line needs about 25 µs to
reach a comfortable level. A 50 kHz clock gives only a 10 µs half-cycle. That
is marginal at 5 V and too short at 3.3 V.

At bring-up, start at the default and confirm correct execution. Then increase
the clock with `p` (`p 25` is 20 kHz, `p 10` is 50 kHz) and find where it
fails. Expect decode errors first, because the PLA input lines are the slowest
nets on the board.

## Roadmap

- A PIO bus engine. It is cycle-accurate, faster than bit-banging, and it frees
  the CPU.
- A host-side loader script. The `L` command already accepts pasted Intel hex.
  A script would make overnight functional-test runs unattended.
- Lock-step co-verification against `tools/switchsim.py` traces. This compares
  the board against the golden model during bring-up.
- Address-bus and data-bus LED support, if the optional LEDs are added.
