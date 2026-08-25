// Persistent settings and a stored 6502 program, in the top of the Pico's flash.
//
// Three things needed somewhere to live across power cycles, and they may as
// well share one mechanism: the clock period and boot behaviour, the WiFi
// credentials (so changing network stops meaning "rebuild and reflash"), and a
// 6502 image to run at power-up.
//
// Layout, measured down from the end of flash so it does not move when the
// firmware grows:
//
//   FLASH_END - 64K   settings_t          1 sector, CRC checked
//   FLASH_END - 60K   6502 image          4 sectors = 16 KB, the whole address
//                                         space the Pico can decode
//
// THE HAZARD, and why saving stops the CPU: erasing or programming flash turns
// XIP off, so any code executing from flash dies mid-write. On a dual-core build
// (the wifi firmware runs the bus engine on core 1) the other core must be
// parked first. flash_safe_execute() does that, but only if core 1 has called
// multicore_lockout_victim_init() -- see settings_save().
//
// Two rules for anything that touches this file:
//   - keep stdio_init_all() first in main(). USB and the 1200-baud reset path
//     must come up before anything can hang, or a soldered Pico stops being
//     reprogrammable.
//   - never hold interrupts off for long. TinyUSB is serviced by a background
//     timer IRQ; starve it and the same reset path is lost.
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define SETTINGS_MAGIC 0x36353032u  // '6502'
#define SETTINGS_VERSION 2

#define SETTINGS_SSID_MAX 33
#define SETTINGS_PASS_MAX 65

typedef struct {
    uint32_t magic;
    uint16_t version;
    uint16_t size;
    uint32_t crc;  // CRC32 of everything after this field

    uint32_t half_period_us;  // clock; 50 us = 10 kHz, the measured-safe default
    uint8_t autorun;          // clock the CPU at boot instead of parking it
    uint8_t clk_open_drain;   // almost always false: clk0 has no board pull-up
    uint8_t have_program;     // a stored image is present and CRC-valid
    uint8_t reserved;
    uint32_t program_len;
    uint32_t program_crc;
    // What the stored image IS, so the board can say "about 2 h 41 m at this
    // clock" instead of leaving you to notice overnight that the clock was
    // wrong. 0 cycles = unknown, which an uploaded image usually is.
    uint32_t program_cycles;
    char program_name[24];

    char wifi_ssid[SETTINGS_SSID_MAX];
    char wifi_pass[SETTINGS_PASS_MAX];
} settings_t;

// Read flash into the RAM copy, or install defaults if absent/corrupt. Safe to
// call before anything else; never fails.
void settings_load(void);

// The live RAM copy. Edit it, then call settings_save().
settings_t *settings(void);

// True if flash held a valid record (i.e. these are not just defaults).
bool settings_were_stored(void);

// Write the RAM copy back. Returns false if the flash operation was refused --
// which on a dual-core build means core 1 never registered as a lockout victim.
// STOPS THE CPU for the duration: the caller must not be mid-instruction.
bool settings_save(void);

// Forget everything, including credentials, and fall back to defaults.
bool settings_erase(void);

// ---- stored 6502 image ----------------------------------------------------

// Pointer straight into the XIP window; no RAM is consumed by the image.
// NULL when nothing valid is stored.
const uint8_t *settings_program(void);
uint32_t settings_program_len(void);

// Store an image (at most 16 KB) and mark it as the boot default. `name` and
// `cycles` may be NULL/0 for an image whose identity is not known.
//
// This also persists the REST of the record, so the clock currently set becomes
// the one the stored program boots at. That is deliberate -- a program and the
// clock it should run at belong together -- but it is a side effect worth
// knowing: store the acceptance suite while the clock happens to sit at 1 kHz
// and the board will boot into a 27-hour run instead of a 3-hour one.
bool settings_program_save(const uint8_t *image, uint32_t len,
                           const char *name, uint32_t cycles);

// Seconds the stored program needs at the stored clock. 0 if either is unknown.
uint32_t settings_program_seconds(void);

// "2 h 41 m" / "9 min" / "unknown" into buf.
void settings_fmt_duration(char *buf, size_t n, uint32_t seconds);

// Drop the stored image; the built-in counter becomes the boot default again.
bool settings_program_clear(void);

// Copy the stored image into the Pico's emulated memory. False if none stored.
bool settings_program_load_into_ram(void);
