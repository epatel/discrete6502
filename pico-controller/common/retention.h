// Charge-retention measurement: the clock's LOWER bound, measured on copper.
//
// This CPU is dynamic NMOS -- a bit is charge on a wire's own capacitance --
// so stopping the clock for too long makes it forget itself mid-instruction.
// The number is NOT available from simulation: tools/dynamic_nodes.py puts the
// worst node's retention anywhere between 2.6 ms (typical 1 nA per FET) and
// 5.3 us (the 500 nA datasheet guardband), and sim/retention.sp documents why
// ngspice cannot narrow it -- its answer moves 3.5 orders with solver
// tolerances and its temperature control comes out backwards.
//
// Method: the counter image stores an incrementing A to $0300 every pass. Note
// one stored value, freeze the clock, then require the very next store to be
// exactly one greater. A forgotten register breaks the sequence; a forgotten
// PC stops the stores altogether.
//
// The clock rests LOW between cycles, so this measures retention during phi1.
// Retention in the other phase could differ and is not tested.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define RET_STORE_ADDR 0x0300u
#define RET_CYCLE_CAP 4000u

// Load the counter program (also the tester's and wifi firmware's default
// image). Both retention entry points need it, so they reload it themselves.
void retention_load_image(void);

// One trial: reset, get running, freeze for ms, check execution continued.
bool retention_trial(uint32_t ms);

// Called after each trial so a caller can print or publish progress.
typedef void (*retention_report_fn)(uint32_t ms, bool survived);
// Return true to abandon the scan between trials (a stop button, a keypress).
typedef bool (*retention_abort_fn)(void);

typedef enum {
    RET_SCAN_CONTROL_FAILED,  // 0 ms did not survive: the rig is broken, not the CPU
    RET_SCAN_BOUNDED,         // found: survives *good, fails at *bad
    RET_SCAN_ABOVE_LIMIT,     // still alive at the limit; search higher
    RET_SCAN_ABORTED,
} retention_scan_t;

// Double until failure, then bisect. Runs a 0 ms control FIRST -- if the CPU
// cannot survive no stall at all, every later number would be meaningless, so
// the scan refuses to report one.
retention_scan_t retention_scan(uint32_t limit, retention_report_fn report,
                                retention_abort_fn abort_fn,
                                uint32_t *good, uint32_t *bad);
