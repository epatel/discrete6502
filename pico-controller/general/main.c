// discrete6502 general — free-running runtime with memory-mapped IO.
//
// Boots the CPU and lets it run at full configured speed. One IO port is
// mapped into the 16 KB window:
//   write $3F00 (CPU: $FF00 mirrored) -> character out over Pico USB serial
//
// Default image prints "HELLO 6502" forever — proof of life you can read
// in a terminal while the register LEDs flicker.
#include "bus6502.h"
#include "console.h"
#include "settings.h"

#include "pico/stdlib.h"
#include <stdio.h>
#include <string.h>

#define IO_CHAROUT 0x3F00u

// The console owns $3F00-$3F02 now; this just mirrors what the CPU prints out
// to USB serial as it appears, which is what this firmware is for.
static bool io(uint16_t addr, bool is_write, uint8_t *data) {
    bool handled = console_io(addr, is_write, data);
    if (handled && is_write && addr == CONSOLE_OUT_ADDR) putchar(*data);
    return handled;
}

static void load_default_image(void) {
    uint8_t *m = bus_mem();
    static const uint8_t prog[] = {
        0xA2, 0xFF,        // 0200 LDX #$FF
        0x9A,              // 0202 TXS
        0xA2, 0x00,        // 0203 LDX #$00
        0xBD, 0x00, 0x33,  // 0205 LDA $3300,X   <- next char
        0xF0, 0x06,        // 0208 BEQ $0210     end of string?
        0x8D, 0x00, 0x3F,  // 020A STA $3F00     char out
        0xE8,              // 020D INX
        0xD0, 0xF5,        // 020E BNE $0205
        0x4C, 0x03, 0x02,  // 0210 JMP $0203     restart string
    };
    memcpy(m + 0x0200, prog, sizeof prog);
    strcpy((char *)m + 0x3300, "HELLO 6502\r\n");
    m[0x3FFC] = 0x00;  // reset vector -> $0200
    m[0x3FFD] = 0x02;
}

int main(void) {
    stdio_init_all();
    settings_load();
    bus_init(settings()->clk_open_drain);  // push-pull; see README "Logic levels"
    bus_set_phase_us(settings()->half_period_us,
                     settings()->low_period_us ? settings()->low_period_us
                                               : settings()->half_period_us);
    console_enable(true);   // this firmware exists to run programs that talk
    bus_set_io(io);

    // A stored image if one was saved, otherwise the built-in demo.
    bool stored = settings_program_load_into_ram();
    if (!stored) load_default_image();

    // Start immediately. This firmware exists to free-run, and the old sequence
    // waited for a USB terminal first -- which on a demo board with no computer
    // attached meant the clock stayed parked forever. That is the board's PEAK
    // current state (1.4 A unclocked against 0.87 A clocked, measured) because
    // undefined dynamic nodes leave thousands of FETs biased near threshold.
    bus_reset_sequence();

    bool announced = false;
    for (;;) {
        bus_step_cycle();
        // Say hello once, if and when somebody plugs a terminal in. Checking
        // every 4096 cycles keeps it off the critical path of a dynamic clock.
        if (!announced && (bus_cycle_count & 0xFFFu) == 0 && stdio_usb_connected()) {
            printf("discrete6502 general: free-running since boot, %s image, "
                   "%lu us half-period.\n", stored ? "stored" : "built-in",
                   (unsigned long)settings()->half_period_us);
            announced = true;
        }
    }
}
