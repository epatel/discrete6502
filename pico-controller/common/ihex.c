#include "ihex.h"

#include <string.h>

static int hex2(const char *s) {
    int v = 0;
    for (int i = 0; i < 2; i++) {
        char c = s[i];
        int d = (c >= '0' && c <= '9')   ? c - '0'
                : (c >= 'a' && c <= 'f') ? c - 'a' + 10
                : (c >= 'A' && c <= 'F') ? c - 'A' + 10
                                         : -1;
        if (d < 0) return -1;
        v = v * 16 + d;
    }
    return v;
}

void ihex_begin(ihex_stats_t *st) { memset(st, 0, sizeof *st); }

bool ihex_line(ihex_stats_t *st, const char *line, uint8_t *mem, uint32_t mem_mask) {
    if (st->eof) return false;
    size_t n = strlen(line);
    if (n == 0) return true;  // blank line: ignore
    if (line[0] != ':' || n < 11) { st->bad++; return true; }

    int len = hex2(line + 1), ah = hex2(line + 3), al = hex2(line + 5), type = hex2(line + 7);
    if (len < 0 || ah < 0 || al < 0 || type < 0 || n < (size_t)(11 + 2 * len)) {
        st->bad++;
        return true;
    }

    // checksum first, so a corrupt line never reaches memory
    uint32_t sum = (uint32_t)len + (uint32_t)ah + (uint32_t)al + (uint32_t)type;
    for (int i = 0; i < len; i++) {
        int b = hex2(line + 9 + 2 * i);
        if (b < 0) { st->bad++; return true; }
        sum += (uint32_t)b;
    }
    int cs = hex2(line + 9 + 2 * len);
    if (cs < 0 || (uint8_t)(sum + (uint32_t)cs) != 0) { st->bad++; return true; }

    if (type == 0) {
        uint16_t addr = (uint16_t)((ah << 8) | al);
        for (int i = 0; i < len; i++)
            mem[(addr + i) & mem_mask] = (uint8_t)hex2(line + 9 + 2 * i);
        st->bytes += (uint32_t)len;
    }
    st->records++;
    if (type == 1) { st->eof = true; return false; }
    return true;
}
