// discrete6502 self-test firmware: runs the 23 datapath subtests by itself,
// forever, and prints the verdict every pass.
//
// WHY THIS EXISTS. The tester firmware stops clocking the moment a terminal
// attaches ("CPU free-ran N cycles ... stopped now"), and a parked clock is the
// board's high-current state. On a marginal bench supply the rail then collapses
// about a second after you attach -- measured twice on 2026-08-29, both times at
// the identical step, while the same board had free-run happily for eleven
// seconds with nobody looking. Every interactive route to a verdict therefore
// destroys the thing it is measuring.
//
// So this firmware never waits for anybody. It loads the image, resets, runs,
// reads the verdict off the trace ring and prints it, then does it again. The
// CPU keeps being clocked between passes, which is also the LOW-current state.
// Any fraction of a second of working USB catches a complete result line, and
// nothing about the measurement depends on a terminal being there.
//
// The verdict is the ADDRESS the CPU settles at: $0480 pass, $0400+3(N-1) names
// the failing subtest, $0600 int_trap. That encoding is from
// tools/quick_selftest.py and is shared with the wifi panel and the serial path.
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/gpio.h"

#include "bus6502.h"
#include "selftest_image.h"

// Shortest window that still runs the test to completion. The rail collapses
// inside the old 60 ms (600 cycles at 100 us): the firmware printed "running
// 23 subtests now" and the link died before the verdict. 300 cycles at 20 kHz
// is 15 ms -- four times less time to survive. 20 kHz is the measured design
// ceiling (sim/fanout_speed.sp), so a PASS here is conclusive; a FAIL could be
// a speed artifact and would need rechecking at 10 kHz.
#define RUN_CYCLES 300u
// Asymmetric clock, and it is the difference between running and tripping the
// supply. cclk follows clk0, so all 32 cclk-gated precharge FETs conduct only
// while the clock is HIGH; the average current scales with duty cycle. 40 us
// high satisfies the ~25 us settling bound (sim/fanout_speed.sp); 400 us low
// is well inside the measured 1.13 ms retention floor (board #1, 2026-08-24).
// 9% duty, ~2.3 kHz -- roughly a tenth of the contention current, with peaks
// short enough for a few hundred uF of bulk to supply.
#define PHASE_HIGH_US 40u
#define PHASE_LOW_US 400u

// clk0 low, actively driven, and left that way.
static void clk_park_low(void) {
    gpio_set_dir(PIN_CLK0, GPIO_OUT);
    gpio_put(PIN_CLK0, 0);
}

static void load_image(void) {
    uint8_t *m = bus_mem();
    memset(m, 0, BUS_MEM_SIZE);
    for (unsigned i = 0; i < SELFTEST_NRECS; i++) {
        const selftest_rec_t *r = &SELFTEST_RECS[i];
        memcpy(m + (r->addr & (BUS_MEM_SIZE - 1)), r->data, r->len);
    }
}

// The address the CPU is looping at = the most common address in the recent
// trace. A self-loop is two cycles, so it dominates any window that reaches it.
static uint16_t settled_address(uint32_t window) {
    uint32_t avail = bus_trace_avail();
    if (!avail) return 0xFFFF;
    if (window > avail) window = avail;
    uint16_t best = 0xFFFF;
    uint32_t best_n = 0;
    for (uint32_t i = avail - window; i < avail; i++) {
        uint16_t a = bus_trace_get(i).addr;
        uint32_t n = 0;
        for (uint32_t j = avail - window; j < avail; j++)
            if (bus_trace_get(j).addr == a) n++;
        if (n > best_n) { best_n = n; best = a; }
    }
    return best;
}

static void report(uint16_t addr, uint32_t pass) {
    if (addr == SELFTEST_PASS_ADDR) {
        printf("SELFTEST pass %lu: $%04X  *** ALL %d SUBTESTS PASSED ***\n",
               (unsigned long)pass, addr, SELFTEST_NTESTS);
        return;
    }
    if (addr == SELFTEST_INT_TRAP) {
        printf("SELFTEST pass %lu: $%04X  int_trap -- BRK or spurious interrupt\n",
               (unsigned long)pass, addr);
        return;
    }
    if (addr >= SELFTEST_FAIL_BASE &&
        addr < SELFTEST_FAIL_BASE + 3 * SELFTEST_NTESTS &&
        (addr - SELFTEST_FAIL_BASE) % 3 == 0) {
        unsigned n = (addr - SELFTEST_FAIL_BASE) / 3;
        printf("SELFTEST pass %lu: $%04X  FAILED subtest %u: %s\n",
               (unsigned long)pass, addr, n + 1, SELFTEST_NAMES[n]);
        return;
    }
    printf("SELFTEST pass %lu: $%04X  did not settle -- still running, or lost\n",
           (unsigned long)pass, addr);
}

#ifdef SELFTEST_BUS_ONLY
// Diagnostic build: bus_init and NOTHING else. It never clocks.
//
// This isolates one call. On 2026-08-30 the BOOT_TRACE wifi build died
// immediately after settings_load(), and bus_init() is the next thing it does
// -- but bus_init sets every data and address pin to an INPUT with pulls
// disabled and drives exactly one pin, clk0, LOW. The netlist says clk0 LOW
// holds cclk LOW and all 32 precharge FETs OFF, i.e. the 0.24 A state. So
// either that call is innocent and the killer is later (the radio, core 1, or
// clocking), or driving clk0 low does something the model does not predict --
// which would be worth knowing more than anything else on the board.
//
// The USB_ONLY build already proved the link holds for 45 s+ with nothing
// driven. Anything less here is caused by this one call.
int main(void) {
    stdio_init_all();
    for (int i = 0; i < 3000 && !stdio_usb_connected(); i++) sleep_ms(10);
    sleep_ms(300);
    // bus_init does two separable things: it releases 22 pins to inputs, and it
    // DRIVES clk0. Run them apart, with a pause and a flush between, so the
    // serial log names which one kills the board. Measured 2026-08-30: the
    // combined call dies inside bus_init, and the netlist says clk0 LOW should
    // be the QUIET state -- so one of those two beliefs is wrong.
    printf("\nA/B DIAGNOSTIC. Watch the ammeter against these lines.\n");
    printf("[A] bus_init(open_drain=true): 22 pins to inputs, clk0 LEFT AS AN "
           "INPUT (held by the external pull-down). Calling now...\n");
    sleep_ms(200);
    bus_init(true);
    for (int i = 0; i < 16; i++) {
        printf("[A] survived %d.%d s -- pins released, clk0 NOT driven\n", i / 2, (i % 2) * 5);
        sleep_ms(500);
    }
    printf("[B] >>> DRIVING clk0 LOW NOW <<<  watch the ammeter\n");
    sleep_ms(200);
    gpio_put(PIN_CLK0, 0);
    gpio_set_dir(PIN_CLK0, GPIO_OUT);
    for (uint32_t n = 1;; n++) {
        printf("[B] survived pass %lu -- clk0 driven LOW, both halves are innocent\n",
               (unsigned long)n);
        sleep_ms(500);
    }
}
#elif defined(SELFTEST_USB_ONLY)
// Diagnostic build: identical stdio setup, but the board is NEVER clocked.
// If this one holds a USB link while the normal build resets within 200 ms of
// the host opening the port, then clocking the board is what kills the Pico --
// and no amount of firmware tuning will change that.
int main(void) {
    stdio_init_all();
    for (uint32_t n = 1;; n++) {
        printf("SELFTEST pass %lu: $0000  USB-ONLY DIAGNOSTIC -- board not clocked\n",
               (unsigned long)n);
        sleep_ms(500);
    }
}
#else
int main(void) {
    // stdio FIRST: the 1200-baud reset path must be alive before anything else
    // can hang, or a soldered-down Pico stops being reprogrammable.
    stdio_init_all();

    // RUN FIRST, TALK AFTERWARDS.
    //
    // Measured on 2026-08-29: the board's load on VSYS (pin 39 ties it to board
    // VCC) browns the Pico out. Clocking, it lasts about a second; with clk0
    // left floating, about sixteen -- long enough for 29 clean printed lines.
    // So do not try to hold a link while clocking. Take the measurement in the
    // first 60 ms, release clk0, then spend the whole surviving window
    // repeating the verdict until the rail gives out.
    // ENUMERATE QUIET, THEN TEST. Clocking at boot browns the Pico out before
    // USB is up, so it reboots, re-runs the 60 ms test, and reboots again --
    // seen directly on 2026-08-29 as S1 blinking at about 2 Hz with no serial
    // device ever appearing, while the never-clocks build enumerated in under a
    // second. So do nothing at all until the host is attached: that is the
    // configuration measured to survive 16 s. Only then spend 60 ms clocking.
    // If the rail dies during the test we are no worse off; if it holds, the
    // verdict lands on a link that is already open.
    for (int i = 0; i < 3000 && !stdio_usb_connected(); i++) sleep_ms(10);
    sleep_ms(300);                         // let the host finish opening the port
    printf("\ndiscrete6502 selftest -- link up, running %d subtests now\n",
           SELFTEST_NTESTS);

    bus_init(false);                       // push-pull; there is no pull-up on clk0
    bus_set_phase_us(PHASE_HIGH_US, PHASE_LOW_US);
    load_image();

    bus_trace_clear();
    bus_reset_sequence();                  // reset and run must be ONE operation:
    bus_run(RUN_CYCLES);                   // dynamic state decays in about 1 ms
    uint16_t addr = settled_address(64);
    uint32_t cycles = bus_cycle_count;

    // Park the clock LOW -- do NOT float it. Traced through the netlist on
    // 2026-08-29: clk0 low holds cclk low and all 32 precharge FETs off (the
    // 0.30 A state); clk0 high or drifting high turns them all on at once (2+ A).
    // An earlier version floated this pin "to reduce the load" and had it
    // exactly backwards -- there is no pull-up or pull-down on clk0.
    clk_park_low();

    for (uint32_t pass = 1;; pass++) {
        printf("\ndiscrete6502 selftest -- %d subtests, %d bytes, "
               "%lu us high / %lu us low (%lu%% duty)\n",
               SELFTEST_NTESTS, SELFTEST_CODE_LEN,
               (unsigned long)PHASE_HIGH_US, (unsigned long)PHASE_LOW_US,
               (unsigned long)(100UL * PHASE_HIGH_US / (PHASE_HIGH_US + PHASE_LOW_US)));
        report(addr, pass);
        printf("cycles %lu (test ran at boot; clk0 now floating)\n",
               (unsigned long)cycles);
        sleep_ms(500);
    }
}
#endif
