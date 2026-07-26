// Live watcher for Klaus Dormann's 6502 functional test suite.
//
//   https://github.com/Klaus2m5/6502_65C02_functional_tests  (GPLv3)
//
// The suite is the standard acceptance test for 6502 *re-implementations*,
// which is exactly what this board is. It fits our hardware: with the stock
// configuration (zero_page = $0A, data_segment = $200, code_segment = $400,
// 13.1 kB of code) the whole image ends around $3800 — inside our 16 KB
// mirrored window, with the reset vector at $3FFC still clear. Its own
// ram_top comment even offers "$40 = 16k" as a preset for mirrored systems.
//
// The suite has no I/O: it reports by writing a test number to `test_case`
// and by falling into a branch-to-self trap on failure. Both are visible on
// the bus, so the Pico can narrate a run that would otherwise be blind:
//
//   * progress — every write to `test_case` (the first byte of data_segment,
//     $0200 by default) is a "sub-test N passed" marker. $F0 means all opcode
//     tests are done and the final RAM integrity check has started.
//   * traps    — a failure is `jmp *` / `beq *`, i.e. consecutive opcode
//     fetches at the same address. Detecting a repeated SYNC address needs no
//     symbol table; the address maps to the failing opcode via the assembly
//     listing. Success is also a self-loop, at the address of the `success`
//     macro — so a trap report is a PASS if that address matches, and a FAIL
//     otherwise. Check the listing.
//
// Register with bus_set_watch(functest_watch); it prints to stdout and stops
// the run (returns false) on the first trap.
#pragma once
#include "bus6502.h"

// First byte of data_segment with the suite's stock configuration.
#define FUNCTEST_CASE_ADDR_DEFAULT 0x0200u
// Consecutive opcode fetches at one address before we call it a self-loop.
#define FUNCTEST_LOOP_HITS 4u

typedef struct {
    bool enabled;
    uint16_t case_addr;   // where the suite writes its test number
    bool have_case;       // seen at least one write there
    uint8_t test_case;    // last value written
    uint32_t case_cycle;  // cycle of that write
    uint16_t loop_addr;   // address currently repeating at SYNC
    uint32_t loop_hits;   // how many times in a row
    bool trapped;
    uint16_t trap_addr;
    uint32_t trap_cycle;
} functest_state_t;

void functest_enable(uint16_t case_addr);
void functest_disable(void);
// Suppress the printf narration. REQUIRED when the watcher runs on a
// timing-critical core: pico stdio_usb blocks for up to 500 ms if a terminal
// is attached but not draining, which would stretch a clock phase by ten
// thousand times its length. The wifi firmware sets this and reports through
// the shared snapshot instead.
void functest_set_quiet(bool quiet);
void functest_clear(void);  // forget progress and any trap, keep config
const functest_state_t *functest_state(void);

// bus_watch_fn: returns false once a trap is detected.
bool functest_watch(const bus_trace_t *t);
