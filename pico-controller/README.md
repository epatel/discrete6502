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

## Bring-up sequence: read before first power-up

Do the steps in this order. The order is deliberate: **the boards arrive with
no Pico on them** (U1 is DNP), thus the first two steps have no 3.3 V part
attached, and no logic-level question exists at any rail voltage. Use a bench
supply with the current limit set to about 0.5 A for every step. The current
limit, not a lower rail voltage, is what protects a mis-assembled board.

### Step 1: bare board, no power

Measure the resistance from a VCC bond pad to a VSS bond pad. It must read
high. The pull-up resistors reach floating nodes through FETs that are off,
thus no low-resistance path to VSS exists. A low reading is a solder bridge.
Find it before you apply power.

### Step 2: board alone at 5 V

Croc-clip the current-limited supply to the VCC and VSS bond pads. Set the limit
to 0.5 A, set 5 V, and **ramp the voltage up from zero** while you watch the
current. Do not switch 5 V on in one step; the reason is below.

**Compare the current against the 0.35 A prediction.** This one number is the
most informative test in the whole sequence. It finds a bridged rail, a reel
loaded backwards and missing pull-ups. Expect the current to jump to roughly
**1.8–2.1 A the moment you start clocking** — see "Driver contention" in
`project-plan.md`, and size the supply for 3 A.

| Reading at 5 V | Verdict |
|---|---|
| ≈0.35 A | The prediction. A healthy board. |
| Up to 0.65 A | The legitimate worst case: every pull-up low, every LED lit. Unusual, not a fault. |
| Limits at a fraction of a volt | A short. Stop and find it. |
| Limits only near 5 V | Ambiguous — see below. |
| Grossly high or grossly low | A systematic fault. Do not proceed, and do not rework three more boards. |

**Why you ramp: the limit is below the legitimate worst case.** 0.65 A on a
healthy board would trip a 0.5 A limit and look exactly like a fault. *Where* it
folds back is what separates them — a bridge limits almost immediately, a
healthy-but-high board limits near the top. If it limits near the top and you
need to tell the two apart, raise the limit to **0.8 A**. That is still far below
the ~1.8 A that contention draws, so the limit stays diagnostic and does not
merely become permissive.

**An honest limit on "an unclocked board cannot contend".** The reasoning is that
contention needs live logic state, which an unclocked board has none of. That is
likely but not guaranteed: the dynamic nodes are not in a defined state on an
unclocked board, they hold whatever power-up charge leaves them, and nothing
forbids a `dor` gate and its pull-down from both sitting above threshold. Read the
claim as *sustained* contention being unlikely, not as contention being
impossible. It changes nothing you do, because **the protection was never the
absence of contention — it is the current limit.** At 0.5 A the supply folds back
as soon as two nets contend at 262 mA each, the rail sags, and dissipation stays
well below what damages a SOT-323. These parts fail from sustained heating, which
a current-limited supply prevents.

Optionally, croc-clip a function generator to the Φ0 bond pad and drive clk0
push-pull at some kHz. The data bus floats, because no memory is connected,
thus the CPU executes garbage. The register LEDs must still move. Movement
proves that the clock phases regenerate on-board and that the dynamic logic
holds charge. Keep this brief and keep the current limit on: clocking is what
makes driver contention thermal, and the rework has not been done yet.

### Step 2b: the eight-site rework (rev A boards)

Unpowered. Add a 10k resistor in series with each of the eight data-out driver
pull-ups. Instructions, site by site, with true-scale renders:
`docs/rework-dor-series-r.html`. Background: "Driver contention" in
`project-plan.md`.

It belongs **here**, between Step 2 and Step 3, and the order is the point.
Steps 1 and 2 are the only tests that detect a *systematic* assembly fault, and
any such fault would make the rework wasted labour on four boards. Everything
from Step 4 onward involves sustained clocking, which is the condition that makes
the defect thermal. Thus the rework goes exactly between them.

Repeat the Step 1 resistance measurement when all eight are done.

### Step 3: mount the Pico

**Flash the `tester` firmware onto the bare module first**, on the bench, and
confirm that it enumerates over USB. Then solder the Pico 2 W module on the
underside site. **Solder pin 39.** See Powering for why pin 39 must be a
soldered joint and not a decision.

Pin 38 is `vss` and pin 39 is `vcc`, side by side on 2.54 mm pitch. A solder
bridge between them is a dead short across the board supply. Repeat the Step 1
resistance measurement after you solder the module. Apply power only after that
measurement.

#### Flash before soldering, even though it can be reflashed in place

The module can be reprogrammed in place indefinitely, and with no button press.
`pico_stdio_usb/reset_interface.c` is linked into all three firmwares, thus the
SDK 1200-baud-touch reset-to-bootloader works and `picotool` can reboot the
module into its bootloader over USB. Flash it once beforehand anyway, for three
reasons.

- **A bad module is cheap to reject before it is soldered.** The
  `RaspberryPi_Pico_W_SMD` pads are 3.2 x 1.6 mm and run *under* the module, thus
  desoldering one is a poor operation to perform beside 4,051 transistors.
- **The first flash is the one that needs BOOTSEL**, held while the board
  power-cycles. That is the awkward step, and it is the step you can do off the
  board.
- **The first power-up becomes a known state**, not merely a harmless one. A
  blank module is safe, because RP2350 GPIOs default to inputs, but safe and
  known are not the same property.

**The firmware is inert at boot, which is what makes this safe.** `main()` calls
`bus_init(false)` and then blocks on `while (!stdio_usb_connected())
sleep_ms(100)`. A pre-programmed board that is powered with no terminal attached
does nothing: no clocking and no reset ceremony. The CPU moves only when you
open a serial connection, thus entering Step 4 is a decision and not an event.

**One subtlety: `bus_init` leaves clk0 an output driven LOW**, and every other
pin an input. A powered pre-programmed board therefore sits with the clock
*parked*, which is the stall condition — the condition the retention test
creates deliberately, and the condition that driver contention makes dangerous.
This is safe in the sequence as written, because Step 2b puts the rework before
the Pico goes on. Do not reorder those two, and do not leave an un-reworked board
powered with a Pico fitted.

**Unverified, worth checking before you choose a workholding setup:** the module
mounts pads-down, thus its component side — USB connector and BOOTSEL button —
faces away from the PCB, which is downward when the board lies flat on its back.
Prop the board up or use standoffs to reach the connector. This is reasoned from
the footprint, not from a board in hand.

### Step 4: 5 V logic bring-up

Power the board at 5 V from the bench supply. The `tester` firmware is already on
the module from Step 3; reflash it in place if you have changed it, with no button
press needed. USB may stay connected for serial. Open the terminal — the firmware
waits for it before touching the CPU — then run the default A-register counter
image and watch the A LEDs count.

Watch the supply current here. With the rework done it stays in the low hundreds
of mA. A jump toward 1.8–2.1 A means a rework site did not take.

Then walk the clock up with `p` to find the real ceiling, and measure the
retention floor with `W`. Measure the floor **after** the rework, never before.

3.3 V is **not** a step in this sequence. It is a diagnostic fallback. See
"3.3 V operation" below.

## Logic levels

The Pico is a 3.3 V device. The CPU core runs at 5 V. This is the one
**unresolved hardware question** for bring-up. It does not affect the PCB.

- **Inputs to the Pico** (db on writes, ab, rw and sync at 5 V). The 1k series
  resistors limit the clamp current to about 1.4 mA per pin, and to about
  34 mA in total with all 24 input lines high. This is the common practical
  arrangement, but it is formally outside the RP2350 specification. It is
  acceptable for bring-up. Do not leave the CPU powered at 5 V while the Pico
  has no power. A soldered pin 39 makes that state impossible.
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

## Powering

Board VCC feeds the Pico VSYS pin (pin 39). The two grounds are common. VSYS
accepts 1.8 V to 5.5 V, thus 3.3 V and 5 V are both in specification. Pin 39 is
the only supply pin. The Pico 3V3OUT pin (pin 36) is not connected, thus the
Pico regulator cannot feed the board.

### Either end can supply the power

A soldered pin 39 makes board VCC and Pico VSYS one node. Power therefore flows
in whichever direction you supply it, and **the bond pads are not mandatory**.

- **Bench supply on the bond pads.** The board runs, and the same rail feeds
  VSYS. The Pico then needs no USB power. Connect USB for serial only.
- **USB into the Pico.** VBUS goes through the module Schottky diode to VSYS
  and on to board VCC. One cable runs the whole CPU, with no croc clips.

Only Step 2 of the bring-up sequence needs the bond pads, and only because no
Pico is fitted at that point.

Use the bench supply for test runs, and USB-only mode to demonstrate the board.
The next two sections give the reasons.

### Pin 39 must be soldered

Solder pin 39 when you solder the module. Board VCC and Pico VSYS then become
the same node, and two problems disappear together.

- **No power-up sequence to remember.** The hazard is a 5 V core that drives 26
  clamp diodes into a dead 3V3 rail. One supply for both parts makes that
  condition unreachable.
- **No intermittent joint.** The `RaspberryPi_Pico_W_SMD` footprint has 3.2 x
  1.6 mm pads that extend inward, under the module. An unsoldered pin 39 is two
  flat copper faces that rest against each other, held apart only by the
  standoff that the adjacent solder joints happen to give. That gap is
  uncontrolled, and board flex or a croc clip can close it. An unsoldered pin 39
  is an intermittent contact, not an open circuit. A rail that makes and breaks
  corrupts every dynamic node at once, and the result looks like a random CPU
  fault.

The two rails do not rise together. Board VCC rises immediately. The Pico 3V3
rail follows some milliseconds later, through the buck-boost soft start. The
GPIO clamps do conduct during this interval, but from the same supply and
through the 1k series resistors. This is the usual arrangement on a Pico
carrier board. Board bulk capacitance is only about 50 uF (96 x 100 nF plus
4 x 10 uF), thus there is no inrush that can hold the ramp down.

At 5 V you can keep USB connected for serial at the same time. The module
Schottky diode drops USB VBUS to about 4.7 V to 4.8 V at VSYS, thus a 5.0 V
bench supply wins the node, and the diode blocks all back-feed into the host.

### USB-only demo mode

With no bench supply, Pico USB power runs the whole board through VBUS, the
module Schottky diode and VSYS. Three limits apply.

- **The rail is not 5.0 V.** It is VBUS minus the diode drop: about 4.7 V to
  4.8 V at 0.35 A, and much lower once the CPU is clocked — driver contention
  takes the board to about 2.1 A (see "Driver contention" in `project-plan.md`),
  which through the Schottky and a USB cable is a collapse, not a droop. Cable
  resistance subtracts more still.
- **Current. SUPERSEDED 2026-08-01 — USB-only mode is NOT viable at 5 V.** The
  figures below omit driver contention: the eight data-bus output drivers draw
  262 mA each at 5 V for most of the time, adding about **1.76 A** and taking the
  board to **≈2.1 A**. Use a **3 A bench supply**. See "Driver contention" in
  `project-plan.md`. The original figures, still valid for the *un-clocked* board
  (Step 2, where contention is zero): 0.35 A typical, 0.65 A worst case with every
  pull-up low and every LED lit. The `wifi` firmware adds about 50 mA average, with 200 mA
  transmit bursts, thus about 0.9 A worst case. A USB-3 port or a charger
  supplies this. A legacy 500 mA port does not.
- **Use a bench supply for test runs.** This is dynamic logic. A rail sag does
  not degrade gracefully. It corrupts the dynamic nodes, and you read the
  result as a logic fault in the CPU. Use a bench supply with margin for the
  functional-test run, which is hours long. Keep USB-only mode for
  demonstrations.

All board current in this mode goes through one castellation and one via to
the In4 VCC plane. That is sufficient at these currents, but it is a single
feed.

### Optional modification: bridge VBUS to VSYS (demo boards only)

Pin 40 is VBUS. On our board it is `nc40`, a net with one pad and nothing else
on it, thus a solder bridge across the pin 39 and pin 40 castellations ties
VBUS to VSYS and touches no other net. It bypasses the module Schottky diode.
The modification is reversible.

It improves USB-only mode:

- The rail becomes VBUS, about 5.0 V minus the cable drop, instead of 4.7 V to
  4.8 V. This is the full 5 V margin.
- The supply is stiffer for the WiFi bursts, because the diode dynamic
  resistance leaves the path.
- The diode stops dissipating about 0.12 W at 0.35 A — and far more than that
  at the ~2.1 A the board actually draws when clocked, which is the real reason
  this bridge cannot rescue USB-only operation at 5 V.

**It also removes the reverse blocking, thus a bridged board must never have a
bench supply on its bond pads.** Board VCC becomes VBUS, thus a bench supply
drives current back through the cable into the USB host port. This is outside
the USB specification, and different hosts tolerate it differently. The
"connect USB for serial while the bench supply runs the board" arrangement is
no longer available on a bridged board. Two smaller effects: the USB connector
VBUS contact sits at board voltage when no cable is connected, and the Pico W
VBUS sense reads "USB present" whenever the board has power.

Use this per board, not as a general change. One board of the four can become a
USB-only demonstration unit: one cable, a true 5 V rail and the brightest LEDs.
**Mark that board physically.** Leave the other boards unmodified, so they keep
the bench-supply and serial workflow.

## 3.3 V operation: a fallback, not a first step

The whole CPU can run at VCC = 3.3 V. Simulation clears it: `sim/passpair_33v.sp`
(2026-07-25) shows that the dynamic latches still work at 3.3 V and at 3.0 V,
and that the clock-edge bootstrap keeps the stored '1' at or above the rail.

**Do not use it as the first power-up.** 3.3 V is the tighter operating point,
not the safer one, and it squeezes the usable clock window from both ends.

| | 5 V | 3.3 V |
|---|---|---|
| Clock ceiling (`sim/fanout_speed.sp`) | about 20 kHz | about 10 kHz |
| Retention floor: worst-node leakage budget | under 53 nA per FET | under 27 nA per FET |
| Usable clock window | about 50x | about 13x |
| Register LED current (`sim/led_tap.sp`) | 1.42 mA | 0.67 mA |

The dim LEDs are cosmetic, not a fault, but the LEDs are one of the few
observation channels at bring-up. The important cost is the ambiguity: a board
that misbehaves at 3.3 V does not tell you whether the cause is an assembly
fault or the reduced margin, and you must go to 5 V to find out. A first test
with an ambiguous failure mode is a bad first test.

3.3 V is useful **after** Step 2 has given a good current reading, as a
diagnostic lever: if the CPU behaves erratically at 5 V, a lower rail changes
the timing and the LED currents, and the difference is informative.

To run at 3.3 V, remove the competing supply, because a soldered pin 39 plus
USB pulls board VCC to about 4.8 V and a 3.3 V bench setting cannot win against
it. Two ways:

- **No USB.** Flash over USB first. The board sits at about 4.8 V during
  flashing with the clock idle, which does no harm. Then disconnect USB and
  apply 3.3 V. Use the `wifi` firmware to keep full control with no cable.
- **A data-only USB cable**, if you want serial at 3.3 V. **Unverified:** the
  RP2350 may need VBUS present to enumerate when it is self-powered. Test this
  on a spare Pico before you rely on it.

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
- **Power. Use a bench supply with this firmware.** WiFi adds about 50 mA
  average, with transmit bursts of 200 mA to 300 mA. The WL LED is also left on
  permanently. Added to the real board current of about **2.1 A** when clocked
  (driver contention — see `project-plan.md`), USB-only mode is **not viable at
  all** at 5 V. The old figure here, 0.9 A worst case, assumed the superseded
  0.35 A board current.

  The bursts matter more than the average. A 200 mA to 300 mA step lands on the
  same rail that holds 456 dynamic storage nodes, and the board has only about
  50 uF of bulk capacitance to absorb it. Short croc leads from a bench supply
  make this a non-event. A USB cable and the module Schottky diode make it a
  real dip, and a dip that corrupts the dynamic nodes reads back as a CPU logic
  fault, not as a power problem. This firmware exists for the unattended
  overnight functional-test run, which is the longest possible exposure to that
  failure mode.

  This firmware does not manage power in any way. There is no `cyw43_wifi_pm()`
  call, no `set_sys_clock*` call, and no sleep or dormant mode. `cyw43_arch_init()`
  takes the SDK default, and the core 1 bus loop never idles. The core split is
  a timing decision, not a power decision.

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

> **SAFETY — read before running `w` or `W`.** Stalling the clock is not a
> read-only experiment. Eric Schlaepfer documents the MOnSter 6502's low-clock
> failure as *"if the clock slows down too much, the latch will change state,
> causing both pullup and pulldown to be turned on"* — **shoot-through, not just
> lost data**. He added protective resistors between pullup and pulldown to
> survive it, which is also what caps his clock speed.
>
> Our 1,018 pull-ups are 10k **resistors**, so those nodes are current-limited to
> 0.5 mA and are safe. But **266 nets have a FET-to-FET path** (a VCC-side FET
> sourcing against pull-down FETs, no series resistance), and only 105 of those
> also carry a 10k pull-up. Each is a **single** pull-up FET against its pull-downs
> — a 1:1 ratio where the die had a weak load — so a contended net draws about
> **262 mA and 0.90 W** (measured, `sim/driver_contention.sp`), well past the
> 220 mA and ~0.3 W a SOT-323 is rated for.
>
> Therefore, before any stall test:
> 1. **Use a current-limited bench supply, set to about 0.5 A. Never USB.** A
>    charger will deliver 3 A into a partially-conducting clock driver; a bench
>    supply folds back. This is the real reason for the bench-supply rule, more
>    than the rail-sag argument.
> 2. **Run the first scans at VCC = 3.3 V**, where the shoot-through current is
>    lower.
> 3. **Start sub-millisecond and ramp**, rather than jumping to `W`'s 4000 ms
>    default.
> 4. **Watch the supply current, not just the pass/fail line.** A rising current
>    during the stall is the signal to stop; the firmware cannot sense it.
>
> Caveat both ways: this is a topology result read out of `gen/netlist.json`, not
> proof that the overlap actually occurs at a stalled clock. It may be harmless.
> But the boards are built, protective resistors are not an option, and the
> mitigations above cost nothing.

**Nobody knows this number, and simulation cannot supply it.**
`tools/dynamic_nodes.py` finds the weakest node: the special-bus bits, 32 pF
against twelve leaking FET channels. Its retention spans three orders of
magnitude with part leakage. A typical 1 nA per FET gives 2.6 ms. The 500 nA
datasheet guardband gives 5.3 µs. `sim/retention.sp` records why ngspice cannot
resolve leakage at that level. Its answer moves 3.5 orders of magnitude with
the solver tolerances, and its leakage falls with temperature when it must
rise. You must therefore measure the number on real copper:

**Both commands take MICROSECONDS** (changed 2026-07-31 from milliseconds — the
change is in the safe direction, since an old `w 5` now stalls 5 µs instead of
5 ms):

```
w 500        # freeze the clock for 500 us. Did the CPU survive?
W            # ramp from 64 us, doubling, then bisect (default ceiling 4 s)
W 20000000   # if it survives 4 s, search further
```

`W` **ramps from 64 µs** rather than opening at a millisecond, so it approaches
the boundary from below instead of starting deep in the hazardous condition.
The bisection stops once the bracket is within about 6% of the answer, which is
all the precision the measurement deserves and saves ~18 trials.

`W` prints output like this:

```
control passed (0 us survives). searching...
        64 us -> survived
       128 us -> survived
       ...
   512.000 ms -> lost
retention boundary: survives 256.000 ms, fails at 512.000 ms
```

The counter image stores an incrementing A to `$0300` on every pass. The test
records one stored value. It then freezes the clock and requires the next store
to be exactly one greater. A forgotten register breaks the sequence. A
forgotten PC stops the stores. `W` runs a **0 µs control first**. If the CPU
cannot survive a stall of zero, the harness is broken and every later number is
meaningless. `W` then stops and reports the fault.

Two limits apply, besides the safety rules above:

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
