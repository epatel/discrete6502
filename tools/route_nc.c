/* PathFinder-style negotiated-congestion signal router core.
 *
 * Driven by tools/route_nc.py (which extracts the obstacle grid + pads from
 * the KiCad board and emits the resulting paths back). Grid semantics match
 * tools/route_signals.py v13: G=0.3mm, adjacent cells = exactly legal
 * 0.15/0.15 spacing, F.Cu(0) prefers horizontal / B.Cu(1) vertical,
 * via = 3x3 usage stamp on both layers + static ring check.
 *
 * Negotiation: nets route THROUGH each other's cells but pay a present-
 * sharing penalty (use * pres) plus an accumulated history cost; after each
 * iteration every conflicted net (shares a cell, or failed) is ripped up and
 * rerouted with pres increased and hist bumped on overused cells. Converges
 * when no cell is used by more than one net.
 *
 * Input (little-endian int32 unless noted):
 *   W H nnets
 *   blk[2*NL] as uint8 (layer-major, idx = L*NL + cy*W + cx)
 *   per net: npads
 *     per pad: center_idx, ngoal, goal_idx..., ncarve, carve_idx...
 * Output:
 *   nnets
 *   per net: nrec (=npads-1)
 *     per rec: pad_index, plen, path_idx...   (plen=0 -> failed)
 *
 * Build: cc -O3 -o route_nc route_nc.c
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

static int W, H, NL, NN2, nnets;
static uint8_t *blk, *use8;
static uint32_t *hist;
static uint32_t *vis, *closedv, *treev, *occv;
static int64_t *dist_;
static int32_t *par;
static uint32_t gen, tstamp, ostamp;
static int64_t pres = 10;
static int HINC = 30;          /* env ROUTE_NC_HINC */
static int64_t PRES_MAX = 2000; /* env ROUTE_NC_PRESMAX */
static int VIACOST = 50;       /* env ROUTE_NC_VIACOST */
static int SCALE = 1;          /* env ROUTE_NC_SCALE: 2 = fine grid (G halved), body/halo stamping */
static int NLAY = 2;           /* env ROUTE_NC_LAYERS: routing layers (2 or 4) */
static long EXPCAP = 4000000L; /* env ROUTE_NC_CAP */
static uint32_t *bodyv;
static int ringoff[80][2], nring;
#define HMAX 100000000

typedef struct { int n, cap; int32_t *v; } Vec;
static void vpush(Vec *a, int32_t x) {
    if (a->n == a->cap) {
        a->cap = a->cap ? a->cap * 2 : 16;
        a->v = (int32_t *)realloc(a->v, (size_t)a->cap * 4);
    }
    a->v[a->n++] = x;
}
static void vclear(Vec *a) { a->n = 0; }

typedef struct { int32_t center; Vec goal, carve; } Pad;
typedef struct { int npads; Pad *pads; Vec *paths; Vec occ, occ_h, occ_u; int fails; int conflicted; } Net;
static Net *nets;
static int *order, *rem;

/* ---- binary heap (lazy deletion) ---- */
static int64_t *hF; static int32_t *hI; static int hn, hcap;
static void hpush(int64_t f, int32_t i) {
    if (hn == hcap) {
        hcap = hcap ? hcap * 2 : (1 << 16);
        hF = (int64_t *)realloc(hF, (size_t)hcap * 8);
        hI = (int32_t *)realloc(hI, (size_t)hcap * 4);
    }
    int k = hn++;
    hF[k] = f; hI[k] = i;
    while (k) {
        int p = (k - 1) >> 1;
        if (hF[p] <= hF[k]) break;
        int64_t tf = hF[p]; hF[p] = hF[k]; hF[k] = tf;
        int32_t ti = hI[p]; hI[p] = hI[k]; hI[k] = ti;
        k = p;
    }
}
static int hpop(int64_t *f, int32_t *i) {
    if (!hn) return 0;
    *f = hF[0]; *i = hI[0];
    hn--;
    if (hn) {
        hF[0] = hF[hn]; hI[0] = hI[hn];
        int k = 0;
        for (;;) {
            int a = 2 * k + 1, b = a + 1, m = k;
            if (a < hn && hF[a] < hF[m]) m = a;
            if (b < hn && hF[b] < hF[m]) m = b;
            if (m == k) break;
            int64_t tf = hF[m]; hF[m] = hF[k]; hF[k] = tf;
            int32_t ti = hI[m]; hI[m] = hI[k]; hI[k] = ti;
            k = m;
        }
    }
    return 1;
}

/* ---- tree bbox (heuristic target) ---- */
static int bx0, by0, bx1, by1;
static int64_t hfun(int cx, int cy) {
    int dx = cx < bx0 ? bx0 - cx : (cx > bx1 ? cx - bx1 : 0);
    int dy = cy < by0 ? by0 - cy : (cy > by1 ? cy - by1 : 0);
    return 10LL * (dx + dy);
}
static void tree_add(int32_t idx) {
    treev[idx] = tstamp;
    int c = idx % NL, cx = c % W, cy = c / W;
    if (cx < bx0) bx0 = cx;
    if (cx > bx1) bx1 = cx;
    if (cy < by0) by0 = cy;
    if (cy > by1) by1 = cy;
}

static const int RING[8][2] = {{2,0},{-2,0},{0,2},{0,-2},{1,1},{-1,-1},{1,-1},{-1,1}};

static void reconstruct(int32_t end, Vec *out) {
    vclear(out);
    int32_t cur = end;
    while (cur != -1) { vpush(out, cur); cur = par[cur]; }
    for (int i = 0, j = out->n - 1; i < j; i++, j--) {
        int32_t t = out->v[i]; out->v[i] = out->v[j]; out->v[j] = t;
    }
}

/* multi-goal A* from a pad to the current net tree (treev==tstamp).
 * Goal check BEFORE blocked check -- tree copper is usage-stamped. */
static int astar(int32_t start, Vec *out) {
    if (treev[start] == tstamp) { vclear(out); vpush(out, start); return 1; }
    gen++;
    hn = 0;
    vis[start] = gen; dist_[start] = 0; par[start] = -1;
    int sc = start % NL;
    hpush(hfun(sc % W, sc / W), start);
    long expand = 0;
    int64_t f; int32_t idx;
    static const int DX[4] = {1,-1,0,0}, DY[4] = {0,0,1,-1};
    while (hpop(&f, &idx)) {
        if (closedv[idx] == gen) continue;
        closedv[idx] = gen;
        int64_t g = dist_[idx];
        int L = idx / NL, c = idx - L * NL, cx = c % W, cy = c / W;
        int prefH = (L % 2 == 0);  /* F,In3 horizontal; In2,B vertical */
        if (NLAY == 2) prefH = (L == 0);
        if (++expand > EXPCAP) return 0;
        for (int d = 0; d < 4; d++) {
            int nx = cx + DX[d], ny = cy + DY[d];
            if (nx < 0 || nx >= W || ny < 0 || ny >= H) continue;
            int32_t nc = ny * W + nx, nidx = L * NL + nc;
            int base = ((DX[d] && prefH) || (DY[d] && !prefH)) ? 10 : 14;
            int64_t ng = g + base + (int64_t)use8[nidx] * pres + hist[nidx];
            if (treev[nidx] == tstamp) {
                par[nidx] = idx;
                reconstruct(nidx, out);
                return 1;
            }
            if (blk[nidx]) continue;
            if (vis[nidx] == gen && dist_[nidx] <= ng) continue;
            vis[nidx] = gen; dist_[nidx] = ng; par[nidx] = idx;
            hpush(ng + hfun(nx, ny), nidx);
        }
        /* through-via: column must be statically clear on EVERY routing
         * layer, ring clear on every layer; can land on any other layer */
        int colok = 1;
        for (int l = 0; l < NLAY && colok; l++)
            if (l != L && blk[l * NL + c] && treev[l * NL + c] != tstamp) colok = 0;
        if (colok) {
            int ringok = 1;
            for (int r = 0; r < nring && ringok; r++) {
                int nx = cx + ringoff[r][0], ny = cy + ringoff[r][1];
                if (nx < 0 || nx >= W || ny < 0 || ny >= H) continue;
                int32_t nc2 = ny * W + nx;
                for (int l = 0; l < NLAY; l++)
                    if (blk[l * NL + nc2]) { ringok = 0; break; }
            }
            if (ringok) {
                int64_t pen = 0;
                for (int dy = -SCALE; dy <= SCALE; dy++)
                    for (int dx = -SCALE; dx <= SCALE; dx++) {
                        int nx = cx + dx, ny = cy + dy;
                        if (nx < 0 || nx >= W || ny < 0 || ny >= H) continue;
                        int32_t nc2 = ny * W + nx;
                        for (int l = 0; l < NLAY; l++)
                            pen += (int64_t)use8[l * NL + nc2] * pres;
                    }
                for (int oL = 0; oL < NLAY; oL++) {
                    if (oL == L) continue;
                    int32_t oidx = oL * NL + c;
                    if (treev[oidx] == tstamp) {
                        par[oidx] = idx; reconstruct(oidx, out); return 1;
                    }
                    if (blk[oidx]) continue;
                    int64_t ng = g + VIACOST + pen + hist[idx] + hist[oidx];
                    if (!(vis[oidx] == gen && dist_[oidx] <= ng)) {
                        vis[oidx] = gen; dist_[oidx] = ng; par[oidx] = idx;
                        hpush(ng + hfun(cx, cy), oidx);
                    }
                }
            }
        }
    }
    return 0;
}

/* usage bookkeeping: each net contributes at most 1 per cell (occv dedup),
 * so junction sharing / via-stamp overlap inside one net never self-conflicts */
static void occ_add(Net *nt, int32_t idx) {  /* SCALE==1 semantics */
    if (occv[idx] != ostamp) {
        occv[idx] = ostamp;
        if (use8[idx] < 255) use8[idx]++;
        vpush(&nt->occ, idx);
    }
}
/* SCALE==2: body +4, halo +1; a cell already halo-stamped by this net is
 * upgraded to body with +3. Conflict = own body cell with use >= 5. */
static void body_add(Net *nt, int32_t idx) {
    if (bodyv[idx] == ostamp) return;
    if (occv[idx] == ostamp) {
        if (use8[idx] < 252) use8[idx] += 3;
        vpush(&nt->occ_u, idx);
    } else {
        if (use8[idx] < 251) use8[idx] += 4;
        vpush(&nt->occ, idx);
    }
    bodyv[idx] = ostamp; occv[idx] = ostamp;
}
static void halo_add(Net *nt, int32_t idx) {
    if (occv[idx] == ostamp) return;
    if (use8[idx] < 254) use8[idx]++;
    occv[idx] = ostamp;
    vpush(&nt->occ_h, idx);
}
static void commit(Net *nt, Vec *path) {
    for (int k = 0; k < path->n; k++) {
        int32_t idx = path->v[k];
        if (SCALE == 1) occ_add(nt, idx);
        else {
            body_add(nt, idx);
            int L = idx / NL, c = idx - L * NL, cx = c % W, cy = c / W;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (!dx && !dy) continue;
                    int nx = cx + dx, ny = cy + dy;
                    if (nx >= 0 && nx < W && ny >= 0 && ny < H)
                        halo_add(nt, L * NL + ny * W + nx);
                }
        }
        if (k + 1 < path->n) {
            int32_t a = path->v[k], b = path->v[k + 1];
            if (a % NL == b % NL && a != b) {  /* layer change -> via stamp both layers */
                int c = a % NL, cx = c % W, cy = c / W;
                int R = SCALE, RH = SCALE + 1;
                for (int dy = -RH; dy <= RH; dy++)
                    for (int dx = -RH; dx <= RH; dx++) {
                        int nx = cx + dx, ny = cy + dy;
                        if (nx < 0 || nx >= W || ny < 0 || ny >= H) continue;
                        int32_t nc = ny * W + nx;
                        int body = (dx >= -R && dx <= R && dy >= -R && dy <= R);
                        for (int l = 0; l < NLAY; l++) {
                            if (SCALE == 1) {
                                if (body) occ_add(nt, l * NL + nc);
                            } else if (body) {
                                body_add(nt, l * NL + nc);
                            } else {
                                halo_add(nt, l * NL + nc);
                            }
                        }
                    }
            }
        }
    }
}

static void rip(Net *nt) {
    int d = SCALE == 1 ? 1 : 4;
    for (int i = 0; i < nt->occ.n; i++)
        use8[nt->occ.v[i]] = use8[nt->occ.v[i]] > d ? use8[nt->occ.v[i]] - d : 0;
    for (int i = 0; i < nt->occ_u.n; i++)
        use8[nt->occ_u.v[i]] = use8[nt->occ_u.v[i]] > 3 ? use8[nt->occ_u.v[i]] - 3 : 0;
    for (int i = 0; i < nt->occ_h.n; i++)
        if (use8[nt->occ_h.v[i]]) use8[nt->occ_h.v[i]]--;
    vclear(&nt->occ); vclear(&nt->occ_u); vclear(&nt->occ_h);
    for (int j = 0; j < nt->npads; j++) vclear(&nt->paths[j]);
    nt->fails = 0;
}

static void route_net(Net *nt) {
    rip(nt);
    tstamp++; ostamp++;
    bx0 = by0 = 1 << 29; bx1 = by1 = -(1 << 29);
    for (int i = 0; i < nt->pads[0].goal.n; i++) tree_add(nt->pads[0].goal.v[i]);
    /* carve ALL the net's pads for the whole tree build: a pad's own
     * inflation ring must not moat it off when it is the JOIN TARGET
     * (this sealed the Pico pads -- approach ring blocked, goal adjacent
     * to nothing reachable). Same-net proximity is legal. */
    for (int j = 0; j < nt->npads; j++)
        for (int i = 0; i < nt->pads[j].carve.n; i++)
            blk[nt->pads[j].carve.v[i]] = 0;
    int nrem = 0;
    for (int j = 1; j < nt->npads; j++) rem[nrem++] = j;
    while (nrem) {
        int bi = 0; int64_t bd = 1LL << 60;
        for (int i = 0; i < nrem; i++) {
            int c = nt->pads[rem[i]].center % NL;
            int64_t d = hfun(c % W, c / W);
            if (d < bd) { bd = d; bi = i; }
        }
        int j = rem[bi];
        rem[bi] = rem[--nrem];
        Pad *pd = &nt->pads[j];
        int okr = astar(pd->center, &nt->paths[j]);
        if (okr) {
            commit(nt, &nt->paths[j]);
            for (int k = 0; k < nt->paths[j].n; k++) tree_add(nt->paths[j].v[k]);
            for (int i = 0; i < pd->goal.n; i++) tree_add(pd->goal.v[i]);
        } else {
            /* failed pads must NOT seed the tree (the v12 poisoning lesson) */
            vclear(&nt->paths[j]);
            nt->fails++;
        }
    }
    for (int j = 0; j < nt->npads; j++)  /* restore the carves */
        for (int i = 0; i < nt->pads[j].carve.n; i++)
            blk[nt->pads[j].carve.v[i]] = 1;
}

static int cmp_order(const void *a, const void *b) {
    int ia = *(const int *)a, ib = *(const int *)b;
    int d = nets[ia].npads - nets[ib].npads;
    return d ? d : ia - ib;
}

static int32_t rd32(FILE *f) { int32_t x; fread(&x, 4, 1, f); return x; }

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: route_nc in.bin out.bin\n"); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("in"); return 2; }
    W = rd32(f); H = rd32(f); nnets = rd32(f);
    const char *el = getenv("ROUTE_NC_LAYERS");
    if (el) NLAY = atoi(el);
    NL = W * H; NN2 = NLAY * NL;
    blk = (uint8_t *)malloc(NN2);
    fread(blk, 1, NN2, f);
    use8 = (uint8_t *)calloc(NN2, 1);
    hist = (uint32_t *)calloc(NN2, 4);
    vis = (uint32_t *)calloc(NN2, 4);
    closedv = (uint32_t *)calloc(NN2, 4);
    treev = (uint32_t *)calloc(NN2, 4);
    occv = (uint32_t *)calloc(NN2, 4);
    bodyv = (uint32_t *)calloc(NN2, 4);
    dist_ = (int64_t *)calloc(NN2, 8);
    par = (int32_t *)calloc(NN2, 4);
    nets = (Net *)calloc(nnets, sizeof(Net));
    int maxpads = 2;
    for (int i = 0; i < nnets; i++) {
        Net *nt = &nets[i];
        nt->npads = rd32(f);
        if (nt->npads > maxpads) maxpads = nt->npads;
        nt->pads = (Pad *)calloc(nt->npads, sizeof(Pad));
        nt->paths = (Vec *)calloc(nt->npads, sizeof(Vec));
        for (int j = 0; j < nt->npads; j++) {
            Pad *pd = &nt->pads[j];
            pd->center = rd32(f);
            int ng = rd32(f);
            for (int k = 0; k < ng; k++) vpush(&pd->goal, rd32(f));
            int nc = rd32(f);
            for (int k = 0; k < nc; k++) vpush(&pd->carve, rd32(f));
        }
    }
    fclose(f);
    rem = (int *)malloc((size_t)maxpads * 4);
    order = (int *)malloc((size_t)nnets * 4);
    for (int i = 0; i < nnets; i++) order[i] = i;
    qsort(order, nnets, 4, cmp_order);

    long maxsec = 43200;
    const char *ms = getenv("ROUTE_NC_MAXSEC");
    if (ms) maxsec = atol(ms);
    const char *e;
    if ((e = getenv("ROUTE_NC_HINC"))) HINC = atoi(e);
    if ((e = getenv("ROUTE_NC_PRESMAX"))) PRES_MAX = atol(e);
    if ((e = getenv("ROUTE_NC_VIACOST"))) VIACOST = atoi(e);
    if ((e = getenv("ROUTE_NC_SCALE"))) SCALE = atoi(e);
    if ((e = getenv("ROUTE_NC_CAP"))) EXPCAP = atol(e);
    if (SCALE == 1) {
        nring = 8;
        memcpy(ringoff, RING, sizeof(RING));
    } else {
        /* static via clearance: every cell whose center could hide copper
         * within via_r+clr must be free: radius^2 <= 18 at G=0.13 */
        nring = 0;
        for (int dy = -4; dy <= 4; dy++)
            for (int dx = -4; dx <= 4; dx++)
                if ((dx || dy) && dx * dx + dy * dy <= 18) {
                    ringoff[nring][0] = dx; ringoff[nring][1] = dy; nring++;
                }
    }
    int maxit = 400;
    if ((e = getenv("ROUTE_NC_MAXIT"))) maxit = atoi(e);
    time_t t0 = time(NULL);
    const char *hin = getenv("ROUTE_NC_HIST_IN");
    const char *hout = getenv("ROUTE_NC_HIST_OUT");
    if (hin) {
        FILE *hf = fopen(hin, "rb");
        if (hf) {
            size_t got = fread(hist, 4, NN2, hf);
            fclose(hf);
            if ((int32_t)got == NN2) {
                pres = PRES_MAX;  /* resume in late-negotiation regime */
                printf("hist warm-start loaded (%s)\n", hin);
            } else {
                memset(hist, 0, (size_t)NN2 * 4);
                printf("hist warm-start SIZE MISMATCH, ignored\n");
            }
            fflush(stdout);
        }
    }

    for (int iter = 0; iter < maxit; iter++) {
        int nrer = 0, nfail = 0;
        for (int oi = 0; oi < nnets; oi++) {
            Net *nt = &nets[order[oi]];
            if (iter > 0 && !nt->conflicted) continue;
            route_net(nt);
            nrer++;
            nfail += nt->fails;
            if (iter == 0 && nrer % 1000 == 0) {
                printf("  iter0: %d/%d nets, %ds\n", nrer, nnets,
                       (int)(time(NULL) - t0));
                fflush(stdout);
            }
        }
        int othr = SCALE == 1 ? 2 : 5;
        long overcells = 0;
        for (int32_t i = 0; i < NN2; i++) if (use8[i] >= othr) overcells++;
        int nconf = 0;
        for (int i = 0; i < nnets; i++) {
            Net *nt = &nets[i];
            nt->conflicted = nt->fails > 0;
            if (!nt->conflicted) {
                if (SCALE == 1) {
                    for (int k = 0; k < nt->occ.n; k++)
                        if (use8[nt->occ.v[k]] > 1) { nt->conflicted = 1; break; }
                } else {
                    for (int k = 0; k < nt->occ.n && !nt->conflicted; k++)
                        if (use8[nt->occ.v[k]] >= 5) nt->conflicted = 1;
                    for (int k = 0; k < nt->occ_u.n && !nt->conflicted; k++)
                        if (use8[nt->occ_u.v[k]] >= 5) nt->conflicted = 1;
                }
            }
            nconf += nt->conflicted;
        }
        printf("iter %d: rerouted %d, fails %d, overused cells %ld, conflicted nets %d, pres %lld, %ds\n",
               iter, nrer, nfail, overcells, nconf, (long long)pres,
               (int)(time(NULL) - t0));
        fflush(stdout);
        if (nconf == 0) { printf("CONVERGED\n"); break; }
        if (time(NULL) - t0 > maxsec) { printf("TIME LIMIT\n"); break; }
        for (int32_t i = 0; i < NN2; i++)
            if (use8[i] >= othr) {
                uint32_t h2 = hist[i] + HINC;
                hist[i] = h2 > HMAX ? HMAX : h2;
            }
        pres = pres * 17 / 10 + 1;
        if (pres > PRES_MAX) pres = PRES_MAX;
        if (hout && iter % 200 == 199) {  /* periodic checkpoint */
            FILE *hf = fopen(hout, "wb");
            if (hf) { fwrite(hist, 4, NN2, hf); fclose(hf); }
        }
    }
    if (hout) {
        FILE *hf = fopen(hout, "wb");
        if (hf) { fwrite(hist, 4, NN2, hf); fclose(hf); printf("hist saved (%s)\n", hout); }
    }

    FILE *o = fopen(argv[2], "wb");
    if (!o) { perror("out"); return 2; }
    fwrite(&nnets, 4, 1, o);
    for (int i = 0; i < nnets; i++) {
        Net *nt = &nets[i];
        int32_t nrec = nt->npads - 1;
        fwrite(&nrec, 4, 1, o);
        for (int j = 1; j < nt->npads; j++) {
            int32_t pi = j, plen = nt->paths[j].n;
            fwrite(&pi, 4, 1, o);
            fwrite(&plen, 4, 1, o);
            if (plen) fwrite(nt->paths[j].v, 4, plen, o);
        }
    }
    fclose(o);
    if (argc > 3) {  /* dump overused cells for congestion geography analysis */
        FILE *ov = fopen(argv[3], "w");
        if (ov) {
            int othr2 = SCALE == 1 ? 2 : 5;
            for (int32_t i = 0; i < NN2; i++)
                if (use8[i] >= othr2) {
                    int L = i / NL, c = i % NL;
                    fprintf(ov, "%d %d %d %d\n", L, c % W, c / W, use8[i]);
                }
            fclose(ov);
        }
    }
    printf("wrote %s\n", argv[2]);
    return 0;
}
