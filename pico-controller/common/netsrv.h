// The two servers a captive portal needs, written from the protocols rather
// than vendored, so nothing here carries a licence this repo has to reconcile.
//
// DHCP is mandatory: join an access point that hands out no address and the
// phone never gets one, so nothing can talk. DNS is what makes it a *captive*
// portal -- answering every lookup with our own address is what triggers the
// "Sign in to network" prompt, because the phone's connectivity probe gets us
// instead of the answer it expected.
//
// Both are deliberately minimal. They serve one access point on a bench for a
// few minutes at a time, not a network.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "lwip/ip_addr.h"

// Start handing out addresses in ip's /24, from .2 upward. `ip` is our own
// address and is offered as both router and DNS. Returns false if the socket
// could not be bound.
bool dhcpsrv_start(const ip4_addr_t *ip, const ip4_addr_t *mask);
void dhcpsrv_stop(void);

// Answer every A query with `ip`, whatever was asked for.
bool dnssrv_start(const ip4_addr_t *ip);
void dnssrv_stop(void);
