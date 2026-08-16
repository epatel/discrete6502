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
//
// UNITS ARE MICROSECONDS throughout. The scan ramps from RET_SCAN_START_US so
// that the first trials are far below a millisecond. That is deliberate: the
// MOnSter 6502's designer documents the low-clock failure as pullup and
// pulldown turning on together, and 266 of our nets have a FET-to-FET path
// with no series resistance. Every one of those nets has exactly ONE pull-up
// FET against its pull-downs, so no net is a near-short -- each contended net
// is the same ~262 mA pair. (An earlier version of this comment said cclk was
// "33 VCC-side FETs against 31 pulldowns"; that counted FETs *gated by* cclk
// rather than FETs *on* it. Corrected 2026-08-01, and it is 1 against 1.)
// A scan that opened at milliseconds would spend its first trials deep in that
// condition. See the safety block in ../README.md -- and use a current-limited
// supply, because the firmware cannot sense current.
//
// Run this AFTER the eight-site rework, never before: the stall is exactly the
// condition the rework makes safe, dropping those sites from 262 mA to 0.5 mA.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define RET_STORE_ADDR 0x0300u
#define RET_CYCLE_CAP 4000u

// Scan ramp: first trial, default ceiling, and the relative precision that
// ends the bisection (bisecting to 1 us would cost ~18 extra trials for no
// useful accuracy).
#define RET_SCAN_START_US 64u
#define RET_SCAN_DEFAULT_LIMIT_US 4000000u
#define RET_SCAN_PRECISION_SHIFT 4  // stop when the bracket is within good/16

// Load the counter program (also the tester's and wifi firmware's default
// image). Both retention entry points need it, so they reload it themselves.
void retention_load_image(void);

// One trial: reset, get running, freeze for us, check execution continued.
bool retention_trial(uint32_t us);

// Called after each trial so a caller can print or publish progress.
typedef void (*retention_report_fn)(uint32_t us, bool survived);
// Return true to abandon the scan between trials (a stop button, a keypress).
typedef bool (*retention_abort_fn)(void);

typedef enum {
    RET_SCAN_CONTROL_FAILED,  // 0 us did not survive: the rig is broken, not the CPU
    RET_SCAN_BOUNDED,         // found: survives *good, fails at *bad
    RET_SCAN_ABOVE_LIMIT,     // still alive at the limit; search higher
    RET_SCAN_ABORTED,
} retention_scan_t;

// Ramp from RET_SCAN_START_US, doubling until failure, then bisect. Runs a
// 0 us control FIRST -- if the CPU cannot survive no stall at all, every later
// number would be meaningless, so the scan refuses to report one. limit_us of
// 0 means RET_SCAN_DEFAULT_LIMIT_US.
retention_scan_t retention_scan(uint32_t limit_us, retention_report_fn report,
                                retention_abort_fn abort_fn,
                                uint32_t *good, uint32_t *bad);
