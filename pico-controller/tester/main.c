// discrete6502 tester — interactive bring-up harness.
//
// The Pico is clock master and memory emulator; this firmware adds a USB
// serial CLI for controlled bring-up: reset, run N cycles, single-step
// instructions, dump the bus trace, peek/poke memory, change clock speed.
//
// Default image: a counter loop — A increments forever and is stored to
// $0300 each pass, so the A-register LEDs on the board count in binary
// and the trace shows a regular read/write rhythm. Sanity at a glance.
//
// For the real acceptance test, 'L' loads an Intel hex image over this same
// serial link (Klaus Dormann's functional test suite assembles straight to
// Intel hex) and 'k' + 'g' run it with live progress — see functest.h.
#include "bus6502.h"
#include "functest.h"
#include "ihex.h"

#include "pico/stdlib.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// hand-assembled default program (offsets within the 16 KB image)
static void load_default_image(void) {
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

// Blocking line reader. Returns the length; the buffer is NUL-terminated.
static int read_line(char *buf, int cap) {
    int n = 0;
    for (;;) {
        int ch = getchar();
        if (ch == '\r' || ch == '\n') break;
        if (ch == 8 || ch == 127) { if (n) n--; continue; }
        if (n < cap - 1 && ch >= 0) buf[n++] = (char)ch;
    }
    buf[n] = 0;
    return n;
}

// Load an Intel hex image pasted into the terminal. Parsing lives in
// common/ihex.c (shared with the wifi firmware); this just feeds it lines
// until the EOF record or a blank line.
static void load_intel_hex(char *line, int cap) {
    ihex_stats_t hx;
    ihex_begin(&hx);
    printf("paste Intel hex; ends at the EOF record or a blank line\n");
    for (;;) {
        if (read_line(line, cap) == 0) { printf("(blank line)\n"); break; }
        if (!ihex_line(&hx, line, bus_mem(), BUS_MEM_SIZE - 1)) {
            printf("(EOF record)\n");
            break;
        }
    }
    uint16_t vec = (uint16_t)(bus_mem()[0x3FFC] | (bus_mem()[0x3FFD] << 8));
    printf("loaded %lu bytes in %lu records (%lu bad)\n", (unsigned long)hx.bytes,
           (unsigned long)hx.records, (unsigned long)hx.bad);
    printf("reset vector at $3FFC -> $%04X\n", vec);
    if (vec != 0x0400)
        printf("note: the functional test wants to start at $0400 (its own RES vector\n"
               "      points at res_trap). Set it with:  m 3FFC 00 04\n");
}

static void print_functest_status(void) {
    const functest_state_t *f = functest_state();
    printf("functest %s, test_case at $%04X", f->enabled ? "ON" : "off", f->case_addr);
    if (f->have_case)
        printf(", last test $%02X at cycle %lu", f->test_case, (unsigned long)f->case_cycle);
    if (f->trapped)
        printf(", TRAPPED at $%04X (cycle %lu)", f->trap_addr, (unsigned long)f->trap_cycle);
    printf("\n");
}

static void print_trace_entry(bus_trace_t t) {
    printf("%8lu  %04X  %02X  %c%s\n", (unsigned long)t.cycle, t.addr, t.data,
           t.rw_read ? 'r' : 'W', t.sync ? "  SYNC" : "");
}

static void help(void) {
    printf("discrete6502 tester\n"
           "  R          reset sequence (assert, 8 cycles, release)\n"
           "  c N        run N cycles (quiet)\n"
           "  t N        run N cycles, print each bus cycle\n"
           "  s [N]      step N instructions (default 1), print cycles\n"
           "  d [N]      dump last N trace entries (default 32)\n"
           "  x A L      hexdump L bytes of image at offset A (hex)\n"
           "  m A B..    poke bytes at offset A (all hex)\n"
           "  p US       set clock half-period in us (default 50 = 10 kHz)\n"
           "  z          zero cycle counter + trace\n"
           "  L          load an Intel hex image pasted into this terminal\n"
           "  k [on|off|ADDR]  functional-test watcher (test_case addr, hex)\n"
           "  g [N]      go: run N cycles (0/omitted = until a self-loop),\n"
           "             printing watcher progress; any key interrupts\n"
           "  h          this help\n"
           "columns: cycle  addr(14-bit)  data  r/W  SYNC\n");
}

int main(void) {
    stdio_init_all();
    // Push-pull 3.3 V clock by default -- the board has NO pull-up on
    // clk0, so open-drain only works with an external 10k from the PHI0
    // bond pad to VCC (croc clips). See README "Logic levels".
    bus_init(false);
    bus_set_watch(functest_watch);  // dormant until 'k on'
    load_default_image();

    while (!stdio_usb_connected()) sleep_ms(100);
    printf("\ndiscrete6502 tester ready. h for help.\n");

    char line[128];
    for (;;) {
        printf("> ");
        read_line(line, (int)sizeof line);
        printf("%s\n", line);

        char *tok = strtok(line, " ");
        if (!tok) continue;
        switch (tok[0]) {
        case 'h': help(); break;
        case 'R':
            bus_reset_sequence();
            printf("reset released at cycle %lu\n", (unsigned long)bus_cycle_count);
            break;
        case 'c': {
            char *a = strtok(NULL, " ");
            uint32_t k = a ? strtoul(a, NULL, 0) : 1;
            bus_trace_t t = bus_run(k);
            print_trace_entry(t);
            break;
        }
        case 't': {
            char *a = strtok(NULL, " ");
            uint32_t k = a ? strtoul(a, NULL, 0) : 16;
            for (uint32_t i = 0; i < k; i++) print_trace_entry(bus_step_cycle());
            break;
        }
        case 's': {
            char *a = strtok(NULL, " ");
            uint32_t k = a ? strtoul(a, NULL, 0) : 1;
            while (k--) {
                uint32_t before = bus_trace_avail();
                bus_step_instruction(64);
                uint32_t after = bus_trace_avail();
                uint32_t fresh = after - before;
                for (uint32_t i = after - fresh; i < after; i++)
                    print_trace_entry(bus_trace_get(i));
            }
            break;
        }
        case 'd': {
            char *a = strtok(NULL, " ");
            uint32_t k = a ? strtoul(a, NULL, 0) : 32;
            uint32_t avail = bus_trace_avail();
            if (k > avail) k = avail;
            for (uint32_t i = avail - k; i < avail; i++)
                print_trace_entry(bus_trace_get(i));
            break;
        }
        case 'x': {
            char *a = strtok(NULL, " "), *l = strtok(NULL, " ");
            if (!a || !l) { printf("x ADDR LEN\n"); break; }
            uint32_t addr = strtoul(a, NULL, 16) & (BUS_MEM_SIZE - 1);
            uint32_t len = strtoul(l, NULL, 16);
            for (uint32_t i = 0; i < len; i++) {
                if (i % 16 == 0) printf("%s%04lX:", i ? "\n" : "", (unsigned long)(addr + i));
                printf(" %02X", bus_mem()[(addr + i) & (BUS_MEM_SIZE - 1)]);
            }
            printf("\n");
            break;
        }
        case 'm': {
            char *a = strtok(NULL, " ");
            if (!a) { printf("m ADDR BYTE..\n"); break; }
            uint32_t addr = strtoul(a, NULL, 16) & (BUS_MEM_SIZE - 1);
            char *b;
            while ((b = strtok(NULL, " ")))
                bus_mem()[addr++ & (BUS_MEM_SIZE - 1)] = (uint8_t)strtoul(b, NULL, 16);
            break;
        }
        case 'p': {
            char *a = strtok(NULL, " ");
            if (a) bus_set_half_period_us(strtoul(a, NULL, 0));
            break;
        }
        case 'z':
            bus_cycle_count = 0;
            bus_trace_clear();
            functest_clear();
            break;
        case 'L':
            load_intel_hex(line, (int)sizeof line);
            break;
        case 'k': {
            char *a = strtok(NULL, " ");
            if (!a) { print_functest_status(); break; }
            if (!strcmp(a, "off")) functest_disable();
            else if (!strcmp(a, "on")) functest_enable(functest_state()->case_addr);
            else functest_enable((uint16_t)strtoul(a, NULL, 16));
            print_functest_status();
            break;
        }
        case 'g': {
            char *a = strtok(NULL, " ");
            uint32_t limit = a ? strtoul(a, NULL, 0) : 0;  // 0 = until self-loop
            uint32_t start = bus_cycle_count;
            const uint32_t chunk = 100000;
            functest_clear();
            printf("running (any key to interrupt)...\n");
            for (;;) {
                uint32_t done = bus_cycle_count - start;
                if (limit && done >= limit) { printf("cycle limit reached\n"); break; }
                uint32_t n = (limit && limit - done < chunk) ? limit - done : chunk;
                bus_run(n);
                if (bus_aborted()) break;  // watcher printed why
                if (getchar_timeout_us(0) >= 0) { printf("interrupted\n"); break; }
                printf("... %lu cycles\n", (unsigned long)(bus_cycle_count - start));
            }
            printf("stopped after %lu cycles; ", (unsigned long)(bus_cycle_count - start));
            print_functest_status();
            break;
        }
        default:
            printf("? (h for help)\n");
        }
    }
}
