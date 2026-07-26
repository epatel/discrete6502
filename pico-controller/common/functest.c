#include "functest.h"

#include <stdio.h>

static functest_state_t st = {.case_addr = FUNCTEST_CASE_ADDR_DEFAULT};
static uint16_t last_sync_addr;
static bool have_sync;

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
        if (t->data == 0xF0)
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
                printf("\n[functest] SELF-LOOP at $%04X after %lu cycles"
                       " (last test $%02X).\n"
                       "[functest] PASS if that is the `success` address in your"
                       " listing, else it is the trap for the opcode just above it.\n",
                       t->addr, (unsigned long)t->cycle,
                       st.have_case ? st.test_case : 0);
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
