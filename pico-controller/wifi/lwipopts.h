// lwIP configuration for the discrete6502 wifi firmware.
// NO_SYS (bare-metal, no RTOS): the poll-mode cyw43_arch drives the stack
// from core 0's main loop, which is what keeps every lwIP call on one core.
#pragma once

#define NO_SYS 1
#define LWIP_SOCKET 0
#define LWIP_NETCONN 0

#define MEM_LIBC_MALLOC 0
#define MEM_ALIGNMENT 4
#define MEM_SIZE 4000
#define MEMP_NUM_TCP_SEG 32
#define MEMP_NUM_ARP_QUEUE 10
#define PBUF_POOL_SIZE 24

#define LWIP_ARP 1
#define LWIP_ETHERNET 1
#define LWIP_ICMP 1
#define LWIP_RAW 1
#define LWIP_IPV4 1
#define LWIP_IPV6 0
#define LWIP_TCP 1
#define LWIP_UDP 1
#define LWIP_DNS 1
#define LWIP_DHCP 1
#define LWIP_TCP_KEEPALIVE 1

#define TCP_MSS 1460
#define TCP_WND (8 * TCP_MSS)
#define TCP_SND_BUF (8 * TCP_MSS)
#define TCP_SND_QUEUELEN ((4 * (TCP_SND_BUF) + (TCP_MSS - 1)) / (TCP_MSS))

// mDNS, so the board answers to discrete6502.local instead of an address you
// have to hunt for in the router's admin page. Needs IGMP (it is multicast) and
// one netif client-data slot for the responder's per-interface state.
#define LWIP_IGMP 1
#define LWIP_MDNS_RESPONDER 1
#define LWIP_NUM_NETIF_CLIENT_DATA 1
#define MDNS_MAX_SERVICES 1
// DHCP client, our DHCP server, our DNS hijack and mDNS can all want one at
// once; the default of 4 is uncomfortably close.
#define MEMP_NUM_UDP_PCB 8

#define LWIP_NETIF_STATUS_CALLBACK 1
#define LWIP_NETIF_LINK_CALLBACK 1
#define LWIP_NETIF_HOSTNAME 1
#define DHCP_DOES_ARP_CHECK 0
#define LWIP_DHCP_DOES_ACD_CHECK 0
