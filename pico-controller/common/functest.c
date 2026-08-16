#include "functest.h"

#include <stdio.h>

static functest_state_t st = {.case_addr = FUNCTEST_CASE_ADDR_DEFAULT};
static uint16_t last_sync_addr;
static bool have_sync;
static bool quiet;
static const functest_image_t *image;

void functest_set_quiet(bool q) { quiet = q; }

void functest_set_image(const functest_image_t *img) { image = img; }
const functest_image_t *functest_get_image(void) { return image; }

void functest_enable(uint16_t case_addr) {
    st.case_addr = case_addr & (BUS_MEM_SIZE - 1);
    st.enabled = true;
    functest_clear();
}

void functest_disable(void) { st.enabled = false; }

void functest_clear(void) {
    st.have_case = false;
    st.test_case = 0;
    st.case_cycle = 0;
    st.loop_addr = 0;
    st.loop_hits = 0;
    st.trapped = false;
    st.trap_addr = 0;
    st.trap_cycle = 0;
    st.trap = 0;
    st.trap_is_pass = false;
    have_sync = false;
    last_sync_addr = 0;
}

const functest_state_t *functest_state(void) { return &st; }

bool functest_watch(const bus_trace_t *t) {
    if (!st.enabled) return true;
    if (st.trapped) return false;  // stay stopped until cleared

    // progress: the suite writes its sub-test number to test_case
    if (!t->rw_read && t->addr == st.case_addr) {
        uint32_t delta = st.have_case ? t->cycle - st.case_cycle : 0;
        st.test_case = t->data;
        st.case_cycle = t->cycle;
        st.have_case = true;
        if (quiet) { /* reported through the shared snapshot instead */ }
        else if (t->data == 0xF0)
            printf("[functest] test $F0: opcode tests complete, RAM integrity check running"
                   " (cycle %lu)\n", (unsigned long)t->cycle);
        else
            printf("[functest] test $%02X at cycle %lu (+%lu)\n", t->data,
                   (unsigned long)t->cycle, (unsigned long)delta);
    }

    // trap/success: consecutive opcode fetches at one address = branch-to-self
    if (t->sync) {
        if (have_sync && t->addr == last_sync_addr) {
            st.loop_addr = t->addr;
            if (++st.loop_hits >= FUNCTEST_LOOP_HITS) {
                st.trapped = true;
                st.trap_addr = t->addr;
                st.trap_cycle = t->cycle;
                st.trap = functest_trap_lookup(image, t->addr);
                st.trap_is_pass = st.trap && functest_kind_is_pass(st.trap->kind);
                if (quiet) return false;
                printf("\n[functest] SELF-LOOP at $%04X after %lu cycles"
                       " (last test $%02X).\n",
                       t->addr, (unsigned long)t->cycle,
                       st.have_case ? st.test_case : 0);
                // Check the interrupt vectors before the trap map: nmi_trap
                // uses the same `trap` macro as every failure trap, so by text
                // it is indistinguishable from a real one. Only its address
                // tells them apart.
                if (image && t->addr == image->nmi_addr)
                    printf("[functest] this is the NMI vector target -- a spurious NMI,"
                           " NOT a CPU failure. Tie the nmi bond pad high (it has no"
                           " pull-up) and rerun.\n");
                else if (image && t->addr == image->irq_addr)
                    printf("[functest] this is the IRQ vector target -- a spurious IRQ,"
                           " NOT a CPU failure. Tie the irq bond pad high and rerun.\n");
                else if (st.trap)
                    // The map knows this address, so say what it means instead
                    // of making the reader find it. `kind` distinguishes the
                    // PASS self-loop from the many failure traps, and from the
                    // int_trap that a spurious IRQ/NMI lands in -- which on
                    // this board is a real possibility, since irq and nmi carry
                    // no pull-up, and is NOT a CPU failure.
                    printf("[functest] %s -- %s, listing line %u"
                           " (test $%02X in that region)\n",
                           st.trap_is_pass ? "*** PASS ***" : "FAIL",
                           functest_kind_name(st.trap->kind),
                           (unsigned)st.trap->line, st.trap->test_case);
                else if (image)
                    printf("[functest] address is NOT in %s's trap map -- the CPU"
                           " is looping somewhere the test never parks.\n",
                           image->name);
                else
                    printf("[functest] PASS if that is the `success` address in your"
                           " listing, else it is the trap for the opcode just above"
                           " it. (Build with -DEMBED_FUNCTEST=ON to have this"
                           " named for you.)\n");
                return false;
            }
        } else {
            st.loop_hits = 1;
            st.loop_addr = t->addr;
        }
        last_sync_addr = t->addr;
        have_sync = true;
    }
    return true;
}
