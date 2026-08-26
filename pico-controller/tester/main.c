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
#include "retention.h"
#include "console.h"
#include "settings.h"

#include "pico/stdlib.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Whatever this firmware is waiting for, it must never be a terminal. A board on
// a shelf with nobody attached still has a CPU on it, and a firmware that waits
// forever for a terminal that may never come is wrong on its own terms.
//
// NOTE, corrected 2026-08-26: this used to justify itself on current, claiming a
// parked clock was the board's PEAK draw at 1.4 A. Backwards. That figure came
// from a board with NO Pico, where clk0 (no pull-up), the data bus and reset all
// float and the dynamic nodes drift. Fitted and parked, board #1 draws 0.30 A;
// executing, 1.70 A. Parking is the cheapest state. The argument for not
// blocking stands without it.
static bool s_ran;
static bool s_stored;   // a boot image came out of flash, not the built-in counter

// Printed when a terminal appears, and again every time one reappears. You
// cannot attach before the board boots, so a banner emitted once into the void
// tells nobody anything -- the same reason the wifi firmware reprints its own.
static void greet(void) {
    printf("\ndiscrete6502 tester ready. h for help.\n");
    if (s_stored && settings_program_seconds()) {
        char d[24];
        settings_fmt_duration(d, sizeof d, settings_program_seconds());
        printf("boot image: %s -- about %s at this clock\n",
               settings()->program_name[0] ? settings()->program_name : "stored", d);
    }
    printf("settings: %s, clock %lu us half-period, autorun %s, image %s\n",
           settings_were_stored() ? "from flash" : "defaults (nothing stored)",
           (unsigned long)settings()->half_period_us,
           settings()->autorun ? "on" : "off",
           s_stored ? "stored in flash" : "built-in counter");
    if (s_ran)
        printf("CPU free-ran %lu cycles while waiting; stopped now. 'g' to resume.\n",
               (unsigned long)bus_cycle_count);
}

static void idle_work(void) {
    if (!stdio_usb_connected() && settings()->autorun) {
        bus_run(500);   // small chunks so a terminal appearing is noticed fast
        s_ran = true;
    } else {
        sleep_us(200);  // at a prompt, or autorun off: just poll cheaply
    }
}

// Line reader. Returns the length, or -1 if the terminal went away mid-line --
// which the caller must treat as "no command", not as an empty one. It polls
// rather than blocking, so a board with nobody attached keeps working.
//
// We echo each character ourselves: this is a raw USB CDC link, not a tty, so
// there is no line discipline doing it for us and a terminal like `screen`
// shows nothing while you type. Every character is flushed as it arrives --
// buffering until the newline is exactly the behaviour we are fixing.
//
// echo=false is for pasted Intel hex ('L'), where echoing 37.6 kB back down the
// same link would double the traffic for no benefit.
static int read_line(char *buf, int cap, bool echo) {
    int n = 0;
    for (;;) {
        int ch = getchar_timeout_us(0);
        if (ch < 0) {
            if (!stdio_usb_connected()) return -1;
            idle_work();
            continue;
        }
        if (ch == '\r' || ch == '\n') {
            if (echo) { putchar('\n'); fflush(stdout); }
            break;
        }
        if (ch == 8 || ch == 127) {  // backspace / delete
            if (n) {
                n--;
                // Rub out on screen too, or the display and the buffer diverge.
                if (echo) { fputs("\b \b", stdout); fflush(stdout); }
            }
            continue;
        }
        if (ch == 27) {
            // An arrow key is ESC [ A..D. Swallow the sequence rather than
            // letting "[A" land in the command buffer. Timeout so that a bare
            // ESC does not wedge the reader waiting for a sequence.
            if (getchar_timeout_us(20000) >= 0) getchar_timeout_us(20000);
            continue;
        }
        if (ch < 0x20 || ch > 0x7E) continue;  // other control characters
        if (n < cap - 1) {
            buf[n++] = (char)ch;
            if (echo) { putchar(ch); fflush(stdout); }
        }
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
        int r = read_line(line, cap, false);
        if (r < 0) { printf("(terminal disconnected)\n"); break; }
        if (r == 0) { printf("(blank line)\n"); break; }
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

// Load one of the built-in test images, if this firmware was built with them.
// A default build has none: the images are GPLv3 and this project is
// CC BY-NC-SA, so they are compiled in only behind -DEMBED_FUNCTEST=ON. See
// common/functest_images.h. Everything here still works via 'L' either way.
static void load_builtin(char key) {
    // 'c' is always available: the counter loop is our own code, it is the
    // boot default, and it is what the retention scan needs. Without it there
    // is no way back to the default image after loading a test.
    if (key == 'c') {
        retention_load_image();
        functest_set_image(NULL);
        functest_disable();
        printf("loaded the counter loop at $0200 (A increments, stored to $0300\n"
               "each pass -- watch the A-register LEDs). Watcher off. R then t 40.\n");
        return;
    }

    const functest_image_t *img = key ? functest_image(key) : NULL;
    if (!img) {
        printf("built-in images:\n");
        printf("  T c   counter loop           the boot default; A counts on the LEDs\n");
        for (uint8_t i = 0; i < functest_image_count(); i++) {
            const functest_image_t *e = functest_image_at(i);
            printf("  T %c   %-22s %5u traps, progress at $%04X\n",
                   e->key, e->name, e->trap_count, e->case_addr);
        }
        if (!functest_images_available())
            printf("  (the acceptance tests are not compiled in -- they are GPLv3, see\n"
                   "   gen/functest/README.md. Rebuild with -DEMBED_FUNCTEST=ON, or\n"
                   "   paste one with L.)\n");
        else if (key)
            printf("no such image: '%c'\n", key);
        return;
    }

    memcpy(bus_mem(), img->image, img->image_len);
    // The generator patches the reset vector, so unlike 'L' there is no
    // `m 3FFC 00 04` follow-up step. Print it as proof, not as reassurance.
    uint16_t vec = (uint16_t)(bus_mem()[0x3FFC] | (bus_mem()[0x3FFD] << 8));
    functest_set_image(img);
    functest_enable(img->case_addr);
    printf("loaded %s (%lu bytes), reset vector $3FFC -> $%04X\n",
           img->name, (unsigned long)img->image_len, vec);
    printf("watcher on, progress at $%04X, %u traps known -- R then g to run\n",
           img->case_addr, img->trap_count);
    // Say this at load time, not after a wasted multi-hour run. A vector that
    // does not land on a self-loop means a spurious interrupt is absorbed
    // silently and shows up later as a failure somewhere unrelated.
    if (!img->nmi_is_trap || !img->irq_is_trap)
        printf("WARNING: %s%s%s vector target is live code, not a self-loop.\n"
               "  A spurious interrupt would be absorbed and misreported as a\n"
               "  failure elsewhere. Tie irq and nmi high at the bond pads --\n"
               "  neither has a pull-up on this board.\n",
               img->nmi_is_trap ? "" : "NMI",
               (!img->nmi_is_trap && !img->irq_is_trap) ? " and " : "",
               img->irq_is_trap ? "" : "IRQ");
}

static void print_functest_status(void) {
    const functest_state_t *f = functest_state();
    printf("functest %s, test_case at $%04X", f->enabled ? "ON" : "off", f->case_addr);
    if (f->have_case)
        printf(", last test $%02X at cycle %lu", f->test_case, (unsigned long)f->case_cycle);
    if (f->trapped) {
        printf(", TRAPPED at $%04X (cycle %lu)", f->trap_addr, (unsigned long)f->trap_cycle);
        if (f->trap)
            printf(" = %s %s line %u", f->trap_is_pass ? "PASS" : "FAIL",
                   functest_kind_name(f->trap->kind), (unsigned)f->trap->line);
    }
    printf("\n");
}

// Print a stall duration in whichever unit reads naturally.
static void fmt_us(char *buf, size_t n, uint32_t us) {
    if (us < 1000u) snprintf(buf, n, "%lu us", (unsigned long)us);
    else if (us < 1000000u) snprintf(buf, n, "%lu.%03lu ms",
                                     (unsigned long)(us / 1000u), (unsigned long)(us % 1000u));
    else snprintf(buf, n, "%lu.%03lu s",
                  (unsigned long)(us / 1000000u), (unsigned long)((us / 1000u) % 1000u));
}

static void tester_report(uint32_t us, bool survived) {
    char b[24];
    fmt_us(b, sizeof b, us);
    printf("  %12s -> %s\n", b, survived ? "survived" : "lost");
}

// A scan can run for minutes; let a keypress cut it short between trials.
static bool tester_abort(void) { return getchar_timeout_us(0) >= 0; }

static void print_trace_entry(bus_trace_t t) {
    printf("%8lu  %04X  %02X  %c%s\n", (unsigned long)t.cycle, t.addr, t.data,
           t.rw_read ? 'r' : 'W', t.sync ? "  SYNC" : "");
}

static void help(void) {
    printf("discrete6502 tester\n"
           "  R [N]      reset, then run N cycles -- as ONE operation. Reset\n"
           "             then a separate run does not work: the clock parks\n"
           "             between commands and state decays in about 1 ms.\n"
           "  c N        run N cycles (quiet)\n"
           "  t N        run N cycles, print each bus cycle\n"
           "  s [N]      run N instructions from HERE, printing cycles. NOT a\n"
           "             single-step: state does not survive between commands,\n"
           "             so repeating it resumes garbage. Use R N instead.\n"
           "  d [N]      dump last N trace entries (default 32)\n"
           "  x A L      hexdump L bytes of image at offset A (hex)\n"
           "  m A B..    poke bytes at offset A (all hex)\n"
           "  p US       set clock half-period in us (default 50 = 10 kHz). Live\n"
           "             only -- S clock N then S save to make it the default.\n"
           "  z          zero cycle counter + trace\n"
           "  L          load an Intel hex image pasted into this terminal\n"
           "  T [c|f|d]  load a built-in image: c=counter loop (the boot default),\n"
           "             f=functional, d=decimal. Bare T lists them.\n"
           "  k [on|off|ADDR]  functional-test watcher (test_case addr, hex)\n"
           "  g [N]      go: run N cycles (0/omitted = until a self-loop),\n"
           "             printing watcher progress; any key interrupts\n"
           "  w MS       charge retention: freeze the clock MS ms, did it survive?\n"
           "  W [MAXMS]  find the retention boundary by bisection (default 4000)\n"
           "             both reload the counter image and need it to run\n"
           "  h          this help\n"
           "columns: cycle  addr(14-bit)  data  r/W  SYNC\n"
           "C [on|off|TEXT]   console: show output, enable, or send TEXT to the\n"
           "                  CPU. $3F00 out, $3F01 in (read, then write to ack),\n"
           "                  $3F02 status. OFF during the functional test.\n"
           "S                 show settings; S autorun on|off, S clock US,\n"
           "                  S store (memory -> boot image), S forget, S save\n");
}

int main(void) {
    // stdio FIRST, always. USB and the 1200-baud reset path must be alive before
    // anything else can hang, or a soldered-down Pico stops being reprogrammable.
    stdio_init_all();
    settings_load();

    // Push-pull 3.3 V clock by default -- the board has NO pull-up on
    // clk0, so open-drain only works with an external 10k from the PHI0
    // bond pad to VCC (croc clips). See README "Logic levels".
    bus_init(settings()->clk_open_drain);
    bus_set_half_period_us(settings()->half_period_us);
    bus_set_watch(functest_watch);  // dormant until 'k on'
    bus_set_io(console_io);         // dormant until 'C on'

    bool stored = settings_program_load_into_ram();
    if (!stored) retention_load_image();

    if (settings()->autorun) bus_reset_sequence();

    s_stored = stored;

    char line[128];
    bool attached = false;
    for (;;) {
        // The only wait in this firmware, and it does not block: with autorun on
        // the CPU free-runs while nobody is looking, which is both the useful
        // state and the cooler one.
        if (!stdio_usb_connected()) {
            attached = false;
            idle_work();
            continue;
        }
        if (!attached) {
            attached = true;
            sleep_ms(200);   // let the host finish opening the port
            greet();
        }
        printf("> ");
        fflush(stdout);
        if (read_line(line, (int)sizeof line, true) < 0) continue;  // terminal left

        // strtok writes NULs over the delimiters, so a command whose argument
        // is free text (C) cannot put the words back together afterwards. Keep
        // the line as typed.
        char raw[sizeof line];
        memcpy(raw, line, sizeof raw);

        char *tok = strtok(line, " ");
        if (!tok) continue;
        switch (tok[0]) {
        case 'h': help(); break;
        case 'C': {
            char *a = strtok(NULL, " ");
            if (!a) {
                char buf[256];
                uint32_t n = console_take_output(buf, sizeof buf);
                printf("console %s at $%04X out / $%04X in / $%04X status\n",
                       console_enabled() ? "ON" : "off", CONSOLE_OUT_ADDR,
                       CONSOLE_IN_ADDR, CONSOLE_STATUS_ADDR);
                printf("%lu chars printed since reset, %lu queued for the CPU\n",
                       (unsigned long)console_output_total(),
                       (unsigned long)console_input_pending());
                if (n) printf("--- output ---\n%s\n--------------\n", buf);
                printf("usage: C on|off | C <text to send the CPU>\n");
                break;
            }
            if (!strcmp(a, "on") || !strcmp(a, "off")) {
                bool on = a[1] == 'n';
                console_enable(on);
                printf("console %s\n", on ? "on" : "off");
                // Worth saying every time rather than once in a manual: this is
                // a silent, confusing failure if you hit it during a long run.
                if (on && functest_get_image())
                    printf("WARNING: a functional-test image is loaded. The suite\n"
                           "  checksums RAM up to $3FFF, and the console intercepts\n"
                           "  three addresses inside that range, so it will fail a\n"
                           "  RAM check that has nothing to do with the CPU.\n");
                break;
            }
            // Everything after "C " is text for the CPU, spaces included.
            const char *text = raw + 1;
            while (*text == ' ') text++;
            uint32_t k = console_push_input(text);
            printf("queued %lu chars (%lu waiting)\n", (unsigned long)k,
                   (unsigned long)console_input_pending());
            break;
        }
        case 'S': {
            char *a = strtok(NULL, " "), *b = strtok(NULL, " ");
            if (!a) {
                printf("settings (%s):\n", settings_were_stored() ? "from flash" : "defaults");
                printf("  clock    %lu us half-period (%lu Hz)\n",
                       (unsigned long)settings()->half_period_us,
                       (unsigned long)(500000UL / (settings()->half_period_us ?: 1)));
                printf("  autorun  %s\n", settings()->autorun ? "on" : "off");
                if (settings_program_len()) {
                    char d[24];
                    settings_fmt_duration(d, sizeof d, settings_program_seconds());
                    printf("  image    %s, %lu bytes\n",
                           settings()->program_name[0] ? settings()->program_name : "stored",
                           (unsigned long)settings_program_len());
                    printf("  runtime  about %s at this clock\n", d);
                } else {
                    printf("  image    built-in counter\n");
                }
                printf("  wifi     %s\n",
                       settings()->wifi_ssid[0] ? settings()->wifi_ssid : "(not set)");
                printf("usage: S autorun on|off | S clock US | S store | S forget | S save\n");
                break;
            }
            if (!strcmp(a, "autorun") && b) settings()->autorun = !strcmp(b, "on");
            else if (!strcmp(a, "clock") && b) {
                uint32_t us = (uint32_t)strtoul(b, NULL, 0);
                if (us) { settings()->half_period_us = us; bus_set_half_period_us(us); }
            } else if (!strcmp(a, "store")) {
                // Whatever is in emulated memory becomes the boot image. If a
                // built-in test is loaded we know its name and how long it runs,
                // which is what makes the estimate below possible.
                const functest_image_t *im = functest_get_image();
                bool ok = settings_program_save(bus_mem(), BUS_MEM_SIZE,
                                                im ? im->name : NULL,
                                                im ? im->cycles : 0);
                if (!ok) { printf("flash write refused\n"); break; }
                char d[24];
                settings_fmt_duration(d, sizeof d, settings_program_seconds());
                printf("stored 16 KB as the boot image, with the clock now set\n");
                printf("  %s at %lu us half-period (%lu Hz) -- runs for about %s\n",
                       im ? im->name : "unknown image",
                       (unsigned long)settings()->half_period_us,
                       (unsigned long)(500000UL / (settings()->half_period_us ?: 1)), d);
                break;
            } else if (!strcmp(a, "forget")) {
                printf(settings_program_clear() ? "boot image cleared\n" : "flash write refused\n");
                break;
            } else if (strcmp(a, "save")) { printf("unknown: %s\n", a); break; }
            printf(settings_save() ? "saved\n" : "flash write refused\n");
            break;
        }
        case 'R': {
            // R [N] resets and then runs N cycles as ONE operation. Doing them
            // as two commands you type in sequence does not work on this CPU:
            // the clock parks between them, and the worst dynamic node holds
            // charge for about 1.1 ms (measured, board #1), so the reset state
            // is long gone before the second command arrives. Anything that
            // needs a defined starting state has to be atomic with the reset.
            char *a = strtok(NULL, " ");
            uint32_t n = a ? (uint32_t)strtoul(a, NULL, 0) : 0;
            bus_reset_sequence();
            if (n) bus_run(n);
            printf("reset released, ran %lu cycles, now at cycle %lu\n",
                   (unsigned long)n, (unsigned long)bus_cycle_count);
            if (!n)
                printf("  note: the clock is parked now. State decays in about 1 ms,\n"
                       "        so a follow-up command starts from garbage. Use R N.\n");
            break;
        }
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
            // Live only. Writing flash parks the bus engine for tens of
            // milliseconds against a ~1.1 ms retention floor, so persisting the
            // clock on every change would destroy the CPU's state each time.
            // 'S clock N' then 'S save' is the deliberate way to keep it.
            char *a = strtok(NULL, " ");
            if (a) {
                uint32_t us = (uint32_t)strtoul(a, NULL, 0);
                if (us) {
                    bus_set_half_period_us(us);
                    printf("clock now %lu us half-period (%lu Hz)%s\n",
                           (unsigned long)us, (unsigned long)(500000UL / us),
                           us == settings()->half_period_us
                               ? "" : " -- not saved; S clock N then S save to keep it");
                }
            }
            break;
        }
        case 'z':
            bus_cycle_count = 0;
            bus_trace_clear();
            functest_clear();
            break;
        case 'L':
            functest_set_image(NULL);  // hand-loaded: we cannot name its traps
            load_intel_hex(line, (int)sizeof line);
            break;
        case 'T': {
            char *a = strtok(NULL, " ");
            load_builtin(a ? a[0] : 0);
            break;
        }
        case 'w': {
            // MICROSECONDS. Was milliseconds before 2026-07-31; the change is
            // in the safe direction (an old "w 5" now stalls 5 us, not 5 ms).
            char *a = strtok(NULL, " ");
            uint32_t us = a ? strtoul(a, NULL, 0) : RET_SCAN_START_US;
            char b[24];
            fmt_us(b, sizeof b, us);
            printf("(reloading the counter image -- the retention test needs it)\n");
            retention_load_image();
            bool ok = retention_trial(us);
            printf("stalled %s: %s\n", b, ok ? "SURVIVED" : "STATE LOST");
            break;
        }
        case 'W': {
            char *a = strtok(NULL, " ");   // MICROSECONDS
            uint32_t limit = a ? strtoul(a, NULL, 0) : RET_SCAN_DEFAULT_LIMIT_US;
            printf("(reloading the counter image -- the retention test needs it)\n");
            uint32_t good, bad;
            switch (retention_scan(limit, tester_report, tester_abort, &good, &bad)) {
            case RET_SCAN_CONTROL_FAILED:
                printf("control FAILED: the CPU does not run even with no stall.\n"
                       "fix that before trusting any retention number.\n");
                break;
            case RET_SCAN_ABOVE_LIMIT: {
                char b[24]; fmt_us(b, sizeof b, good);
                printf("still alive after %s -- raise the limit: W %lu\n",
                       b, (unsigned long)limit * 4);
                break;
            }
            case RET_SCAN_ABORTED: {
                char b[24]; fmt_us(b, sizeof b, good);
                printf("interrupted after %s\n", b);
                break;
            }
            case RET_SCAN_BOUNDED: {
                char bg[24], bb[24];
                fmt_us(bg, sizeof bg, good); fmt_us(bb, sizeof bb, bad);
                printf("\nretention boundary: survives %s, fails at %s\n", bg, bb);
                printf("=> clock floor is about %lu Hz; keep any single-step pause\n"
                       "   well under %s\n",
                       (unsigned long)(good ? 1000000ul / good : 0), bg);
                break;
            }
            }
            break;
        }
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
