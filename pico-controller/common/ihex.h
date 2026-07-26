// Streaming Intel hex loader, one line at a time.
//
// Klaus Dormann's functional test suite assembles straight to Intel hex
// (as65 -s2), so this is the load path for both the serial 'L' command and
// the wifi firmware's POST /load. Lines arrive one at a time and are applied
// immediately, so a 30 kB hex file never needs to be buffered whole.
//
// Addresses are masked into the caller's window, which is what makes the
// suite's $FFFA-$FFFF vector block land at $3FFA-$3FFF as the CPU sees it
// through the board's 16 KB mirroring.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint32_t bytes;    // data bytes written
    uint32_t records;  // well-formed records seen
    uint32_t bad;      // malformed or bad-checksum lines
    bool eof;          // EOF record (type 01) seen
} ihex_stats_t;

void ihex_begin(ihex_stats_t *st);

// Apply one complete line (NUL-terminated, CR/LF already stripped).
// Blank lines are ignored. Returns false once the EOF record has been seen.
bool ihex_line(ihex_stats_t *st, const char *line, uint8_t *mem, uint32_t mem_mask);
