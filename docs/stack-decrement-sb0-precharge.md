# The stack `-2`: the decrement's `$FF` operand is a *precharged bus*, and bit 0 of it is missing

**Research note, 2026-08-27. Simulation and netlist analysis only — nothing on the board, in the
netlist, in the fab package or in the firmware was touched.** Companion to
`docs/stack-decrement-defect.md`, which holds the hardware measurements this builds on.

**Prompted by a hint from the user's friend:** *"could it be a netlist thing — the CPU does
something on each rising and falling clock phase"*. **The hint was right, and it points at the
answer.** The phase-driven action that matters is the **precharge of the special bus (SB)**, and
the stack decrement's arithmetic operand *is* that precharge.

---

## Result in one paragraph

The 6502 decrements S by feeding **S onto ADL into the ALU's B input** and taking the ALU's
**A input from the SB bus while nothing is driving SB** — SB floats at its precharge, so
`A = $FF`, and `S + $FF = S − 1`. SB has **no pull-up resistor**; it is held high solely by
**one FET per bit, gated by `cclk`**, that precharges it every clock phase. If the bit-0
precharge FET is open, SB reads `$FE` instead of `$FF` and **every push decrements by 2**.
The increment path is immune because it forces `A = 0` explicitly (`0/ADD` + carry-in), and DEX
is immune because its `$FF` comes from the **IDB** precharge, a different bus. On our board that
one transistor is **Q1804 (F.Cu, x 71.35, y 191.80)** — the transistor
`docs/stack-decrement-defect.md` already listed as the `sb0` driver and then set aside.

Simulated on both the visual6502 netlist and our transformed netlist, an open Q1804 reproduces
every hardware observation that was cleanly taken — including the ones that falsified the previous
hypothesis. The single exception is the `−2, −1` BRK sequences from the decimal runs, which match
none of the candidates and which `docs/stack-decrement-defect.md` already flags as the noisy
samples.

---

## The measured decrement path (not assumed — dumped from the simulator)

Half-cycle trace of a healthy `PHA` at `$0205` with S = `$FF` (`operands.py`, below):

```
hc clk ab   db rw sy | S  | sb adl alua alub alu | SADL SBADD ADLADD ADDSB SBS
31 1  0206 48 r      | ff | ff  ff   54   54  a8 |  1     .      .      ..   .
32 0  01ff 48 W      | ff | ff  ff   ff   ff  a8 |  1     1      1      ..   .    <- operands latch
33 1  01ff aa W      | ff | fe  06   ff   ff  fe |  .     .      .      11   .    <- sum to SB
34 0  0206 48 r S    | fe | fe  06   00   aa  fe |  .     .      .      11   1    <- SB to S
```

- hc31: `S/ADL` puts S = `$FF` on ADL.
- hc32: `SB/ADD` latches **alua = SB = `$FF`**, `ADL/ADD` latches **alub = S**. Nothing is driving
  SB at this moment — `$FF` is its *precharge*.
- hc33–34: `SUMS` → `ADD/SB` → `SB/S`. S = `$FE`.

The same dump for `PLA` shows `0/ADD` asserted instead of `SB/ADD`: **alua is driven to 0** and the
carry-in supplies the `+1`. And for `DEX` the `$FF` operand arrives as **alub from IDB**, with
alua = X from SB (SB actively driven by `X/SB`, so its precharge is irrelevant).

**That asymmetry is the whole explanation of the observed symptom set:**

| operation | where the `$FF`/`$00` operand comes from | affected by a dead SB bit-0 precharge? |
|---|---|---|
| push (`PHA`, `PHP`, BRK) | **SB, floating at precharge** | **yes → `−2`** |
| pull (`PLA`, `PLP`, `RTS`) | `0/ADD` drives alua low, carry-in = 1 | no |
| `DEX`/`INX` | IDB precharge, SB actively driven by X | no |
| `TXS`/`TSX` | no ALU involved | no |

---

## The suspect, and why it is one transistor

SB is a **precharged dynamic bus**. From the die netlist, each bit has exactly one driver to a
rail, and it is the same structure eight times:

```
sb0  pullup_resistor = none   drivers = [ (gate cclk) -> VCC ]     die t1587  -> our Q1804
sb1..sb7                       same, one cclk-gated FET each
```

There is **no pull-up resistor on any SB bit**. One FET per bit, gated by the internal clock
phase, is the *only* thing that makes SB high. Lose it and that bit reads 0 whenever the bus is
not actively driven — which is exactly the moment the stack decrement samples it.

On the board (`gen/board_routed_golden.kicad_pcb`):

| ref | die | role | pins | layer | x | y |
|---|---|---|---|---|---|---|
| **Q1804** | t1587 | `vcc_side` (SB0 precharge) | 1 `cclk`, 2 `sb0`, 3 `vcc` | F.Cu | **71.35** | **191.80** |

Three pins; an open on pin 2 or pin 3 kills the precharge, and an open on pin 1 (`cclk`) leaves the
gate floating and does the same on average. **This is a single-joint, single-part, one-board
defect** — consistent with the 0.5–2 defects/board yield estimate, not with the driver-contention
ratio bug (see "Which of the two explanations" below).

---

## Simulation evidence

All of it is fault injection around `tools/switchsim.py`, run against **both** the original
visual6502 netlist and `gen/netlist.json` (identical results on both).

### 1. Exhaustive single-fault sweeps

| sweep | space | runs | results reproducing `$01FF, $01FD` |
|---|---|---|---|
| stuck-at HIGH/LOW on every node | 1,668 nodes × 2 | 3,336 | **0** |
| contention resolves HIGH (the predicted ratio bug) on each VCC-side site | 100 sites | 100 | **0** |
| "cannot hold precharge" on each SB / IDB bit | 16 | 16 | 0 |
| **open FET (gate tied off)** | 3,236 FETs | 3,236 | **5** |

The five FET hits are all in the **bit-0 slice of the ALU input path** and nowhere else on the die:

```
t1587  gate cclk         dasb0 - vcc      SB bit-0 precharge          -> Q1804
t53    gate dpc11_SBADD  alua0 - dasb0    SB bit0 -> ALU A            -> Q71/Q72
t372   gate dpc10_ADLADD adl0  - alub0    ADL bit0 -> ALU B           -> Q442/Q443
t228   gate alub0        n1628 - n316     alub0 inverter
t2458  gate alua0        n316  - vss      alua0 inverter
```

### 2. Narrowing the five to one

`t228` and `t2458` break `INX`/`DEX` (final X wrong) and `t53` breaks `LDA abs,X`, `LDA (zp),Y`
and `ADC`/`SBC` — all of which the board does correctly. That leaves `t1587` (Q1804) and `t372`
(Q442/Q443). A battery of eight programs separates those two:

| program | healthy | **Q1804 open** | Q442/443 open |
|---|---|---|---|
| `PHA` ×2 | writes `01FF, 01FE` | **`01FF, 01FD`** | `01FF, 01FD` |
| **`JSR`** | writes `01FF, 01FE` | **`01FF, 01FE` (correct)** | **`01FE, 01FD` (wrong)** |
| `BNE` loop to X=0 | X = `00` | **X = `00`** | X = `02`, plus a spurious write to `$0000` |
| `ADC`/`SBC` | `1F`, `1E` | **`1F`, `1E`** | `1F`, `1E` |
| `LDA $02FB,X` | A = `5A` | **A = `5A`** | A = `5A` |
| `LDA ($10),Y` | A = `5A` | **A = `5A`** | A = `5A` |
| `INC $0300` ×2 | `02` | **`02`** | `02` |
| `PHP`/`PLP`/`TSX` | S = `FF` | **S = `FE`** | S = `FD` |

**Q1804 is the only single fault in the whole netlist that doubles pushes while leaving DEX, INX,
ADC, SBC, indexed addressing, indirect addressing, branches, `INC` and `TXS`/`TSX` perfect** —
which is precisely what the board does.

---

## The bench test that settles it, and it is one instruction

**`JSR` is the discriminator.** Under Q1804 the JSR pushes are *correct*; under the ADL-side
alternative they are shifted. (The simulator shows why JSR is different: during a `JSR` the 6502
parks the target's low byte in S itself and does not generate the stack addresses through the
SB-precharge decrement — the well-known "S as a temporary" quirk. The mechanism was observed, not
traced end to end.)

```asm
$0200  A2 FF     LDX #$FF
$0202  9A        TXS            ; S = $FF
$0203  20 10 02  JSR $0210      ; two pushes -> S should be $FD inside the subroutine
$0206  A9 AA     LDA #$AA
$0208  48        PHA            ; one push  -> S should be $FE (RTS restored it to $FF)
$0209  BA        TSX
$020A  8E 01 03  STX $0301
$020D  4C 0D 02  JMP $020D
$0210  BA        TSX            ; subroutine: report S as JSR left it
$0211  8E 00 03  STX $0300
$0214  60        RTS
$0220  4C 20 02  JMP $0220      ; interrupt trap
```

```
:10020000A2FF9A201002A9AA48BA8E01034C0D023F
:05021000BA8E0003603E
:030220004C20026D
:063FFA002002000220027B
:00000001FF
```

`TSX` is what makes this readable: the write addresses alone do **not** separate the candidates
(`RTS` restores S, so the `PHA` lands on `$01FF` either way). Watch the two data bytes written to
`$0300` (768) and `$0301` (769) in `/trace`:

| | `$0300` = S after `JSR` | `$0301` = S after `PHA` | verdict |
|---|---|---|---|
| healthy | `FD` | `FE` | the `-2` is gone |
| **Q1804 open** | **`FD`** | **`FD`** | **JSR clean, PHA doubled — Q1804 confirmed** |
| Q442/Q443 open | `FB` | `00` (derailed) | the ADL-side pair instead |
| Q71/Q72 open | `FA` | `00` (derailed) | the SB→ALU pair instead |

The stack-write addresses corroborate: healthy and Q1804 both give `01FF, 01FE, …, 01FF`, while
Q442/Q443 gives `01FE, 01FD, …` and Q71/Q72 gives `01FF, 01FD, …`.

- **`FD` then `FD`** → **Q1804 confirmed.** JSR is clean, only the ALU-path decrement doubles, and
  the rework target is one transistor at (71.35, 191.80).
- **`FB` or `FA` in `$0300`** → the JSR pushes are wrong too, Q1804 is exonerated, and the target
  is instead Q442/Q443 (`ADL/ADD` bit 0, F.Cu, x 82.45, y 180.6 / 183.4) or Q71/Q72 (`SB/ADD`
  bit 0, F.Cu, x 86.15 / 82.45, y 191.8 / 189.0).
- Anything else → all five candidates are wrong and this note's localisation fails.

A second, cheaper confirmation with no assembler: **BRK should step by 2 on all three of its
pushes** under Q1804 (`01FF, 01FD, 01FB`). The `−2, −1` sequences in the earlier decimal captures
do **not** match any of the five candidates; those runs also carried the intermittent `ab2` fault,
and `docs/stack-decrement-defect.md` already says not to overfit to them. Worth re-taking cleanly.

### The electrical check, if you have the scope out anyway

Q1804 is on the top face at **(71.35, 191.80)**, and its job is visible directly: **`sb0` must be
pulled to VCC once per clock phase.** A scope on the `sb0` side of Q1804 should show a full-swing
precharge every cycle; a dead or resistive joint shows it sitting low or crawling. Continuity from
Q1804 pin 3 to the VCC plane and pin 2 to the `sb0` net is the DC version of the same test.

---

## Which of the two explanations this supports

**Fab defect, not the driver-contention ratio bug.** The polarity is wrong for contention:

- The ratio bug makes a net **read HIGH when it should read LOW** (a contended node sits at
  1.0–1.9 V against a 1.1–1.5 V threshold). Forcing that behaviour on `sb0` — and on each of the
  other 99 VCC-side sites reachable in the die netlist — was simulated, and **none of them
  produces a double decrement.** `sb0` contending high came out *healthy*.
- What is needed here is the opposite: `sb0` **failing to reach HIGH**.
- It is also frequency-independent from 2 kHz to 16.7 kHz, which fits a precharge that simply
  never happens. A *resistive* joint would precharge given enough time and the fault would vanish
  at low clock. It does not. That argues for a hard open.

**Consequence: board #1 only, and the fix is a reflow or replacement of one SOT-323.** The other
three boards should be unaffected, and the sixteen-site `adh`/`adl` rework is unrelated to this —
it remains a heat fix.

**This also corrects the "not the ratio bug" argument in `docs/stack-decrement-defect.md`, which
had been retracted.** That note first localised on bit-0 specificity, then withdrew it after DEX
came back clean, concluding `-2` was "a clean whole-byte double decrement, not a bit fault" and
that the contention bug was back as the leading explanation. **Both halves are reconcilable:** it
*is* a bit-0 fault, in the *operand*, and it produces a clean whole-byte `−2` because `$FE` is a
perfectly good subtrahend — the borrow chain works fine. DEX survives because its `$FF` comes from
a different bus. The earlier note reached `sb0` and rejected it on the arithmetic that `sb0` stuck
**HIGH** would prevent decrementing altogether; that is true, and the actual fault is `sb0` stuck
**LOW**, which it did not test.

---

## Caveats

- **Switch-level only.** The model cannot tell an open joint from a weak one, or from a cracked
  part, or from a via-in-pad void under Q1804's VCC pad. It says *which node's high level is
  missing*, not *why*.
- **The stuck-ON half of the FET sweep did not actually run.** Tying a gate to VCC does not turn
  the FET on in `switchsim`'s incremental recalc (the VCC node never changes state, so the gate
  update never fires), so both sweep modes tested opens. **Shorted/always-conducting FETs are
  therefore unswept**, and the "5 hits out of 3,236" uniqueness claim covers opens only.
- The `other` bucket of each sweep was classified by the first two stack-write addresses only; a
  fault that produces the right addresses via a wildly different route would have been counted,
  and one that gets there after extra writes would have been missed.
- `JSR` being unaffected is an observation from the simulator, offered as a prediction. It is the
  load-bearing part of the bench test — if it does not hold on hardware, this localisation is
  wrong, and that is the point of running it.

---

## Reproducing the analysis

Scripts live in this session's scratchpad (outside the repo, so nothing was added to `tools/`):

```
/private/tmp/claude-501/-Users-epatel-Development-claude-monster6502v2/<session>/scratchpad/
  faultsim.py    Sim subclass with forced nodes + the PHA/DEX/INX/PLA test image
  sweep.py       stuck-at sweep over every node          (156 s, 8 cores)
  fetsweep.py    open-FET sweep over every transistor    (243 s, 8 cores)
  contend.py     "contention reads HIGH" over the 164 VCC-side sites (3 s)
  sbtest.py      SB/IDB precharge failure models         <- the hit
  operands.py    half-cycle dump of ALU operands and controls
  battery.py     the eight-program discriminator table
```

They import `tools/switchsim.py` unmodified and read `gen/netlist.json` and
`data/visual6502/` read-only. Promote whichever are worth keeping into `tools/`.

---

## Appendix: the phase structure, which is what the hint was about

Two facts fell out while chasing this, both verified against `data/visual6502/transdefs.js` and
reproduced in `gen/netlist.json` (so they are the die's design, not our transform):

**1. SB and IDB are precharged by `cclk`, once per phase, with one FET per bit and no pull-up
resistor.** That precharge is not merely a bus idle state — the stack decrement *reads it as the
number `$FF`*. It is the only place in the CPU where a bus's precharge is used as an arithmetic
operand, and it is why a single missing precharge FET shows up as an off-by-one in arithmetic
rather than as corrupt data.

**2. S is the odd register out in how the clock protects it.** The hold path of every other
register is gated by `cclk` *directly*; S's is gated by a decoded control line:

| register | hold path | gated by |
|---|---|---|
| A | `a0 – n146` | **`cclk`** |
| X | `x0 – n1169` | **`cclk`** |
| Y | `y0 – n564` | **`cclk`** |
| **S** | `s0 – n332` | **`dpc7_SS`** (a decode output) |

And of the 44 datapath control lines, 18 carry a `cclk`-gated pull-down that forces them low every
other phase. `dpc4_SSB` (S→SB) and `dpc5_SADL` (S→ADL) are **the only two register-source controls
with no clock qualification at all** — every other register's path to SB (`X/SB`, `Y/SB`, `AC/SB`)
is clock-gated.

So for A, X and Y the clock itself makes "holding" and "loading" physically exclusive; for S the
exclusion is only combinational logic. **That did not turn out to be the cause here** — no
simulated fault on those lines reproduces the symptom — but it is a real single-point-of-failure
in the S path, it is worth knowing before the next puzzling stack result, and it is the reason the
friend's instinct pointed in a productive direction.
