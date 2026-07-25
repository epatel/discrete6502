// discrete6502 general — free-running runtime with memory-mapped IO.
//
// Boots the CPU and lets it run at full configured speed. One IO port is
// mapped into the 16 KB window:
//   write $3F00 (CPU: $FF00 mirrored) -> character out over Pico USB serial
//
// Default image prints "HELLO 6502" forever — proof of life you can read
// in a terminal while the register LEDs flicker.
#include "bus6502.h"

#include "pico/stdlib.h"
#include <stdio.h>
#include <string.h>

#define IO_CHAROUT 0x3F00u

static bool io(uint16_t addr, bool is_write, uint8_t *data) {
    if (addr == IO_CHAROUT && is_write) {
        putchar(*data);
        return true;
    }
    return false;
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
    bus_init(false);  // push-pull 3.3V clock; see README "Logic levels"
    bus_set_io(io);
    load_default_image();

    while (!stdio_usb_connected()) sleep_ms(100);
    printf("discrete6502 general: releasing reset, free-running.\n");

    bus_reset_sequence();
    for (;;) bus_step_cycle();
}
