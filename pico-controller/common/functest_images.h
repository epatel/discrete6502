// Optional built-in copies of Klaus Dormann's test images, plus their trap maps.
//
// WHY THIS IS OPTIONAL
// --------------------
// The suite is GPLv3; this project is CC BY-NC-SA 4.0, and the two are
// incompatible (GPLv3 forbids adding a NonCommercial restriction). Separate
// files in gen/functest/ are mere aggregation and fine. A firmware binary with
// the images compiled in is a combined work, so we never build or ship one by
// default:
//
//     cmake -B build -DEMBED_FUNCTEST=ON ..
//
// turns it on, which runs tools/embed_functest.py to generate
// functest_images.c (gitignored). Without the flag, functest_images_none.c is
// compiled instead, functest_images_available() returns false, and the tester's
// 'T' command tells you how to enable it. Everything still works via 'L'.
//
// WHAT IT BUYS
// ------------
//  * No paste. The functional test is 37.6 kB of Intel hex through a terminal,
//    by hand, at the point in the evening when you are least fresh.
//  * A named verdict. Without the trap map the firmware can only report "a
//    self-loop at $34D8" and you go to the CSV. With it, the firmware knows
//    that address is the PASS trap -- and, just as important, that $380B and
//    $3819 are the NMI and IRQ traps and NOT test failures. That distinction
//    matters on this board specifically: irq and nmi carry no pull-up, so a
//    spurious interrupt during a 2 h 41 m run is a real possibility and would
//    otherwise read as a CPU defect.
//
// Deliberately absent: the `source` column of the traps CSV. Those 48 kB are
// upstream's expression; the listing line number points at it and is enough.
#pragma once
#include <stdbool.h>
#include <stdint.h>

// One entry per trap: an address where the test parks in a branch-to-self.
// 6 bytes, no padding.
typedef struct {
    uint16_t addr;       // where it loops (masked into the 16 KB window)
    uint16_t line;       // line in upstream's assembly listing
    uint8_t test_case;   // the test number in force at that point
    uint8_t kind;        // index for functest_kind_name/_is_pass
} functest_trap_t;

typedef struct {
    char key;                      // 'f' functional, 'd' decimal
    const char *name;              // e.g. "6502_functional_test"
    const uint8_t *image;          // full 16 KB, zero-filled, vectors patched
    uint32_t image_len;
    const functest_trap_t *traps;  // sorted by addr
    uint16_t trap_count;
    uint16_t case_addr;            // where this test reports progress
    // Read out of the image's own vector block, so a spurious interrupt can be
    // named rather than mistaken for a CPU defect. This matters on this board:
    // irq and nmi carry only a 100R and clamp diodes -- no pull-up -- so both
    // float unless tied at the bond pads.
    uint16_t nmi_addr;
    uint16_t irq_addr;
    // True when that vector lands on a self-loop, i.e. the CPU stops there and
    // you can see it. FALSE IS THE DANGEROUS CASE: the functional test's
    // irq_trap is live BRK-handling code, not a trap, so a spurious IRQ is
    // absorbed, corrupts Y and SP, and surfaces later as a failure somewhere
    // unrelated. That is why tying irq high is necessary and not merely tidy.
    bool nmi_is_trap;
    bool irq_is_trap;
    // Cycles to completion, measured in an emulator. 0 = unknown. Divide by the
    // clock rate for a runtime the operator can plan around.
    uint32_t cycles;
} functest_image_t;

// False in a default build. Everything below returns empty in that case, so
// callers need no #ifdef -- only a message when this is false.
bool functest_images_available(void);

uint8_t functest_image_count(void);
const functest_image_t *functest_image_at(uint8_t i);
const functest_image_t *functest_image(char key);  // NULL if unknown/not built

// NULL if this address is not a known trap.
const functest_trap_t *functest_trap_lookup(const functest_image_t *img, uint16_t addr);

const char *functest_kind_name(uint8_t kind);
bool functest_kind_is_pass(uint8_t kind);
