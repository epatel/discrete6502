#include "retention.h"

#include "bus6502.h"
#include "pico/stdlib.h"
#include <string.h>

void retention_load_image(void) {
    uint8_t *m = bus_mem();
    static const uint8_t prog[] = {
        0xA2, 0xFF,        // 0200 LDX #$FF
        0x9A,              // 0202 TXS
        0xA9, 0x00,        // 0203 LDA #$00
        0x18,              // 0205 CLC
        0x69, 0x01,        // 0206 ADC #$01   <- loop
        0x8D, 0x00, 0x03,  // 0208 STA $0300
        0x4C, 0x06, 0x02,  // 020B JMP $0206
    };
    memcpy(m + 0x0200, prog, sizeof prog);
    m[0x3FFC] = 0x00;  // reset vector $FFFC -> $0200 (16 KB mirrored)
    m[0x3FFD] = 0x02;
}

// Run until the program stores to $0300; false if it never does.
static bool run_to_store(uint8_t *out) {
    for (uint32_t i = 0; i < RET_CYCLE_CAP; i++) {
        bus_trace_t t = bus_step_cycle();
        if (!t.rw_read && t.addr == RET_STORE_ADDR) {
            *out = t.data;
            return true;
        }
    }
    return false;
}

bool retention_trial(uint32_t ms) {
    bus_reset_sequence();
    uint8_t before, after;
    if (!run_to_store(&before)) return false;
    sleep_ms(ms);  // clock frozen low
    if (!run_to_store(&after)) return false;
    return after == (uint8_t)(before + 1);
}

retention_scan_t retention_scan(uint32_t limit, retention_report_fn report,
                                retention_abort_fn abort_fn,
                                uint32_t *good, uint32_t *bad) {
    *good = *bad = 0;
    retention_load_image();

    // Control first. Without this a broken harness -- a CPU that never runs,
    // a missing image, a dead clock -- would report "fails at 1 ms" and look
    // exactly like a real retention limit.
    if (!retention_trial(0)) return RET_SCAN_CONTROL_FAILED;

    for (uint32_t ms = 1; ms <= limit; ms *= 2) {
        bool ok = retention_trial(ms);
        if (report) report(ms, ok);
        if (!ok) { *bad = ms; break; }
        *good = ms;
        if (abort_fn && abort_fn()) return RET_SCAN_ABORTED;
    }
    if (!*bad) return RET_SCAN_ABOVE_LIMIT;

    while (*bad - *good > 1) {
        uint32_t mid = *good + (*bad - *good) / 2;
        bool ok = retention_trial(mid);
        if (report) report(mid, ok);
        if (ok) *good = mid; else *bad = mid;
        if (abort_fn && abort_fn()) return RET_SCAN_ABORTED;
    }
    return RET_SCAN_BOUNDED;
}
