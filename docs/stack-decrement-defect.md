# The stack pointer decrements by 2 — board #1

**Found 2026-08-26, from the wifi control panel, no terminal.**
Status: **confirmed, deterministic, localised.** Cause class (fab defect vs. the known
driver-contention ratio bug) is **not yet settled** — see "The one question left".

---

## Summary

On board #1, every stack **push** decrements the stack pointer by **2 instead of 1**.
Stack **pulls** increment correctly by 1. Every other instruction observed executes
perfectly.

This is the root cause of the decimal-test failures reported as
`FAILED at $02F3, listing line 367`. The chain is:

```
push decrements S by 2
  -> every push sequence leaves one stack slot never written, and S drifts down twice as fast
  -> RTS pulls two bytes that are not the return address (they are stale PHP flag bytes)
  -> PC lands in the zero-filled void ($00 everywhere outside the 252-byte image)
  -> $00 is BRK
  -> BRK vectors to int_trap at $02F3
  -> the watcher reports "FAILED at $02F3"
```

`$02F3` is **not** a decimal-arithmetic failure and **not** a spurious interrupt. It is a
catch-all: `tools/build_functest.py` points both NMI and IRQ at one self-loop, and
`bus6502.c` zero-fills memory, so *any* PC excursion off the image reaches it. The
decimal test's real verdict traps are `$024F` (PASS) and `$0252` (FAIL); neither was
ever reached.

---

## The decisive measurement

A purpose-built 14-byte image, loaded over the network via `POST /load`:

```asm
$0200  A2 FF     LDX #$FF
$0202  9A        TXS          ; S = $FF, from a known constant
$0203  A9 AA     LDA #$AA
$0205  48        PHA          ; expect -> $01FF
$0206  48        PHA          ; expect -> $01FE
$0207  48        PHA          ; expect -> $01FD
$0208  4C 08 02  JMP $0208    ; done
$020B  4C 0B 02  JMP $020B    ; BRK/IRQ/NMI land here, distinct from the done-loop
```

Vectors: NMI `$3FFA` -> `$020B`, RES `$3FFC` -> `$0200`, IRQ `$3FFE` -> `$020B`.

Result, decoded from `/trace?n=32`:

```
cycle  addr    data  what
16     $3FFD   02    reset vector high                    OK
17     $0200   A2    SYNC  LDX #$FF                       OK
18     $0201   FF                                         OK
19     $0202   9A    SYNC  TXS                            OK
21     $0203   A9    SYNC  LDA #$AA                       OK
22     $0204   AA                                         OK
23     $0205   48    SYNC  PHA
25     $01FF   AA    WRITE     S = $FF                    OK
26     $0206   48    SYNC  PHA
28     $01FD   AA    WRITE     S = $FD   <-- expected $01FE
29     $0207   48    SYNC  PHA
31     $01FB   AA    WRITE     S = $FB   <-- expected $01FD
32+    $0208/$0209/$020A  JMP self-loop                   OK
```

**S goes `$FF` -> `$FD` -> `$FB`.** Minus two, every time.

Everything else in the trace is correct: `LDX`, `TXS`, `LDA`, the data written
(`$AA` on all three pushes), the reset vector fetch, and a textbook 3-cycle
`JMP` absolute loop.

### Frequency independence

The identical run at two clock rates produced **byte-identical traces** — same
addresses, same cycle numbers, same data:

| clock op | half-period | frequency | result |
|---|---|---|---|
| `v=100` | 100 us | 5 kHz | `511, 509, 507` |
| `v=30`  | 30 us  | 16.7 kHz | `511, 509, 507` |

The same `-2` signature was also present in the decimal-test failures at **2 kHz**.
That is an **8x span, bit-for-bit reproducible.**

A marginal analog fault — charge retention, node settling, a flaky solder joint —
would jitter somewhere across that range. This does not. It is a clean logic fault.

---

## Reproducing it

Requires only `curl`. No USB terminal. Replace the IP.

```bash
B=http://192.168.68.65

curl "$B/cmd?op=stop"        # /load returns 409 while the CPU is running
curl "$B/cmd?op=ft&v=0"      # watcher off, so the cycle budget is deterministic

curl -X POST --data-binary @- "$B/load" <<'HEX'
:0E020000A2FF9AA9AA4848484C08024C0B02DB
:063FFA000B0200020B02A5
:00000001FF
HEX

curl "$B/cmd?op=clock&v=100"      # 100 us half-period = 5 kHz
curl "$B/cmd?op=resetrun&v=40"    # reset+run atomically; never reset then run separately
curl "$B/trace?n=32"
```

`/load` answers `{"ok":1,"bytes":20,"rec":2,"bad":0,"vec":512}` — `vec` 512 is `$0200`,
confirming the reset vector took.

`/trace` returns `[cycle, addr, data, flags]` in **decimal**; `flags` bit0 = read,
bit1 = sync. `$01FF` = 511, `$01FE` = 510, `$01FD` = 509, `$01FC` = 508, `$01FB` = 507.

**Two procedural traps that cost time before this worked:**

1. **`R` then `g` does not work, and the firmware tells you to do it anyway.**
   `load_builtin()` prints *"R then g to run"*, but `R`'s own comment says a reset
   followed by a separately-typed run command starts from garbage — the clock parks at
   the prompt and the worst dynamic node holds charge for ~1.1 ms. On the wifi panel the
   equivalent trap is loading an image while stopped (which pushes `CMD_RESET`, parking
   the clock) and then pressing **"Capture 200 cycles"** (`cmd('run',200)` — no reset).
   Only **"Reset and run"** (`CMD_RESETRUN`) is atomic. *Suggested fix: change that
   printed string to `R <N>`.*
2. **The wifi panel can only show 32 cycles.** `MIRROR_LEN` is 32 and the page requests
   `n=16`; `/trace?n=32` doubles what the UI shows. The full 1024-entry ring on core 1 is
   **not exposed over the network** — only the tester firmware reaches it, via `d N` over
   USB. Diagnosing this needed the purpose-built 15-cycle program precisely because a
   32-cycle window cannot hold the run-up to a failure in real code.

---

## Mechanism

Pulls are correct and pushes are not, so the fault is in one direction of the stack
pointer adjust:

- **Increment** (`PLA`, `RTS`): `S + $00` with carry-in 1. Observed correct three
  times in a row during one `RTS` (`$01F8`, `$01F9`, `$01FA`).
- **Decrement** (`PHA`, `BRK`): `S + $FF` with carry-in 0.

If **bit 0 of that `$FF` constant is stuck low**, the operand becomes `$FE` and every
decrement is `-2`. Increments are untouched, because `$00` already has bit 0 low.

That single fault explains the entire trace and the asymmetry between push and pull.
It is a hypothesis, not yet proven — see the next section for the test that confirms it.

### Not yet reconciled

The three BRK push sequences captured before the purpose-built test show `-2` on the
**first** decrement and `-1` on the second:

| source | pushed at | S sequence |
|---|---|---|
| decimal run 1 | `$012B, $0129, $0128` | `$2B -> $29 -> $28` |
| decimal run 2 | `$01F9, $01F7, $01F6` | `$F9 -> $F7 -> $F6` |
| decimal run 3 | `$01FA, $01F8, $01F7` | `$FA -> $F8 -> $F7` |

Each third push is exactly **one address bit 0** away from fitting "always `-2`".
Run 1 also carried an unrelated intermittent fault (below), so these are the noisier
samples. **Do not overfit to them.** The `PHA` test is the clean evidence.

### A separate, unrelated intermittent: address bit 2

The first decimal trace showed `ab2` reading low on five consecutive bus cycles
(`$3FFE`->`$3FFA`, `$3FFF`->`$3FFB`, `$02F4`->`$02F0`, `$02F5`->`$02F1`,
`$0A85`->`$0A81`) and then correct on the sixth. It has **not recurred** in any run
since.

That trace also proved the CPU's internal PC was right while the pin was wrong: a BRK
at real address `$0A85` pushed `$0A87` = PC+2, while the pin had shown `$0A81`. So the
fault was between the internal address and the pad, not in the PC.

`adl2` is one of the sixteen address-path rework sites. **Worth re-checking after the
rework, but it is not what breaks the decimal test.**

---

## What is ruled out

| hypothesis | ruled out by |
|---|---|
| Spurious NMI or IRQ | Pushed P = `$34` and `$36` — **bit 4 (B) set** in both. That is BRK, not a hardware interrupt. The vector fetch was `$3FFE/$3FFF`, correct for BRK. |
| Decimal-mode arithmetic bug | The test never reached `$024F` or `$0252`. Pushed P also had **bit 3 (D) clear** — it was not even in decimal mode when it derailed. |
| Charge retention / clock too slow | Identical at 2 kHz, 5 kHz and 16.7 kHz. |
| Node settling / clock too fast | Same. The address is already sampled at the very end of phi1, the latest possible point. |
| Reset never taken / decayed start state | `CMD_RESETRUN` is atomic; the trace shows the reset vector fetch at `$3FFD` and correct execution from `$0200`. |
| Netlist transform error | `tools/switchsim.py`'s equivalence gate ran a test program exercising **JSR and the stack** and passed. Topology is right. |
| Floating `irq`/`nmi` | 10k pull-ups fitted, and the pushed B flag says BRK regardless. |

Note that switchsim passing is *consistent* with a contention fault: the gate is
structurally incapable of judging levels (`_value()` resolves any contention as low),
which is the blind spot already recorded in `cards/verification.md`.

---

## The one question left

**Is this a random fab defect on board #1, or the predicted driver-contention ratio bug
finally showing itself functionally?**

It matters enormously:

| | random fab defect | driver-contention ratio bug |
|---|---|---|
| Scope | board #1 only | **all four boards, identically** |
| Fix | find and reflow one joint | a series resistor at that site (the rework already in progress elsewhere) |
| Precedent | matches the yield estimate of 0.5–2 defects/board | matches the 2026-08-01 prediction, never before observed |

The contention prediction, in its own words from `project-plan.md`:

> *the contended node sits at 1.0–1.9 V against a 1.1–1.5 V receiver threshold, so the
> stage can read HIGH when it should read LOW*

A `$FF` constant whose bit 0 will not go low is exactly "reads HIGH when it should read
LOW". If that net is one of the **164 VCC-side FET sites**, this is the first functional
manifestation of a defect predicted three weeks ago and so far seen only as heat.

---

## Netlist query on the 164 VCC-side sites (run 2026-08-26)

**Answer: yes — 21 of the 164 sit in the stack-pointer datapath. But the mechanism
points at a node that is _not_ one of them, and that distinction is the whole finding.**

### The 21

Extracted from `gen/netlist.json` (`role == 'vcc_side'`, 164 FETs on 164 distinct nets):

```
sb0 sb1 sb2 sb3 sb4 sb5 sb6 sb7          the special bus, all eight bits
dpc4_SSB    dpc6_SBS    dpc7_SS          S -> SB, SB -> S, S -> S
dpc5_SADL                                S -> ADL (the push address)
dpc11_SBADD dpc12_0ADD                   ALU A input select
dpc8_nDBADD dpc9_DBADD dpc10_ADLADD      ALU B input select
dpc17_SUMS                               ALU sum
dpc19_ADDSB7 dpc20_ADDSB06 dpc21_ADDADL  ALU result routing
```

Every control line the stack pointer touches is a VCC-side site.

### Contention duty, measured

`tools/contention_duty.py --halves 600`, both workloads:

| net | real (stack/JSR) | nop |
|---|---|---|
| `sb0` | 15.8% | **24.2%** |
| `sb1` | 15.7% | 0.5% |
| `sb2` | 15.2% | 0.3% |
| `sb3` | 15.2% | 0.0% |
| `sb4` | 15.5% | 0.3% |
| `sb5` | 14.7% | 0.0% |
| `sb6` | 15.2% | 0.0% |
| `sb7` | 15.3% | 0.0% |
| all 13 `dpc*` above | **0.0%** | **0.0%** |

`sb0` is 48x the next-highest `sb` bit under NOP. Suggestive — but **`sb0` does not fit
the symptom.** `sb0` carries both S into the ALU and the result back to S. If it read
HIGH when it should read LOW, S bit 0 could never fall, giving *no decrement at all*
(`$FF` -> `$FF`), not `-2`. Rejected on arithmetic, not on the duty figure.

### What does fit: `alub0` stuck low

> **SUPERSEDED — falsified on hardware the same day. See the CORRECTION section below.
> DEX decrements correctly, so `alub0` is fine and Q1313/Q1314 are exonerated.**

The netlist gives the ALU operand structure directly:

- `alua` <- SB (`dpc11_SBADD`), or forced to 0 by a pull-down gated by `dpc12_0ADD`
- `alub` <- ADL (`dpc10_ADLADD`) / DB (`dpc9_DBADD`) / **nDB** (`dpc8_nDBADD`)

So a decrement is `A = S`, `B = $FF` (the complement of a zero DB, via nDB/ADD),
carry-in 0. An increment is `A = S`, `B = $00`, carry-in 1.

**`alub0` has no pull-up resistor.** It is a pure dynamic node driven only by three pass
gates. If it cannot be pulled high:

| operation | B should be | B becomes | result |
|---|---|---|---|
| decrement | `$FF` | `$FE` | **S - 2** |
| increment | `$00` | `$00` | **unchanged — correct** |

That reproduces both halves of the observation exactly, including the asymmetry that
pulls are perfect while pushes are not. `$FF -> $FD -> $FB` follows directly.

It also explains why **only bit 0** is wrong. A contended *control* line
(`dpc8_nDBADD` et al.) is shared by all eight bits and would corrupt the whole operand;
those three lines also measure **0.0% duty** under both workloads.

### The suspect site

The nDB -> `alub0` pass pair, and its two rivals on the same node. All on the **top
face**, clustered within 15 mm:

| ref | role | gate | board x | board y |
|---|---|---|---|---|
| **Q1313** | pass_a | `dpc8_nDBADD` | 86.15 | 186.20 |
| **Q1314** | pass_b | `dpc8_nDBADD` | 75.05 | 180.60 |
| Q532 / Q533 | pass pair | `dpc9_DBADD` | 82.45 | 186.20 / 183.40 |
| Q442 / Q443 | pass pair | `dpc10_ADLADD` | 82.45 | 180.60 / 183.40 |
| (`sb0` driver) Q1804 | vcc_side | `cclk` | 71.35 | 191.80 |

**Q1313/Q1314 are the primary suspects**: an open there leaves `alub0` with no path to
the `$FF` operand at all.

### Verdict on the original question

**This looks more like a single-transistor fab defect than the driver-contention ratio
bug — and the discriminator is bit-specificity.** The contention bug acts on whole nets;
here seven of eight operand bits are provably fine (`$FF -> $FD -> $FB` differs from a
correct decrement only in bit 0). Consequences if that holds: **board #1 only**, the fix
is a reflow or replacement at one site rather than a series resistor, and the other
three boards are unaffected.

Not yet excluded: a marginal level on `dpc8_nDBADD` that happens to fail only the
weakest of its eight pass gates. Contrived, and contradicted by the 0.0% duty, but not
impossible.

### The bench test that settles it

`DEX` uses the same ALU decrement path as a push (`X -> SB -> alua`, `B = $FF` via nDB).
If `alub0` is the fault, **DEX must also decrement by 2, and INX must be correct.** If
DEX is clean, the fault is stack-specific instead and this localisation is wrong.

13 bytes. `STX` makes the result visible on the bus, since the panel has no memory read:

```asm
$0200  A2 FF     LDX #$FF
$0202  CA        DEX
$0203  8E 00 03  STX $0300     ; healthy $FE (254) / faulty $FD (253)
$0206  E8        INX
$0207  8E 01 03  STX $0301     ; healthy $FF (255) / faulty $FE (254)
$020A  4C 0A 02  JMP $020A
$0210  4C 10 02  JMP $0210     ; interrupt trap, clear of the code
```

```
:0D020000A2FFCA8E0003E88E01034C0A0223
:030210004C10028D
:063FFA001002000210029B
:00000001FF
```

Watch for writes to `768` (`$0300`) and `769` (`$0301`) in `/trace?n=32`.

- `768 <- 253` and `769 <- 254` -> **`alub0` confirmed.** The fault is in the shared ALU
  decrement operand, not in the stack logic; Q1313/Q1314 become the rework target.
- `768 <- 254` and `769 <- 255` -> DEX is clean, the fault is stack-specific, and the
  `alub0` hypothesis is wrong.

---

## CORRECTION 2026-08-26 (later): `alub0` falsified on hardware

> **Superseded -- see "RESOLVED 2026-08-28" below. The `sb0` conclusion
> reached in this section is also wrong; `DEX` rules it out.**

Run with `tools/board_probe.py` against board #1, over the wifi panel. **The
`alub0` hypothesis above is dead and Q1313/Q1314 are exonerated.**

| test | program | result |
|---|---|---|
| `dex` | `LDX #$FF; DEX; STX $0300; INX; STX $0301` | **PASS** — `$FE` then `$FF` |
| `sxfer` | `LDX #$FF; TXS; TSX; STX $0300` | **PASS** — `$FF` |
| `push1` | `LDA #$AA; LDX #$FF; TXS; PHA; TSX; STX $0300` | **FAIL** — S = `$FD` |

What each one removes:

- **DEX is correct**, so the ALU decrement operand (`$FF` via nDB/ADD) is fine and
  `alub0` reaches a valid high. The whole "stuck-low operand bit" chain fails here.
- **TXS/TSX round-trips cleanly**, so the S register and its SB interface are healthy
  when no decrement is involved.
- **A single PHA steps by 2**, so this is not a consecutive-push effect. Every push
  doubles.

### The reframing that matters

`-2` is a **clean whole-byte double decrement, not a bit fault.** `$FF -> $FD` and
`$FD -> $FB` both require the borrow chain to work perfectly. The earlier bit-0 framing
was wrong, and with it the argument that bit-specificity pointed at a single transistor.

**The stack pointer is decremented twice per push.**

### Revised localisation

What a push does that DEX and TXS/TSX do not:

| | control lines |
|---|---|
| push | `dpc5_SADL` (S->ADL), `dpc4_SSB` (S->SB), ALU -1, `dpc6_SBS` (SB->S), `dpc7_SS` (S->S hold) |
| DEX | `dpc2_XSB` (X->SB), ALU -1, `dpc3_SBX` (SB->X) |

If **`dpc4_SSB` and `dpc6_SBS` are ever asserted together**, `S -> SB -> ALU(-1) -> SB
-> S` becomes a live feedback loop and settles two steps down. The 6502 never asserts
both at once. A control line that cannot reach a valid low would do exactly this.

**All four push-side control lines are among the 164 VCC-side sites** (`dpc4_SSB`,
`dpc5_SADL`, `dpc6_SBS`, `dpc7_SS`) — and so are the DEX-side pair, so their presence in
the list is not by itself evidence. What *is* suggestive: a stuck-partially-on control
line is precisely the predicted contention failure, *"the stage can read HIGH when it
should read LOW"*.

Their measured contention duty is 0.0%, but **`switchsim` cannot see levels** — the
blind spot recorded in `cards/verification.md` — and duty is workload-dependent, so 0.0%
is weak evidence of absence here.

**Consequence: the driver-contention ratio bug is back as the leading explanation, and
if it is that, the fault is systematic across all four boards** — the opposite of the
verdict in the section above.

### Frequency sweep

`push1` at four clock rates, all identical:

| half-period | frequency | result |
|---|---|---|
| 250 us | 2.0 kHz | FAIL, S = `$FD` |
| 100 us | 5.0 kHz | FAIL, S = `$FD` |
| 50 us | 10.0 kHz | FAIL, S = `$FD` |
| 30 us | 16.7 kHz | FAIL, S = `$FD` |

### Probe points

The VCC-side FET on each control line — the site that would sit at an invalid level.
All on the **top face**, in one row at y = 172.2 apart from `dpc4_SSB`:

| net | ref | x | y | side |
|---|---|---|---|---|
| `dpc4_SSB` | **Q3907** | 67.65 | 175.00 | F.Cu |
| `dpc5_SADL` | Q1944 | 75.05 | 172.20 | F.Cu |
| `dpc6_SBS` | **Q3978** | 78.75 | 172.20 | F.Cu |
| `dpc7_SS` | Q552 | 82.45 | 172.20 | F.Cu |
| `dpc2_XSB` (control, works) | Q2818 | 56.55 | 172.20 | F.Cu |
| `dpc3_SBX` (control, works) | Q3041 | 67.65 | 172.20 | F.Cu |

**The decisive measurement is a scope on `dpc4_SSB` and `dpc6_SBS` during a push.** A
contended net sits at **1.0–1.9 V** against a 1.1–1.5 V receiver threshold instead of
below 0.5 V. `dpc2_XSB` and `dpc3_SBX` are the built-in controls: same structure, same
164 list, and DEX proves they work — so if the push pair reads high and the DEX pair
reads clean, that is the contention bug caught in the act.

---

## RESOLVED 2026-08-28: S bit 0 is stuck high

> **Cause found and repaired the same day -- see "FIXED 2026-08-28" below.**

**Confirmed on board #1 across a power cycle, with a negative control.**

```
LDX #$3C ; TXS ; TSX ; STX $0300   ->  $3D     bit 0 forced high   FAIL
LDX #$3D ; TXS ; TSX ; STX $0300   ->  $3D     bit 0 already 1     pass
LDX #$3C ;           STX $0300     ->  $3C     never touches S     pass
```

The third line is what makes this conclusive: `LDX`, the X register, `STX`, the data
bus and the literal `$3C` are all proven good. The only difference in the first test is
that the value passes through S, and bit 0 returns set.

Also measured the same session, 4/4 trials each:

| test | result |
|---|---|
| one `PHA`, then `TSX` | S = `$FF`, should be `$FE` -- S never decrements |
| `DEX` / `INX` | `$FE` then `$FF` -- **correct** |

`DEX` passing matters: it requires bit 0 to carry a zero through the SB bus and the ALU.
So `sb0` and the ALU are fine, and this is the stack pointer register itself.

### Why every earlier symptom followed

- `$FF -> $FD -> $FB` (the original "decrements by 2") -- bit 0 never changing
- S not decrementing at all -- from `$FF`, a decrement needs bit 0 to fall
- `RTS` pulling flag bytes instead of a return address, PC into the zero-filled void,
  `$00` = BRK, and the reported `FAILED at $02F3`

### The suspects

`s0` has **no pull-up and no VCC-side FET** -- it is a pure dynamic node, so this is
**not** the driver-contention ratio bug. Only four parts touch it:

| ref | role | function | x | y |
|---|---|---|---|---|
| **Q4024** | led_driver, gate `s0` | drives the S0 LED; its drain reaches VCC through the LED | 78.75 | 189.00 |
| **Q1099** | pass_b, gate `dpc6_SBS` | writes S from the SB bus | 71.35 | 183.40 |
| **Q269** | pass_b, gate `dpc7_SS` | the S->S recirculating hold | 78.75 | 191.80 |
| Q2577 | pulldown, gate `s0` | a load s0 drives, not a driver | 75.05 | 183.40 |

**Q4024 is the prime suspect** because it is the only path from `s0` to VCC that exists
at all. A gate-to-drain short there pulls `s0` up through the LED, and `s0` has no
pull-down to fight it. Free check: the **S0 LED should be permanently lit** if bit 0 is
stuck high.

### Provenance

This is bit-specific, on a net the rework never touched, and consistent with the
recorded yield estimate of 0.5-2 random defects per board across ~14,700 joints. It was
present from the start; the driver contention and the address-bus faults were louder.

### Hypotheses that were wrong, and why

Both were stated with more confidence than single-run evidence supported, on a board
whose address bus was itself intermittent at the time.

- **`alub0` / Q1313-Q1314** -- falsified the same day: `DEX` decrements correctly, so
  the ALU operand is fine.
- **`sb0` / Q1804** -- falsified here: `DEX` requires bit 0 to pass a zero over SB.

The lesson worth keeping: **on an intermittent board, no single run is evidence.** The
diagnosis only became stable once the address bus held steady across a power cycle and
every test carried a negative control.

---

## FIXED 2026-08-28: Q2577 replaced

**Root cause: Q2577 (x 75.05, y 183.40) had a gate-to-drain leak of 20 kohm,
against 177 kohm on its matched twin Q3793.**

Q2577 is the pull-down whose gate is `s0` and whose drain is `n983`. Net `n983`
carries a 10 kohm pull-up to VCC (R585). The leak therefore tied `s0` to a node held
high, and `s0` is a pure dynamic node with no pull-down of its own -- so it could never
fall.

```
Q2577 gate-drain leak (20 kohm)
  -> s0 tied to n983, which R585 holds at VCC through 10 kohm
  -> S bit 0 stuck high
  -> PHA cannot decrement S
  -> RTS pulls flag bytes instead of a return address
  -> PC into the zero-filled void, $00 = BRK
  -> "FAILED at $02F3"
```

It also explains the step-1 reading: `s0` measured 30 kohm to *both* rails against
`s1`'s 150 kohm -- symmetric, because through Q2577 it inherited `n983`'s pull-up to VCC
*and* Q2577's own source to VSS. A rail short would have been asymmetric.

**Repair:** transplanted the FET from Q4050, the P2 flag LED driver -- a cosmetic tap the
CPU does not use. Same part (BSS138K / C504052), same package, same rotation, same pin
roles. Cost: the P2 and S0 LEDs are now dark. No donor board needed.

### Verification after the swap

```
LDX #$3C ; TXS ; TSX ; STX        $3C                    PASS
one PHA, then TSX                 $FE                    PASS
PHA x3                            $01FF $01FE $01FD      PASS
push (repeat)                     $FE                    PASS
DEX / INX                         $FE $FF                PASS
PHA $AA / PLA back, S restored    $AA $FF                PASS
```

### How the measurement finally worked

Six readings, each suspect against its matched twin on bit 1:

| part | reading | twin | twin reading |
|---|---|---|---|
| **Q2577** | **20k** | Q3793 | **177k** |
| Q269 | 80k | Q362 | OL |
| Q1099 | 80k | Q311 | OL |

Q269 and Q1099 both read low, but **their pin 3 *is* `s0`** -- once `s0` was tied to
something, they were measuring the same fault through the network. Q2577 was the only
one whose pin 3 (`n983`) is independent of `s0`, so its low reading could not be a side
effect. **The discriminator was not "which reads lowest" but "which reads low for a
reason that cannot be borrowed from the others."**

### Wrong turns, and what they cost

- **`alub0` / Q1313-Q1314** -- DEX decrements correctly, so the ALU operand was fine.
- **`sb0` / Q1804** -- DEX again: bit 0 passes a zero over SB.
- **Q4024**, the S0 LED driver -- read 70 kohm gate-drain against a healthy OL, and was
  removed. **That reading was contaminated**: Q4024's gate *is* `s0`, so the meter saw
  the Q2577 fault straight through it. Removing it changed nothing and cost a part
  (it shed a pin on removal).

All three were called from single in-circuit readings. **An in-circuit two-point
measurement reads the part *and* everything around it** -- on a net that is already
faulty, every part sitting on it reads wrong. The rule that worked: measure against a
matched twin, and trust only the part whose reading cannot be explained by the fault
itself.

---

## 2026-08-28: 23-test datapath self-test PASSES on hardware

After replacing Q2577, board #1 passes `tools/quick_selftest.py` -- 23 subtests, 266
bytes, settling at `$0480` (the pass loop):

```
TXS/TSX   TAX   TXA   TAY/TYA
INX   DEX   INY/DEY wrap
ADC   SBC   AND   ORA   EOR   ASL   LSR
PHA/PLA   S decrements twice   S restored by PLA   PHP/PLP
zero page   absolute,X   Z flag set   Z flag clear   JSR/RTS
```

**The verdict is the address it loops at**, which is the only thing the wifi panel's
32-cycle trace window can always show: `$0480` = pass, `$0400 + 3*(N-1)` = first failing
subtest, `$0600` = BRK or spurious interrupt. No memory read-back needed -- the panel
cannot do one.

**Validated before it was trusted:** the same image runs on the reference visual6502
netlist under `switchsim` and passes all 23 there. That caught two bugs in the test
program itself (the interrupt trap was being written into the middle of the code, and the
`abs,X` subtest wrote on top of the fail-loop table) which would otherwise have looked
like hardware faults.

**What this proves:** registers and every transfer between them, the ALU including carry
and borrow, shifts, the stack in both directions with S tracking correctly, flag
save/restore, two addressing modes, and subroutine call/return. Far beyond the NOP
free-run of 2026-08-25, which exercised only fetch, decode and the PC.

**What it does not prove:** decimal mode, the undocumented opcodes, and the full
addressing-mode matrix. **Klaus Dormann's suite remains the acceptance gate.**

**Still open (bench, not silicon):** the Pico loses power every 25-45 s -- the cycle
counter resets, USB disappears, mDNS drops. VSYS is tied to board VCC, so USB cannot
rescue it and a 10 uF at pins 38/39 did not help. The distinguishing measurement is
whether supply current spikes just before each dropout (a board fault) or the voltage
sags on its own (bench wiring). Until that is settled, long runs are not viable.

---

## Suggested plan

### Do now — before touching the iron again (about 30 minutes, zero hardware risk)

The board is already set up and the whole sequence is `curl` commands.

1. **Confirm the mechanism. One byte changed: `LDX #$FE`.**
   The current test started S odd (`$FF`) and it stayed odd, so "always `-2`" and
   "S bit 0 stuck high" both fit. Starting even separates them.

   ```
   :0E020000A2FE9AA9AA4848484C08024C0B02DC
   :063FFA000B0200020B02A5
   :00000001FF
   ```

   - Writes at `510, 508, 506` (`$01FE, $01FC, $01FA`) -> **always `-2`**, confirming
     the decrement-operand hypothesis.
   - Writes at `510, 509, 507` -> it is S's own bit 0, not the operand.

   Verify the load took: cycle 18 should now read `254`, not `255`.

2. **Test the borrow chain across a byte boundary.** `LDX #$80` -> expect
   `$0180, $017E, $017C` under "always `-2`". Confirms the fault is not confined to
   the top of the page.

3. **Netlist query — the highest-value step, and it needs no hardware.**
   Determine whether the net driving bit 0 of the S decrement operand is among the
   **164 VCC-side FET sites**. If yes, add it to the rework batch. If no, it is a
   solder-joint hunt on one board.

4. **Cross-reference the FLIR images.** A contended site dissipates; a bad joint does
   not. If the suspect site appears in the existing hot-spot images or in
   `docs/hotsites-marked.jpg`, that is corroboration for the contention explanation
   from a completely independent instrument.

### Then — the ordering question

**Recommendation: finish steps 1–4 before completing the current 16-site rework, and let
the netlist answer decide whether the rework list grows.**

Reasoning:

- The 16 `adh`/`adl` sites are being reworked for **heat**, not for logic. They do not
  fix this, and this blocks the acceptance test outright. Priority belongs to the
  blocker.
- **If the S-decrement net is among the 164**, it wants the same 10k-in-series
  treatment, and doing it in the same session with the same setup is far cheaper than a
  second rework session. This is the whole argument for resolving it first — a netlist
  query costs minutes and could save an entire teardown.
- Nothing in steps 1–4 touches the board, so there is no risk in doing them first.
- **Do not start the multi-hour functional test either way.** It cannot pass with the
  stack broken, and the 80 C sites are still unfixed.

### After the rework

5. **Re-run the `PHA` test first, before anything long.** It takes seconds and tells you
   immediately whether the rework changed the stack behaviour.
6. **Re-check `ab2`.** `adl2` is one of the reworked sites; the intermittent bit-2 fault
   may be fixed, unchanged, or newly introduced.
7. **Only then** run the decimal test (`T d` equivalent, ~2h41m at 10 kHz), and only
   after it passes, the functional test.

### If it turns out to be systematic

Testing board #2 is the decisive random-vs-systematic experiment, but it is **not
cheap**: the Pico is soldered to board #1 and boards #2–#4 have DNP Pico sites. Treat it
as a deliberate step to take *after* the netlist query points one way, not as a first
resort.

---

## Appendix: raw captures

Decode key: `/trace` emits `[cycle, addr, data, flags]` in decimal; `flags` bit0 = read
(1) / write (0), bit1 = sync.

### The PHA test, 5 kHz and 16.7 kHz (identical)

```
[16,16381,2,1] [17,512,162,3] [18,513,255,1] [19,514,154,3] [20,515,169,1]
[21,515,169,3] [22,516,170,1] [23,517,72,3]  [24,518,72,1]  [25,511,170,0]
[26,518,72,3]  [27,519,72,1]  [28,509,170,0] [29,519,72,3]  [30,520,76,1]
[31,507,170,0] [32,520,76,3]  ...JMP loop...
```

### The decimal test failing, with the RTS that does it (2 kHz)

```
172  $0295  68  read SYNC   PLA
174  $01F7  00  read        PLA dummy stack read, S=$F7
175  $01F8  34  read        pulls $34 (a stale PHP flag byte)
179  $0298  60  read SYNC   RTS
181  $01F8  34  read        dummy, S=$F8
182  $01F9  34  read        PCL = $34
183  $01FA  34  read        PCH = $34   -> returns to $3434
185  $3435  00  read SYNC   BRK
187  $01FA  34  WRITE       push PCH
188  $01F8  37  WRITE       push PCL ($3435 + 2 = $3437, correct BRK arithmetic)
189  $01F7  34  WRITE       push P = $34, bit 4 set -> BRK confirmed
190  $3FFE  F3  read        IRQ/BRK vector, correct
191  $3FFF  02  read
192+ $02F3  4C  read SYNC   int_trap self-loop
```

The image at `$0291` is `PHP / PLA / STA $0A / PLA / STA $08 / RTS` — every instruction
executed correctly. `RTS` simply found flag bytes where a return address belonged.
