// The default build: no test images compiled in.
//
// This file exists so that nothing else in the firmware needs an #ifdef. Every
// call site works unchanged; it just finds no images. See functest_images.h for
// why the real thing is opt-in (GPLv3 vs CC BY-NC-SA), and CMake's
// EMBED_FUNCTEST option for how to swap this out for the generated version.
#include "functest_images.h"

bool functest_images_available(void) { return false; }

uint8_t functest_image_count(void) { return 0; }
const functest_image_t *functest_image_at(uint8_t i) { (void)i; return 0; }
const functest_image_t *functest_image(char key) { (void)key; return 0; }

const functest_trap_t *functest_trap_lookup(const functest_image_t *img, uint16_t addr) {
    (void)img;
    (void)addr;
    return 0;
}

const char *functest_kind_name(uint8_t kind) { (void)kind; return "?"; }
bool functest_kind_is_pass(uint8_t kind) { (void)kind; return false; }
