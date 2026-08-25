#include "netsrv.h"

#include <string.h>

#include "lwip/udp.h"

// ---------------------------------------------------------------- DHCP -----
//
// Enough of RFC 2131 to get a phone onto the access point: DISCOVER -> OFFER,
// REQUEST -> ACK, and the four options a client actually needs (mask, router,
// DNS, lease). Everything else is ignored rather than answered wrongly.

#define DHCP_SERVER_PORT 67
#define DHCP_CLIENT_PORT 68
#define DHCP_MAGIC 0x63825363u

#define DHCPDISCOVER 1
#define DHCPOFFER 2
#define DHCPREQUEST 3
#define DHCPACK 5

#define OPT_PAD 0
#define OPT_MASK 1
#define OPT_ROUTER 3
#define OPT_DNS 6
#define OPT_REQ_IP 50
#define OPT_LEASE 51
#define OPT_MSG_TYPE 53
#define OPT_SERVER_ID 54
#define OPT_END 255

#define LEASES 8
#define LEASE_SECS 3600

typedef struct {
    uint8_t op, htype, hlen, hops;
    uint32_t xid;
    uint16_t secs, flags;
    uint8_t ciaddr[4], yiaddr[4], siaddr[4], giaddr[4];
    uint8_t chaddr[16];
    uint8_t sname[64], file[128];
    uint8_t options[312];
} dhcp_msg_t;

static struct {
    struct udp_pcb *pcb;
    ip4_addr_t ip, mask;
    uint8_t mac[LEASES][6];
    bool used[LEASES];
} dh;

static struct udp_pcb *dns_pcb;
static ip4_addr_t dns_ip;

// Find one option in the variable-length tail. Returns its length, or 0.
static uint8_t opt_find(const uint8_t *o, size_t n, uint8_t want, const uint8_t **val) {
    size_t i = 4;  // skip the magic cookie
    while (i + 1 < n) {
        uint8_t code = o[i];
        if (code == OPT_END) break;
        if (code == OPT_PAD) { i++; continue; }
        uint8_t len = o[i + 1];
        if (i + 2 + len > n) break;
        if (code == want) { *val = &o[i + 2]; return len; }
        i += 2 + len;
    }
    return 0;
}

static uint8_t *opt_put(uint8_t *p, uint8_t code, const void *v, uint8_t len) {
    *p++ = code;
    *p++ = len;
    memcpy(p, v, len);
    return p + len;
}

// One lease per MAC, reused on repeat requests so a reconnecting phone keeps
// its address instead of exhausting the pool.
static int lease_for(const uint8_t *mac) {
    for (int i = 0; i < LEASES; i++)
        if (dh.used[i] && !memcmp(dh.mac[i], mac, 6)) return i;
    for (int i = 0; i < LEASES; i++)
        if (!dh.used[i]) {
            memcpy(dh.mac[i], mac, 6);
            dh.used[i] = true;
            return i;
        }
    return -1;
}

static void dhcp_recv(void *arg, struct udp_pcb *pcb, struct pbuf *p,
                      const ip_addr_t *addr, u16_t port) {
    (void)arg; (void)addr; (void)port;
    if (!p) return;
    dhcp_msg_t m;
    if (p->tot_len < 240 || pbuf_copy_partial(p, &m, sizeof m, 0) < 240) goto done;

    const uint8_t *v;
    if (opt_find(m.options, sizeof m.options, OPT_MSG_TYPE, &v) != 1) goto done;
    uint8_t type = v[0];
    if (type != DHCPDISCOVER && type != DHCPREQUEST) goto done;

    int slot = lease_for(m.chaddr);
    if (slot < 0) goto done;

    // Build the reply in place: most of the request is echoed back.
    m.op = 2;  // BOOTREPLY
    memcpy(m.yiaddr, &dh.ip.addr, 4);
    m.yiaddr[3] = (uint8_t)(2 + slot);  // .2 upward; we keep .1
    memcpy(m.siaddr, &dh.ip.addr, 4);
    memset(m.options, 0, sizeof m.options);

    uint8_t *o = m.options;
    uint32_t magic = PP_HTONL(DHCP_MAGIC);
    memcpy(o, &magic, 4);
    o += 4;
    uint8_t reply_type = (type == DHCPDISCOVER) ? DHCPOFFER : DHCPACK;
    o = opt_put(o, OPT_MSG_TYPE, &reply_type, 1);
    o = opt_put(o, OPT_SERVER_ID, &dh.ip.addr, 4);
    o = opt_put(o, OPT_MASK, &dh.mask.addr, 4);
    o = opt_put(o, OPT_ROUTER, &dh.ip.addr, 4);
    o = opt_put(o, OPT_DNS, &dh.ip.addr, 4);   // us: that is the portal hijack
    uint32_t lease = PP_HTONL(LEASE_SECS);
    o = opt_put(o, OPT_LEASE, &lease, 4);
    *o++ = OPT_END;

    size_t len = (size_t)(o - (uint8_t *)&m);
    struct pbuf *q = pbuf_alloc(PBUF_TRANSPORT, (u16_t)len, PBUF_RAM);
    if (q) {
        memcpy(q->payload, &m, len);
        // Broadcast: the client has no address yet, so it cannot be unicast to.
        udp_sendto(pcb, q, IP_ADDR_BROADCAST, DHCP_CLIENT_PORT);
        pbuf_free(q);
    }
done:
    pbuf_free(p);
}

bool dhcpsrv_start(const ip4_addr_t *ip, const ip4_addr_t *mask) {
    dhcpsrv_stop();
    dh.ip = *ip;
    dh.mask = *mask;
    memset(dh.used, 0, sizeof dh.used);
    dh.pcb = udp_new();
    if (!dh.pcb) return false;
    if (udp_bind(dh.pcb, IP_ANY_TYPE, DHCP_SERVER_PORT) != ERR_OK) {
        udp_remove(dh.pcb);
        dh.pcb = NULL;
        return false;
    }
    udp_recv(dh.pcb, dhcp_recv, NULL);
    return true;
}

void dhcpsrv_stop(void) {
    if (dh.pcb) { udp_remove(dh.pcb); dh.pcb = NULL; }
}

// ----------------------------------------------------------------- DNS -----
//
// Every A query gets our own address, whatever was asked for. That is the whole
// trick: the phone's connectivity check resolves to us, gets the portal page
// instead of its expected 204, and raises "Sign in to network".

static void dns_recv(void *arg, struct udp_pcb *pcb, struct pbuf *p,
                     const ip_addr_t *addr, u16_t port) {
    (void)arg;
    if (!p) return;
    uint8_t q[512];
    u16_t n = pbuf_copy_partial(p, q, sizeof q, 0);
    if (n < 12) goto done;
    if (q[2] & 0x80) goto done;                       // already a response
    uint16_t qdcount = (uint16_t)((q[4] << 8) | q[5]);
    if (qdcount != 1) goto done;

    // Walk the single question's name to find where it ends.
    size_t i = 12;
    while (i < n && q[i]) {
        if ((q[i] & 0xC0) == 0xC0) goto done;         // compression: not our problem
        i += q[i] + 1;
    }
    if (i + 5 > n) goto done;
    size_t qend = i + 5;                              // 0 terminator + type + class
    uint16_t qtype = (uint16_t)((q[qend - 4] << 8) | q[qend - 3]);
    if (qtype != 1) goto done;                        // A records only

    if (qend + 16 > sizeof q) goto done;
    uint8_t *r = q + qend;
    q[2] = 0x84;                                      // response, authoritative
    q[3] = 0x00;
    q[6] = 0; q[7] = 1;                               // one answer
    q[8] = 0; q[9] = 0; q[10] = 0; q[11] = 0;         // no NS, no AR
    *r++ = 0xC0; *r++ = 0x0C;                         // pointer back to the question
    *r++ = 0; *r++ = 1;                               // type A
    *r++ = 0; *r++ = 1;                               // class IN
    *r++ = 0; *r++ = 0; *r++ = 0; *r++ = 30;          // TTL 30 s
    *r++ = 0; *r++ = 4;                               // rdlength
    memcpy(r, &dns_ip.addr, 4);
    r += 4;

    size_t len = (size_t)(r - q);
    struct pbuf *out = pbuf_alloc(PBUF_TRANSPORT, (u16_t)len, PBUF_RAM);
    if (out) {
        memcpy(out->payload, q, len);
        udp_sendto(pcb, out, addr, port);
        pbuf_free(out);
    }
done:
    pbuf_free(p);
}

bool dnssrv_start(const ip4_addr_t *ip) {
    dnssrv_stop();
    dns_ip = *ip;
    dns_pcb = udp_new();
    if (!dns_pcb) return false;
    if (udp_bind(dns_pcb, IP_ANY_TYPE, 53) != ERR_OK) {
        udp_remove(dns_pcb);
        dns_pcb = NULL;
        return false;
    }
    udp_recv(dns_pcb, dns_recv, NULL);
    return true;
}

void dnssrv_stop(void) {
    if (dns_pcb) { udp_remove(dns_pcb); dns_pcb = NULL; }
}
