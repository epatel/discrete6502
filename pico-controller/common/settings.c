#include "settings.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "bus6502.h"
#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/flash.h"
#include "pico/stdlib.h"

#define RESERVE (64 * 1024)
#define BASE_OFF ((uint32_t)(PICO_FLASH_SIZE_BYTES - RESERVE))
#define SET_OFF (BASE_OFF)
#define PROG_OFF (BASE_OFF + FLASH_SECTOR_SIZE)
#define PROG_MAX BUS_MEM_SIZE  // 16 KB: everything the Pico can address
#define PROG_SECTORS (((PROG_MAX) + FLASH_SECTOR_SIZE - 1) / FLASH_SECTOR_SIZE)

// The reserved region must fit, and must not start before the firmware ends.
// The first is checkable here; the second is not (the linker decides), but at
// 345 KB of firmware against a 4 MB part there is 3.7 MB of daylight.
_Static_assert(PROG_OFF + PROG_MAX <= PICO_FLASH_SIZE_BYTES,
               "settings + program area runs past the end of flash");
_Static_assert(sizeof(settings_t) <= FLASH_SECTOR_SIZE, "settings_t exceeds one sector");

// Flash writes go through a staging buffer because flash_range_program needs a
// pointer that stays valid while XIP is off -- which a pointer INTO flash would
// not be. That is the classic way to brick this operation.
static uint8_t stage[FLASH_SECTOR_SIZE];

static settings_t live;
static bool was_stored;

static uint32_t crc32(const void *data, size_t n) {
    const uint8_t *p = (const uint8_t *)data;
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; i++) {
        c ^= p[i];
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(c & 1)));
    }
    return ~c;
}

static uint32_t record_crc(const settings_t *s) {
    const uint8_t *after = (const uint8_t *)s + offsetof(settings_t, crc) + sizeof(s->crc);
    return crc32(after, sizeof(*s) - offsetof(settings_t, crc) - sizeof(s->crc));
}

static const uint8_t *flash_at(uint32_t off) { return (const uint8_t *)(XIP_BASE + off); }

static void defaults(void) {
    memset(&live, 0, sizeof live);
    live.magic = SETTINGS_MAGIC;
    live.version = SETTINGS_VERSION;
    live.size = sizeof live;
    // 50 us half-period = 10 kHz. Inside the window measured on board #1:
    // floor 456-871 Hz from charge retention, ceiling ~20 kHz from PLA fanout.
    live.half_period_us = 50;
    live.low_period_us = 0;  // 0 = symmetric, the long-standing behaviour
    live.autorun = 1;
    live.clk_open_drain = 0;
}

void settings_load(void) {
    const settings_t *f = (const settings_t *)flash_at(SET_OFF);
    if (f->magic == SETTINGS_MAGIC && f->version == SETTINGS_VERSION &&
        f->size == sizeof(settings_t) && record_crc(f) == f->crc) {
        memcpy(&live, f, sizeof live);
        was_stored = true;
    } else {
        defaults();
        was_stored = false;
    }
}

settings_t *settings(void) { return &live; }
bool settings_were_stored(void) { return was_stored; }

// ---- flash plumbing -------------------------------------------------------

typedef struct {
    uint32_t off;
    uint32_t sectors;
    const uint8_t *src;  // NULL = erase only
    uint32_t len;
} write_job_t;

// Runs with XIP off and the other core parked. Must touch nothing in flash.
static void do_write(void *param) {
    const write_job_t *j = (const write_job_t *)param;
    flash_range_erase(j->off, j->sectors * FLASH_SECTOR_SIZE);
    if (j->src && j->len) flash_range_program(j->off, j->src, j->len);
}

static bool run_job(write_job_t *j) {
    // 500 ms is generous: the other core only has to reach its lockout point.
    return flash_safe_execute(do_write, j, 500) == PICO_OK;
}

bool settings_save(void) {
    live.magic = SETTINGS_MAGIC;
    live.version = SETTINGS_VERSION;
    live.size = sizeof live;
    live.crc = record_crc(&live);

    memset(stage, 0xFF, sizeof stage);
    memcpy(stage, &live, sizeof live);
    write_job_t j = {SET_OFF, 1, stage, FLASH_PAGE_SIZE * ((sizeof live + FLASH_PAGE_SIZE - 1) / FLASH_PAGE_SIZE)};
    if (!run_job(&j)) return false;
    was_stored = true;
    return true;
}

bool settings_erase(void) {
    write_job_t j = {SET_OFF, 1, NULL, 0};
    if (!run_job(&j)) return false;
    defaults();
    was_stored = false;
    return true;
}

// ---- stored image ---------------------------------------------------------

const uint8_t *settings_program(void) {
    if (!live.have_program || !live.program_len) return NULL;
    const uint8_t *p = flash_at(PROG_OFF);
    if (crc32(p, live.program_len) != live.program_crc) return NULL;
    return p;
}

uint32_t settings_program_len(void) { return settings_program() ? live.program_len : 0; }

bool settings_program_save(const uint8_t *image, uint32_t len,
                           const char *name, uint32_t cycles) {
    if (!image || !len || len > PROG_MAX) return false;

    // Programmed a sector at a time out of the staging buffer, because the
    // source must not live in flash while XIP is off.
    for (uint32_t done = 0; done < len; done += FLASH_SECTOR_SIZE) {
        uint32_t chunk = len - done;
        if (chunk > FLASH_SECTOR_SIZE) chunk = FLASH_SECTOR_SIZE;
        memset(stage, 0xFF, sizeof stage);
        memcpy(stage, image + done, chunk);
        write_job_t j = {PROG_OFF + done, 1, stage, FLASH_SECTOR_SIZE};
        if (!run_job(&j)) return false;
    }
    live.have_program = 1;
    live.program_len = len;
    live.program_crc = crc32(image, len);
    live.program_cycles = cycles;
    memset(live.program_name, 0, sizeof live.program_name);
    if (name) strncpy(live.program_name, name, sizeof live.program_name - 1);
    // Writes the whole record, so the clock in force right now is stored too.
    return settings_save();
}

bool settings_program_clear(void) {
    live.have_program = 0;
    live.program_len = 0;
    live.program_crc = 0;
    live.program_cycles = 0;
    live.program_name[0] = 0;
    return settings_save();
}

uint32_t settings_program_seconds(void) {
    if (!live.program_cycles || !live.half_period_us) return 0;
    // A cycle is two half-periods. 64-bit intermediate: 96.8 M cycles times
    // 100 us overflows 32 bits by four orders of magnitude.
    uint64_t us = (uint64_t)live.program_cycles * 2u * live.half_period_us;
    return (uint32_t)(us / 1000000u);
}

void settings_fmt_duration(char *buf, size_t n, uint32_t s) {
    if (!s) snprintf(buf, n, "unknown");
    else if (s < 90) snprintf(buf, n, "%lu s", (unsigned long)s);
    else if (s < 5400) snprintf(buf, n, "%lu min", (unsigned long)((s + 30) / 60));
    else snprintf(buf, n, "%lu h %02lu m", (unsigned long)(s / 3600),
                  (unsigned long)((s % 3600) / 60));
}

bool settings_program_load_into_ram(void) {
    const uint8_t *p = settings_program();
    if (!p) return false;
    uint8_t *mem = bus_mem();
    memset(mem, 0, BUS_MEM_SIZE);
    memcpy(mem, p, live.program_len);
    return true;
}
