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

#include "bus6502.h"
#include "selftest_image.h"

#define RUN_CYCLES 600u        // the whole test is ~200 cycles; 600 is slack
#define HALF_PERIOD_US 50u     // 10 kHz, the firmware default

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

int main(void) {
    // stdio FIRST: the 1200-baud reset path must be alive before anything else
    // can hang, or a soldered-down Pico stops being reprogrammable.
    stdio_init_all();

    bus_init(false);                       // push-pull; there is no pull-up on clk0
    bus_set_half_period_us(HALF_PERIOD_US);
    load_image();

    for (uint32_t pass = 1;; pass++) {
        bus_trace_clear();
        bus_reset_sequence();              // reset and run must be ONE operation:
        bus_run(RUN_CYCLES);               // dynamic state decays in about 1 ms
        uint16_t addr = settled_address(64);

        // Print the banner and the verdict together and repeatedly, so a USB
        // window of any length lands on a complete, self-describing line.
        printf("\ndiscrete6502 selftest firmware -- %d subtests, %d bytes, "
               "%lu us half-period\n", SELFTEST_NTESTS, SELFTEST_CODE_LEN,
               (unsigned long)HALF_PERIOD_US);
        report(addr, pass);
        printf("cycles %lu\n", (unsigned long)bus_cycle_count);

        // Keep clocking between passes rather than parking: parked is the
        // high-current state, and this is the whole reason for this firmware.
        for (int i = 0; i < 20; i++) bus_run(200);
    }
}
