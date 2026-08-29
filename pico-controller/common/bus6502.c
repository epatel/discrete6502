#include "bus6502.h"

#include "hardware/gpio.h"
#include "pico/stdlib.h"
#include <string.h>

static uint8_t mem[BUS_MEM_SIZE];
static bus_trace_t trace[BUS_TRACE_LEN];
static uint32_t trace_head;   // next write slot
static uint32_t trace_count;  // total entries ever written (min with LEN for avail)
// 50us half-period = 10 kHz.  Deliberately conservative: sim/fanout_speed.sp
// shows the worst decode-PLA input line (ir2, 71 gate loads = 1.9nF behind a
// 10k pull-up) needs ~7us at 5V / ~11us at 3.3V just to flip the receiving
// stage, and ~25us to reach a comfortable level.  Speed up with 'p' once the
// CPU is known good.
static uint32_t high_us = 50;   // phi2, clock HIGH -- see bus_set_phase_us
static uint32_t low_us = 50;    // phi1, clock LOW
static bool clk_od;
static bus_io_fn io_fn;
static bus_watch_fn watch_fn;
static bool aborted;
uint32_t bus_cycle_count;

// ---- pin helpers -----------------------------------------------------------

static inline void clk_low(void) {
    if (clk_od) {
        gpio_set_dir(PIN_CLK0, GPIO_OUT);  // sink; output register preset to 0
    } else {
        gpio_put(PIN_CLK0, 0);
    }
}

static inline void clk_high(void) {
    if (clk_od) {
        gpio_set_dir(PIN_CLK0, GPIO_IN);  // float; board pull-up to VCC
    } else {
        gpio_put(PIN_CLK0, 1);
    }
}

static inline void db_drive(uint8_t v) {
    gpio_put_masked(DB_MASK, (uint32_t)v << PIN_DB0);
    gpio_set_dir_out_masked(DB_MASK);
}

static inline void db_release(void) { gpio_set_dir_in_masked(DB_MASK); }

static inline uint8_t db_read(void) {
    return (uint8_t)((gpio_get_all() >> PIN_DB0) & 0xFF);
}

static inline uint16_t ab_read(void) {
    return (uint16_t)((gpio_get_all() >> PIN_AB0) & 0x3FFF);
}

// ---- api -------------------------------------------------------------------

void bus_init(bool clk_open_drain) {
    clk_od = clk_open_drain;
    for (int p = PIN_DB0; p < PIN_DB0 + 8; p++) {
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);
    }
    for (int p = PIN_AB0; p < PIN_AB0 + 14; p++) {
        gpio_init(p);
        gpio_set_dir(p, GPIO_IN);
        gpio_disable_pulls(p);
    }
    gpio_init(PIN_RW);
    gpio_set_dir(PIN_RW, GPIO_IN);
    gpio_init(PIN_SYNC);
    gpio_set_dir(PIN_SYNC, GPIO_IN);

    gpio_init(PIN_CLK0);
    gpio_put(PIN_CLK0, 0);
    if (clk_od) {
        gpio_set_dir(PIN_CLK0, GPIO_IN);  // idle: floating high via pull-up
    } else {
        gpio_set_dir(PIN_CLK0, GPIO_OUT);
    }

    gpio_init(PIN_RES);  // open-drain reset: idle floating (board pull-up)
    gpio_put(PIN_RES, 0);
    gpio_set_dir(PIN_RES, GPIO_IN);

    memset(mem, 0, sizeof mem);
    bus_trace_clear();
    bus_cycle_count = 0;
}

void bus_set_half_period_us(uint32_t us) { high_us = low_us = us ? us : 1; }

void bus_set_phase_us(uint32_t h, uint32_t l) {
    high_us = h ? h : 1;
    low_us = l ? l : 1;
}
uint32_t bus_get_high_us(void) { return high_us; }
uint32_t bus_get_low_us(void) { return low_us; }
void bus_set_io(bus_io_fn fn) { io_fn = fn; }
void bus_set_watch(bus_watch_fn fn) { watch_fn = fn; }
bool bus_aborted(void) { return aborted; }
uint8_t *bus_mem(void) { return mem; }

void bus_reset_assert(void) { gpio_set_dir(PIN_RES, GPIO_OUT); }
void bus_reset_release(void) { gpio_set_dir(PIN_RES, GPIO_IN); }

void bus_reset_sequence(void) {
    bus_reset_assert();
    for (int i = 0; i < 8; i++) bus_step_cycle();
    bus_reset_release();
}

bus_trace_t bus_step_cycle(void) {
    bus_trace_t t;

    // phi1: clock low -- the CPU puts out the new address and r/w
    clk_low();
    sleep_us(low_us);
    t.addr = ab_read();
    t.rw_read = gpio_get(PIN_RW) ? 1 : 0;
    t.sync = gpio_get(PIN_SYNC) ? 1 : 0;

    // phi2: clock high -- data transfers
    clk_high();
    if (t.rw_read) {
        uint8_t v = 0xEA;  // NOP for unmapped reads
        if (!(io_fn && io_fn(t.addr, false, &v))) v = mem[t.addr & (BUS_MEM_SIZE - 1)];
        db_drive(v);
        t.data = v;
        sleep_us(high_us);
        clk_low();          // CPU latches on the falling edge...
        sleep_us(1);        // ...small hold, then get off the bus
        db_release();
    } else {
        db_release();
        sleep_us(high_us);  // CPU drives data through phi2
        t.data = db_read(); // sample just before the edge
        clk_low();
        uint8_t v = t.data;
        if (!(io_fn && io_fn(t.addr, true, &v))) mem[t.addr & (BUS_MEM_SIZE - 1)] = t.data;
    }

    t.cycle = bus_cycle_count++;
    trace[trace_head] = t;
    trace_head = (trace_head + 1) % BUS_TRACE_LEN;
    if (trace_count < BUS_TRACE_LEN) trace_count++;
    if (watch_fn && !watch_fn(&t)) aborted = true;
    return t;
}

bus_trace_t bus_run(uint32_t n) {
    bus_trace_t t = {0};
    aborted = false;
    while (n-- && !aborted) t = bus_step_cycle();
    return t;
}

bus_trace_t bus_step_instruction(uint32_t max_cycles) {
    bus_trace_t t = {0};
    aborted = false;
    // leave the current sync cycle first, then run to the next one
    do {
        t = bus_step_cycle();
    } while (t.sync && max_cycles-- && !aborted);
    while (!t.sync && max_cycles-- && !aborted) t = bus_step_cycle();
    return t;
}

uint32_t bus_trace_avail(void) { return trace_count; }

bus_trace_t bus_trace_get(uint32_t idx) {
    uint32_t start = (trace_head + BUS_TRACE_LEN - trace_count) % BUS_TRACE_LEN;
    return trace[(start + idx) % BUS_TRACE_LEN];
}

void bus_trace_clear(void) {
    trace_head = 0;
    trace_count = 0;
}
