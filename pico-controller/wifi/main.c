// discrete6502 wifi firmware — control and observe the CPU from a browser.
//
// Motivation: the 6502 functional test suite is an hours-long run at our
// 10-20 kHz clock. Sitting at a serial terminal for that is no way to work,
// so this firmware puts the same controls on a web page: upload the Intel
// hex, start it, and watch test_case climb from anywhere.
//
// ARCHITECTURE — the one rule that matters:
//
//   core 1  the bus engine, and nothing else. Never touches lwIP, cyw43 or
//           stdio. It is the clock master for a DYNAMIC-logic CPU, so a
//           stretched clock phase is a correctness bug, not a hiccup.
//   core 0  wifi, lwIP, HTTP. Blocks freely; nobody cares.
//
// The two share a snapshot struct (core 1 writes, core 0 reads) and an SDK
// multicore queue for commands (core 0 writes, core 1 reads). This is why
// wifi is safe here at all: association and DHCP block for milliseconds at a
// time, which would be fatal inside the clock loop but is invisible on
// another core. functest is put in quiet mode for the same reason — its
// printf would block core 1 on USB stdio.
//
// Build: cmake -DWIFI_SSID=... -DWIFI_PASSWORD=... (never committed)
#include "bus6502.h"
#include "functest.h"
#include "ihex.h"
#include "page.h"
#include "retention.h"

#include "lwip/tcp.h"
#include "pico/cyw43_arch.h"
#include "netsrv.h"
#include "pico/multicore.h"
#include "pico/stdlib.h"
#include "pico/util/queue.h"
#include "hardware/watchdog.h"
#include "settings.h"
#include <stdio.h>
#include <string.h>

// Credentials now live in flash (common/settings.c) and are set through the
// captive portal. These remain only as optional build-time seeds for a board
// you want to arrive pre-provisioned; a plain build has neither.
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#define HTTP_PORT 80
#define MIRROR_LEN 32u  // recent cycles core 0 may read
#define MAX_CONN 4

// ---- shared state ---------------------------------------------------------

// Core 1 writes, core 0 reads. Fields are word-sized and individually atomic
// on ARM; a reader can still catch two adjacent cycles mixed, which for a
// twice-a-second display is not worth a lock in the clock loop.
static volatile uint32_t s_cycle, s_half = 50;
static volatile uint16_t s_addr, s_trap_addr;
static volatile uint8_t s_data, s_flags, s_test_case, s_trapped, s_ft_on;
static volatile bool s_running;

static bus_trace_t mirror[MIRROR_LEN];
static volatile uint32_t mirror_count;

// retention test state: core 1 runs it, core 0 only reports it. s_ret_seq
// increments once per completed trial so the page can log each result exactly
// once without needing an event channel.
static volatile uint8_t s_ret_busy, s_ret_verdict, s_ret_last_ok;
static volatile uint32_t s_ret_seq, s_ret_last_ms, s_ret_good, s_ret_bad;

static queue_t cmd_q;
typedef struct {
    uint8_t op;
    uint32_t arg;
} cmd_t;
enum { CMD_RUN, CMD_STOP, CMD_RESET, CMD_STEP, CMD_CLOCK, CMD_FT,
       CMD_RET, CMD_RETSCAN };

// ---- core 1: the bus engine ----------------------------------------------

static bool __not_in_flash_func(publish)(const bus_trace_t *t) {
    s_cycle = t->cycle;
    s_addr = t->addr;
    s_data = t->data;
    s_flags = (uint8_t)((t->rw_read ? 1u : 0u) | (t->sync ? 2u : 0u));

    uint32_t i = mirror_count;
    mirror[i % MIRROR_LEN] = *t;
    mirror_count = i + 1;

    bool go = functest_watch(t);
    const functest_state_t *f = functest_state();
    s_test_case = f->test_case;
    s_trapped = f->trapped ? 1u : 0u;
    s_trap_addr = f->trap_addr;
    return go;
}

// Published after every trial. Runs on core 1; core 0 reads the snapshot.
static void ret_report(uint32_t us, bool survived) {
    s_ret_last_ms = us;   // microseconds since 2026-07-31
    s_ret_last_ok = survived ? 1u : 0u;
    s_ret_seq++;
}

// A scan can take minutes, during which core 1 is not reading commands. Peek
// at the queue between trials so the page's stop button still works.
static bool ret_abort(void) {
    cmd_t c;
    if (queue_try_peek(&cmd_q, &c) && c.op == CMD_STOP) {
        queue_try_remove(&cmd_q, &c);
        return true;
    }
    return false;
}

static void __not_in_flash_func(core1_main)(void) {
    // Required before core 0 may write flash. Erasing turns XIP off, so this
    // core has to be parked somewhere that is not flash; without registering,
    // flash_safe_execute() refuses and every settings/image save fails.
    //
    // Note what being parked costs: a sector erase takes tens of milliseconds
    // and the worst dynamic node holds charge for about 1.1 ms (measured, board
    // #1). A flash write therefore DESTROYS the 6502's state. Stop the CPU and
    // reset it afterwards -- never save while a program is running.
    multicore_lockout_victim_init();

    bool run = false;
    for (;;) {
        cmd_t c;
        while (queue_try_remove(&cmd_q, &c)) {
            switch (c.op) {
            case CMD_RET:
                s_ret_busy = 1; s_ret_verdict = 0; s_ret_seq = 0;
                run = false; s_running = false;
                retention_load_image();
                ret_report(c.arg, retention_trial(c.arg));
                s_ret_good = s_ret_last_ok ? c.arg : 0;
                s_ret_bad = s_ret_last_ok ? 0 : c.arg;
                s_ret_verdict = (uint8_t)(RET_SCAN_BOUNDED + 1);
                s_ret_busy = 0;
                break;
            case CMD_RETSCAN: {
                s_ret_busy = 1; s_ret_verdict = 0; s_ret_seq = 0;
                run = false; s_running = false;
                uint32_t g = 0, b = 0;
                retention_scan_t r = retention_scan(c.arg ? c.arg : RET_SCAN_DEFAULT_LIMIT_US,
                                                    ret_report, ret_abort, &g, &b);
                s_ret_good = g; s_ret_bad = b;
                s_ret_verdict = (uint8_t)(r + 1);   // 0 stays "not run yet"
                s_ret_busy = 0;
                break;
            }
            case CMD_RUN: functest_clear(); run = true; break;
            case CMD_STOP: run = false; break;
            case CMD_RESET: run = false; bus_reset_sequence(); break;
            case CMD_STEP: run = false; bus_step_instruction(64); break;
            case CMD_CLOCK: bus_set_half_period_us(c.arg); s_half = c.arg; break;
            case CMD_FT:
                if (c.arg) functest_enable(FUNCTEST_CASE_ADDR_DEFAULT);
                else functest_disable();
                s_ft_on = c.arg ? 1u : 0u;
                break;
            }
            s_running = run;
        }
        if (run) {
            bus_run(1000);              // chunked so commands stay responsive
            if (bus_aborted()) {        // watcher saw a self-loop
                run = false;
                s_running = false;
            }
        } else {
            sleep_us(200);
        }
    }
}

static void push(uint8_t op, uint32_t arg) {
    cmd_t c = {op, arg};
    queue_try_add(&cmd_q, &c);
}


// ---- WiFi provisioning ----------------------------------------------------
//
// Credentials live in flash, not in the build. With none stored (or if the
// stored ones fail) the Pico raises its own open access point and serves a
// setup page; a phone joining it is pushed at that page by the DNS hijack in
// common/netsrv.c. Pick a network, type the password, save, reboot.
//
// The page is served FROM the Pico, deliberately. Hosting it elsewhere is
// impossible rather than merely undesirable: GitHub Pages is HTTPS, and a
// HTTPS page may not call an http:// address on a private network -- browsers
// block it as mixed content and no CORS header changes that. And in AP mode
// there is no internet at all, which is exactly when the page is needed.

#define AP_SSID "discrete6502-setup"
#define MAX_SCAN 16

static bool ap_mode;
static absolute_time_t s_reboot_at;  // nil until /wifi/save succeeds
static struct {
    char ssid[33];
    int16_t rssi;
    uint8_t auth;
} scan_res[MAX_SCAN];
static volatile uint8_t scan_n;
static volatile bool scan_busy;

static int scan_cb(void *env, const cyw43_ev_scan_result_t *r) {
    (void)env;
    if (!r || !r->ssid_len) return 0;
    char ssid[33];
    size_t n = r->ssid_len < 32 ? r->ssid_len : 32;
    memcpy(ssid, r->ssid, n);
    ssid[n] = 0;
    for (uint8_t i = 0; i < scan_n; i++)          // one row per network
        if (!strcmp(scan_res[i].ssid, ssid)) {
            if (r->rssi > scan_res[i].rssi) scan_res[i].rssi = r->rssi;
            return 0;
        }
    if (scan_n >= MAX_SCAN) return 0;
    strcpy(scan_res[scan_n].ssid, ssid);
    scan_res[scan_n].rssi = r->rssi;
    scan_res[scan_n].auth = r->auth_mode;
    scan_n++;
    return 0;
}

static void scan_start(void) {
    if (scan_busy) return;
    scan_n = 0;
    cyw43_wifi_scan_options_t o = {0};
    if (cyw43_wifi_scan(&cyw43_state, &o, NULL, scan_cb) == 0) scan_busy = true;
}

static void scan_poll(void) {
    if (scan_busy && !cyw43_wifi_scan_active(&cyw43_state)) scan_busy = false;
}

// %XX and + decoding, in place. Query strings carry passwords, and a password
// with a space or a '#' in it is otherwise silently mangled.
static void url_decode(char *s) {
    char *w = s;
    for (; *s; s++) {
        if (*s == '+') *w++ = ' ';
        else if (*s == '%' && s[1] && s[2]) {
            char h[3] = {s[1], s[2], 0};
            *w++ = (char)strtol(h, NULL, 16);
            s += 2;
        } else *w++ = *s;
    }
    *w = 0;
}

static uint32_t auth_for(const char *pass) {
    return pass[0] ? CYW43_AUTH_WPA2_AES_PSK : CYW43_AUTH_OPEN;
}

// Two attempts: an access point that is merely slow to answer should not push
// a correctly-provisioned board into setup mode.
static bool try_sta(void) {
    const settings_t *st = settings();
    if (!st->wifi_ssid[0]) return false;
    cyw43_arch_enable_sta_mode();
    for (int i = 0; i < 2; i++) {
        printf("[wifi] connecting to %s (attempt %d)\n", st->wifi_ssid, i + 1);
        if (!cyw43_arch_wifi_connect_timeout_ms(st->wifi_ssid, st->wifi_pass,
                                                auth_for(st->wifi_pass), 20000))
            return true;
    }
    return false;
}

static void start_ap(void) {
    ap_mode = true;
    cyw43_arch_enable_ap_mode(AP_SSID, NULL, CYW43_AUTH_OPEN);

    ip4_addr_t ip, mask;
    IP4_ADDR(&ip, 192, 168, 4, 1);
    IP4_ADDR(&mask, 255, 255, 255, 0);
    struct netif *nif = &cyw43_state.netif[CYW43_ITF_AP];
    netif_set_addr(nif, &ip, &mask, &ip);

    if (!dhcpsrv_start(&ip, &mask)) printf("[wifi] DHCP server failed\n");
    if (!dnssrv_start(&ip)) printf("[wifi] DNS server failed\n");
    printf("[wifi] setup mode: join \"%s\", then http://192.168.4.1/\n", AP_SSID);
    scan_start();
}

static const char PORTAL_HTML[] =
    "<!doctype html><meta charset=utf-8><title>discrete6502 setup</title>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<style>body{font:16px system-ui;margin:0;padding:18px;background:#111;color:#eee}"
    "h1{font-size:1.2rem}input,button{font:inherit;width:100%;padding:10px;margin:5px 0;"
    "background:#222;color:#eee;border:1px solid #444;border-radius:5px}"
    "button{background:#2a5;color:#fff;border:0;font-weight:600}"
    "li{list-style:none;padding:9px;border-bottom:1px solid #333;cursor:pointer}"
    "ul{padding:0;margin:8px 0}small{color:#999}</style>"
    "<h1>discrete6502 &mdash; WiFi setup</h1>"
    "<p><small>Pick a network, or type its name.</small></p>"
    "<ul id=l><li>scanning&hellip;</li></ul>"
    "<input id=s placeholder='network name'>"
    "<input id=p type=password placeholder='password (blank if open)'>"
    "<button onclick=save()>Save and reboot</button>"
    "<p id=m><small></small></p>"
    "<script>"
    "function go(){fetch('/wifi/scan').then(r=>r.json()).then(j=>{"
    "if(j.busy){setTimeout(go,900);return}"
    "document.getElementById('l').innerHTML=j.nets.map(n=>"
    "'<li onclick=\"pick(this)\" data-s=\"'+n.ssid+'\">'+n.ssid+' <small>'+n.rssi+' dBm'"
    "+(n.open?' &middot; open':'')+'</small></li>').join('')||'<li>none found</li>'})}"
    "function pick(e){document.getElementById('s').value=e.dataset.s}"
    "function save(){var s=document.getElementById('s').value,p=document.getElementById('p').value;"
    "if(!s){alert('pick a network');return}"
    "fetch('/wifi/save?ssid='+encodeURIComponent(s)+'&pass='+encodeURIComponent(p))"
    ".then(r=>r.text()).then(t=>{document.getElementById('m').innerHTML='<small>'+t+'</small>'})}"
    "go();</script>";

static void wifi_scan_json(char *b, size_t n) {
    size_t k = (size_t)snprintf(b, n, "{\"busy\":%s,\"nets\":[", scan_busy ? "true" : "false");
    for (uint8_t i = 0; i < scan_n && k < n - 90; i++)
        k += (size_t)snprintf(b + k, n - k, "%s{\"ssid\":\"%s\",\"rssi\":%d,\"open\":%s}",
                              i ? "," : "", scan_res[i].ssid, scan_res[i].rssi,
                              scan_res[i].auth == 0 ? "true" : "false");
    snprintf(b + k, n - k, "]}");
}

// ---- core 0: HTTP ---------------------------------------------------------

typedef enum { ST_REQ, ST_HDR, ST_BODY, ST_SEND } hstate_t;

typedef struct {
    bool used;
    hstate_t state;
    char line[300];
    uint16_t line_n;
    char path[120];
    bool is_post;
    uint32_t body_left;
    bool loading;
    ihex_stats_t hx;
    const char *out;  // remaining response
    uint32_t out_len;
    char buf[1400];   // dynamic responses live here for the connection's life
} conn_t;

static conn_t conns[MAX_CONN];
static char scratch[1200];

static conn_t *conn_alloc(void) {
    for (int i = 0; i < MAX_CONN; i++)
        if (!conns[i].used) {
            memset(&conns[i], 0, sizeof conns[i]);
            conns[i].used = true;
            return &conns[i];
        }
    return NULL;
}

static void pump(struct tcp_pcb *pcb, conn_t *c) {
    while (c->out_len) {
        uint16_t room = tcp_sndbuf(pcb);
        if (!room) return;
        uint16_t n = c->out_len < room ? (uint16_t)c->out_len : room;
        // No copy: both sources (flash page, per-connection buf) stay valid
        // until the connection is freed, which happens after everything is
        // acked.
        if (tcp_write(pcb, c->out, n, 0) != ERR_OK) return;
        c->out += n;
        c->out_len -= n;
    }
    tcp_output(pcb);
}

static void reply(struct tcp_pcb *pcb, conn_t *c, const char *status, const char *ctype,
                  const char *body) {
    int n = snprintf(c->buf, sizeof c->buf,
                     "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %u\r\n"
                     "Connection: close\r\n\r\n%s",
                     status, ctype, (unsigned)strlen(body), body);
    if (n < 0) n = 0;
    c->out = c->buf;
    c->out_len = (uint32_t)n < sizeof c->buf ? (uint32_t)n : sizeof c->buf - 1;
    c->state = ST_SEND;
    pump(pcb, c);
}

static const char *qparam(const char *path, const char *key, char *out, size_t cap) {
    const char *q = strchr(path, '?');
    if (!q) return NULL;
    size_t kl = strlen(key);
    for (const char *p = q + 1; p && *p;) {
        if (!strncmp(p, key, kl) && p[kl] == '=') {
            const char *v = p + kl + 1;
            size_t i = 0;
            while (v[i] && v[i] != '&' && i < cap - 1) { out[i] = v[i]; i++; }
            out[i] = 0;
            return out;
        }
        p = strchr(p, '&');
        if (p) p++;
    }
    return NULL;
}

static void status_json(char *b, size_t cap) {
    snprintf(b, cap,
             "{\"run\":%u,\"cyc\":%lu,\"half\":%lu,\"a\":%u,\"d\":%u,\"f\":%u,"
             "\"ft\":%u,\"tc\":%u,\"tr\":%u,\"ta\":%u,"
             "\"rb\":%u,\"rv\":%u,\"rs\":%lu,\"rms\":%lu,\"rok\":%u,"
             "\"rg\":%lu,\"rbad\":%lu,\"img\":%lu,\"ip\":\"%s\"}",
             s_running ? 1u : 0u, (unsigned long)s_cycle, (unsigned long)s_half, s_addr,
             s_data, s_flags, s_ft_on, s_test_case, s_trapped, s_trap_addr,
             s_ret_busy, s_ret_verdict, (unsigned long)s_ret_seq,
             (unsigned long)s_ret_last_ms, s_ret_last_ok,
             (unsigned long)s_ret_good, (unsigned long)s_ret_bad,
             (unsigned long)settings_program_len(),
             ip4addr_ntoa(netif_ip4_addr(netif_default)));
}

static void trace_json(char *b, size_t cap, uint32_t want) {
    if (want > MIRROR_LEN) want = MIRROR_LEN;
    uint32_t total = mirror_count;
    if (want > total) want = total;
    size_t n = (size_t)snprintf(b, cap, "{\"t\":[");
    for (uint32_t i = 0; i < want && n < cap - 40; i++) {
        const bus_trace_t *t = &mirror[(total - want + i) % MIRROR_LEN];
        n += (size_t)snprintf(b + n, cap - n, "%s[%lu,%u,%u,%u]", i ? "," : "",
                              (unsigned long)t->cycle, t->addr, t->data,
                              (unsigned)((t->rw_read ? 1u : 0u) | (t->sync ? 2u : 0u)));
    }
    snprintf(b + n, cap - n, "]}");
}

static void do_cmd(struct tcp_pcb *pcb, conn_t *c) {
    char op[16], v[16];
    if (!qparam(c->path, "op", op, sizeof op)) {
        reply(pcb, c, "400 Bad Request", "application/json", "{\"err\":\"no op\"}");
        return;
    }
    uint32_t val = qparam(c->path, "v", v, sizeof v) ? (uint32_t)strtoul(v, NULL, 0) : 0;

    if (!strcmp(op, "run")) push(CMD_RUN, 0);
    else if (!strcmp(op, "stop")) push(CMD_STOP, 0);
    else if (!strcmp(op, "reset")) push(CMD_RESET, 0);
    else if (!strcmp(op, "step")) push(CMD_STEP, 0);
    else if (!strcmp(op, "clock")) push(CMD_CLOCK, val ? val : 1);
    else if (!strcmp(op, "ft")) push(CMD_FT, val);
    else if (!strcmp(op, "ret") || !strcmp(op, "retscan")) {
        if (s_ret_busy) {
            reply(pcb, c, "409 Conflict", "application/json",
                  "{\"err\":\"a retention test is already running\"}");
            return;
        }
        push(op[3] == 's' ? CMD_RETSCAN : CMD_RET, val);
    }
    else if (!strcmp(op, "store") || !strcmp(op, "forget")) {
        // Flash writes park core 1 for tens of milliseconds against a ~1.1 ms
        // retention floor, so the CPU's state cannot survive one. Refuse rather
        // than silently corrupting a run that looked fine a moment ago.
        if (s_running) {
            reply(pcb, c, "409 Conflict", "application/json", "{\"err\":\"stop first\"}");
            return;
        }
        bool ok = (op[0] == 's') ? settings_program_save(bus_mem(), BUS_MEM_SIZE)
                                 : settings_program_clear();
        if (!ok) {
            reply(pcb, c, "500 Server Error", "application/json",
                  "{\"err\":\"flash write refused\"}");
            return;
        }
        // The image is gone from RAM as far as the CPU is concerned -- reload
        // and reset so what runs next is what is now stored.
        if (op[0] == 'f') retention_load_image();
        push(CMD_RESET, 0);
    }
    else if (!strcmp(op, "vector")) {
        // The functional test's own RES vector points at res_trap; it must be
        // repointed at code_segment ($0400) to start. Memory is shared, so
        // only touch it while core 1 is idle.
        if (s_running) {
            reply(pcb, c, "409 Conflict", "application/json", "{\"err\":\"stop first\"}");
            return;
        }
        bus_mem()[0x3FFC] = 0x00;
        bus_mem()[0x3FFD] = 0x04;
    } else {
        reply(pcb, c, "400 Bad Request", "application/json", "{\"err\":\"bad op\"}");
        return;
    }
    reply(pcb, c, "200 OK", "application/json", "{\"ok\":1}");
}

static void dispatch(struct tcp_pcb *pcb, conn_t *c) {
    if (!strncmp(c->path, "/status", 7)) {
        status_json(scratch, sizeof scratch);
        reply(pcb, c, "200 OK", "application/json", scratch);
    } else if (!strncmp(c->path, "/trace", 6)) {
        char v[8];
        uint32_t n = qparam(c->path, "n", v, sizeof v) ? (uint32_t)strtoul(v, NULL, 10) : 16;
        trace_json(scratch, sizeof scratch, n);
        reply(pcb, c, "200 OK", "application/json", scratch);
    } else if (!strncmp(c->path, "/cmd", 4)) {
        do_cmd(pcb, c);
    } else if (!strncmp(c->path, "/wifi/scan", 10)) {
        scan_poll();
        if (!scan_busy && scan_n == 0) scan_start();
        wifi_scan_json(scratch, sizeof scratch);
        reply(pcb, c, "200 OK", "application/json", scratch);
    } else if (!strncmp(c->path, "/wifi/save", 10)) {
        char ss[SETTINGS_SSID_MAX], pw[SETTINGS_PASS_MAX];
        if (!qparam(c->path, "ssid", ss, sizeof ss) || !ss[0]) {
            reply(pcb, c, "400 Bad Request", "text/plain", "need ssid");
        } else {
            if (!qparam(c->path, "pass", pw, sizeof pw)) pw[0] = 0;
            url_decode(ss);
            url_decode(pw);
            // Stop the CPU first. A flash erase parks core 1 for tens of
            // milliseconds and the worst dynamic node holds charge for about
            // 1.1 ms, so the 6502's state does not survive this either way --
            // but a program left mid-run would look like it crashed.
            push(CMD_STOP, 0);
            sleep_ms(20);
            strncpy(settings()->wifi_ssid, ss, SETTINGS_SSID_MAX - 1);
            strncpy(settings()->wifi_pass, pw, SETTINGS_PASS_MAX - 1);
            if (settings_save()) {
                reply(pcb, c, "200 OK", "text/plain",
                      "saved. rebooting -- rejoin your own network and find the board there.");
                s_reboot_at = make_timeout_time_ms(1200);   // let the reply flush
            } else {
                reply(pcb, c, "500 Server Error", "text/plain", "flash write refused");
            }
        }
    } else if (!strcmp(c->path, "/") || !strncmp(c->path, "/index", 6)) {
        if (ap_mode) {
            reply(pcb, c, "200 OK", "text/html", PORTAL_HTML);
            return;
        }
        c->out = PAGE_HTML;                       // already includes its headers
        c->out_len = (uint32_t)(sizeof PAGE_HTML - 1);
        c->state = ST_SEND;
        pump(pcb, c);
    } else if (ap_mode) {
        reply(pcb, c, "200 OK", "text/html", PORTAL_HTML);
    } else {
        reply(pcb, c, "404 Not Found", "text/plain", "no");
    }
}

static void finish_load(struct tcp_pcb *pcb, conn_t *c) {
    uint16_t vec = (uint16_t)(bus_mem()[0x3FFC] | (bus_mem()[0x3FFD] << 8));
    snprintf(scratch, sizeof scratch,
             "{\"ok\":1,\"bytes\":%lu,\"rec\":%lu,\"bad\":%lu,\"vec\":%u}",
             (unsigned long)c->hx.bytes, (unsigned long)c->hx.records,
             (unsigned long)c->hx.bad, vec);
    printf("[wifi] loaded %lu bytes, %lu bad records, vector $%04X\n",
           (unsigned long)c->hx.bytes, (unsigned long)c->hx.bad, vec);
    reply(pcb, c, "200 OK", "application/json", scratch);
}

// Feed one received byte through the request state machine.
static void feed(struct tcp_pcb *pcb, conn_t *c, char ch) {
    if (c->state == ST_SEND) return;

    if (c->state == ST_BODY) {
        if (c->body_left) c->body_left--;
        if (ch == '\n' || ch == '\r') {
            if (c->line_n) {
                c->line[c->line_n] = 0;
                ihex_line(&c->hx, c->line, bus_mem(), BUS_MEM_SIZE - 1);
                c->line_n = 0;
            }
        } else if (c->line_n < sizeof c->line - 1) {
            c->line[c->line_n++] = ch;
        }
        if (!c->body_left) finish_load(pcb, c);
        return;
    }

    if (ch == '\r') return;
    if (ch != '\n') {
        if (c->line_n < sizeof c->line - 1) c->line[c->line_n++] = ch;
        return;
    }
    c->line[c->line_n] = 0;

    if (c->state == ST_REQ) {
        c->is_post = !strncmp(c->line, "POST ", 5);
        const char *sp = strchr(c->line, ' ');
        if (sp) {
            const char *e = strchr(sp + 1, ' ');
            size_t n = e ? (size_t)(e - sp - 1) : strlen(sp + 1);
            if (n >= sizeof c->path) n = sizeof c->path - 1;
            memcpy(c->path, sp + 1, n);
            c->path[n] = 0;
        }
        c->state = ST_HDR;
    } else if (c->line_n == 0) {
        // end of headers
        if (c->is_post && !strncmp(c->path, "/load", 5)) {
            if (s_running) {
                reply(pcb, c, "409 Conflict", "application/json",
                      "{\"err\":\"stop the CPU before loading\"}");
                return;
            }
            ihex_begin(&c->hx);
            c->loading = true;
            c->state = ST_BODY;
            c->line_n = 0;
            if (!c->body_left) finish_load(pcb, c);
        } else {
            dispatch(pcb, c);
        }
        return;
    } else if (!strncasecmp(c->line, "Content-Length:", 15)) {
        c->body_left = (uint32_t)strtoul(c->line + 15, NULL, 10);
    }
    c->line_n = 0;
}

static void conn_close(struct tcp_pcb *pcb, conn_t *c) {
    if (c) c->used = false;
    tcp_arg(pcb, NULL);
    tcp_recv(pcb, NULL);
    tcp_sent(pcb, NULL);
    tcp_err(pcb, NULL);
    tcp_close(pcb);
}

static err_t on_sent(void *arg, struct tcp_pcb *pcb, u16_t len) {
    (void)len;
    conn_t *c = arg;
    if (!c) return ERR_OK;
    if (c->out_len) pump(pcb, c);
    else if (c->state == ST_SEND) conn_close(pcb, c);
    return ERR_OK;
}

static err_t on_recv(void *arg, struct tcp_pcb *pcb, struct pbuf *p, err_t err) {
    conn_t *c = arg;
    if (err != ERR_OK || !p) {
        if (c && c->loading && c->state == ST_BODY) finish_load(pcb, c);
        else conn_close(pcb, c);
        if (p) pbuf_free(p);
        return ERR_OK;
    }
    for (struct pbuf *q = p; q; q = q->next) {
        const char *d = q->payload;
        for (uint16_t i = 0; i < q->len; i++) feed(pcb, c, d[i]);
    }
    tcp_recved(pcb, p->tot_len);
    pbuf_free(p);
    return ERR_OK;
}

static void on_err(void *arg, err_t err) {
    (void)err;
    conn_t *c = arg;
    if (c) c->used = false;  // pcb is already gone
}

static err_t on_accept(void *arg, struct tcp_pcb *pcb, err_t err) {
    (void)arg;
    if (err != ERR_OK || !pcb) return ERR_VAL;
    conn_t *c = conn_alloc();
    if (!c) { tcp_abort(pcb); return ERR_ABRT; }
    tcp_arg(pcb, c);
    tcp_recv(pcb, on_recv);
    tcp_sent(pcb, on_sent);
    tcp_err(pcb, on_err);
    return ERR_OK;
}

// ---- boot -----------------------------------------------------------------

int main(void) {
    stdio_init_all();

    settings_load();
    bus_init(settings()->clk_open_drain);  // push-pull: no board pull-up on clk0
    bus_set_half_period_us(settings()->half_period_us);
    bus_set_watch(publish);
    functest_set_quiet(true);  // core 1 must never block on stdio
    // Prefer a stored boot image; fall back to the counter so there is always
    // something visible before any upload.
    if (!settings_program_load_into_ram()) retention_load_image();
    queue_init(&cmd_q, sizeof(cmd_t), 16);
    multicore_launch_core1(core1_main);

    if (cyw43_arch_init()) {
        printf("[wifi] cyw43 init failed\n");
        return 1;
    }
    // Seed flash from the build-time credentials once, if any were given and
    // nothing is stored. That is the only thing -DWIFI_SSID still does.
    if (!settings()->wifi_ssid[0] && WIFI_SSID[0]) {
        strncpy(settings()->wifi_ssid, WIFI_SSID, SETTINGS_SSID_MAX - 1);
        strncpy(settings()->wifi_pass, WIFI_PASSWORD, SETTINGS_PASS_MAX - 1);
        settings_save();
    }

    if (try_sta()) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 1);
        printf("[wifi] http://%s/\n", ip4addr_ntoa(netif_ip4_addr(netif_default)));
    } else {
        // No credentials, or they did not work. Raise the setup portal rather
        // than retrying forever with nobody able to tell it what to try.
        start_ap();
    }

    struct tcp_pcb *pcb = tcp_new_ip_type(IPADDR_TYPE_ANY);
    if (!pcb || tcp_bind(pcb, NULL, HTTP_PORT) != ERR_OK) {
        printf("[wifi] bind failed\n");
        return 1;
    }
    pcb = tcp_listen_with_backlog(pcb, MAX_CONN);
    tcp_accept(pcb, on_accept);

    for (;;) {
        cyw43_arch_poll();
        cyw43_arch_wait_for_work_until(make_timeout_time_ms(10));
        if (ap_mode) scan_poll();
        if (!is_nil_time(s_reboot_at) && absolute_time_diff_us(get_absolute_time(),
                                                               s_reboot_at) < 0) {
            printf("[wifi] rebooting to apply new credentials\n");
            watchdog_reboot(0, 0, 0);
        }
    }
}
