#include "console.h"

#include <string.h>

// Powers of two so the wrap is a mask, not a modulo -- this runs inside the
// clock loop of a dynamic CPU, where every microsecond is a phase stretch.
#define OUT_SIZE 1024u
#define IN_SIZE 256u
#define OUT_MASK (OUT_SIZE - 1u)
#define IN_MASK (IN_SIZE - 1u)

// Single producer, single consumer, one index owned by each side:
//   out: the CPU produces (out_head), the host consumes (out_tail)
//   in:  the host produces (in_head),  the CPU consumes (in_tail)
// Each index is written by exactly one core and read by the other, and a
// 32-bit aligned load or store is atomic on ARM, so this needs no lock.
static volatile uint8_t out_buf[OUT_SIZE];
static volatile uint32_t out_head, out_tail, out_total;
static volatile uint8_t in_buf[IN_SIZE];
static volatile uint32_t in_head, in_tail;
static volatile bool enabled;

void console_enable(bool on) { enabled = on; }
bool console_enabled(void) { return enabled; }

void console_reset(void) {
    out_head = out_tail = out_total = 0;
    in_head = in_tail = 0;
}

bool console_io(uint16_t addr, bool is_write, uint8_t *data) {
    if (!enabled) return false;

    if (addr == CONSOLE_OUT_ADDR) {
        if (!is_write) return false;   // reads of the out port fall through
        uint32_t h = out_head, t = out_tail;
        if (h - t < OUT_SIZE) {        // drop rather than block or overwrite
            out_buf[h & OUT_MASK] = *data;
            out_head = h + 1;
        }
        out_total++;
        return true;
    }

    if (addr == CONSOLE_IN_ADDR) {
        uint32_t h = in_head, t = in_tail;
        if (is_write) {
            // Any write is an acknowledgement. Drop the character the CPU has
            // just finished with; the next one becomes visible immediately.
            if (h != t) in_tail = t + 1;
        } else {
            *data = (h != t) ? in_buf[t & IN_MASK] : 0u;
        }
        return true;
    }

    if (addr == CONSOLE_STATUS_ADDR) {
        if (is_write) return true;     // writes to status are simply swallowed
        uint8_t s = 0;
        if (in_head != in_tail) s |= CONSOLE_STATUS_IN_READY;
        if (out_head - out_tail < OUT_SIZE) s |= CONSOLE_STATUS_OUT_ROOM;
        *data = s;
        return true;
    }

    return false;
}

// ---- host side ------------------------------------------------------------

uint32_t console_take_output(char *buf, uint32_t cap) {
    if (!cap) return 0;
    uint32_t n = 0, t = out_tail;
    while (n + 1 < cap && t != out_head) {
        buf[n++] = (char)out_buf[t & OUT_MASK];
        t++;
    }
    out_tail = t;
    buf[n] = 0;
    return n;
}

uint32_t console_push_input(const char *s) {
    if (!s) return 0;
    uint32_t n = 0;
    for (; s[n]; n++) {
        uint32_t h = in_head;
        if (h - in_tail >= IN_SIZE) break;   // full
        in_buf[h & IN_MASK] = (uint8_t)s[n];
        in_head = h + 1;
    }
    return n;
}

uint32_t console_input_pending(void) { return in_head - in_tail; }
uint32_t console_output_pending(void) { return out_head - out_tail; }
uint32_t console_output_total(void) { return out_total; }
