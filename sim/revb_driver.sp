* discrete6502: does the rev B series resistor fix contention WITHOUT breaking
* the driver it is inserted into?
*
* WHY THIS DECK EXISTS (2026-08-01). sim/driver_contention.sp measured the bug:
* a VCC-side FET fighting a pull-down draws 262 mA and holds its node at 1.86 V
* against a 1.1-1.5 V receiver threshold -- a ratio error, because the transform
* gave the load the SAME BSS138W as the pull-down. The proposed fix (rev B,
* DISCRETE6502_REV_B=1 in tools/gen_netlist.py, 142 sites) puts a resistor in
* series with the pull-up FET's drain:
*
*        rev A                          rev B
*     VCC ---- d                   VCC --[Rs]-- d
*              M_up (g = dor)                   M_up (g = dor)
*              s ---- OUT                       s ---- OUT
*              |                                |
*        pull-downs                       pull-downs
*
* That change was argued for on paper and gated only by tools/switchsim.py --
* which, as cards/verification.md now records, resolves ANY contention as low
* and is therefore structurally blind to exactly this class of defect. It can
* confirm rev B did not break the topology; it cannot confirm the levels. This
* deck supplies the levels.
*
* THE CHAIN SIMULATED IS A REAL ONE, taken from gen/netlist.json rather than
* invented, and it is deliberately two stages deep so the fix is judged by what
* comes OUT of the CPU, not just by the node it is applied to:
*
*   dor1 --gate--> Q401 (t333, vcc_side)  --> n798   [rev B: R21 = 10k]
*                  Q1722 (g = n288)       pull-downs on n798
*                  Q1867 (g = RnWstretched)
*   n798 --gate--> Q192 (t154, vcc_side)  --> db1    [rev B: R12 = 10k]
*                  Q3910 (g = n794)       pull-down on db1
*   db1  --gate--> Q5, Q460 (2 internal gates) + edge pad TP18 + R1228 (1k) to
*                  the Pico. db1 is DATA BUS BIT 1: an actual chip output.
*
* n798 is one of the eight nets tools/switchsim.py found contended 47-93% of
* the time (90% for this one), because RnWstretched holds Q1867 on through
* every read while a stale dor1 holds Q401 on.
*
* FOUR QUESTIONS, in the order that decides whether rev B is right:
*   Q1 does the contention current actually collapse?
*   Q2 does the contended node reach a VALID low (the functional half of the bug)?
*   Q3 does the stage still SWITCH inside a half-cycle -- i.e. did we trade a
*      current problem for a speed problem? This is the one that could kill it:
*      the pull-up is now a 0.5 mA source charging real gate capacitance.
*   Q4 do the 0402 resistors themselves survive? 142 sites, and 7 of them are
*      not 10k (5 x 1k, 2 x 100R on cclk/cp1 where 10k would destroy the clock).
*      A 100R in this position dissipates ~50x more than a 10k does.
*
* ======================== RESULT (2026-08-01) ========================
* VERDICT: rev B works, and it is not a trade -- it improves every figure it
* touches. It is not free: see the 100R caveat at the bottom.
*
* Q1/Q2 CONTENTION, VCC = 5 V, pull-down fully on, per contended net:
*
*   Vdor      rev A I     rev B I      rev A V(n798)   rev B V(n798)
*   3.5 V     172 mA      0.499 mA        1.023 V        0.0029 V
*   4.0 V     217 mA      0.499 mA        1.295 V        0.0029 V
*   4.5 V     262 mA      0.499 mA        1.574 V        0.0029 V
*   5.0 V     308 mA      0.499 mA        1.859 V        0.0029 V
*   (3.3 V: 224 mA -> 0.330 mA, 1.559 V -> 0.0021 V at Vdor = 4.5)
*
*   Current falls by 525x and is now flat in gate voltage, which is the real
*   tell: the resistor, not the FET, sets it. 262 mA was over the BSS138W's
*   220 mA rating; 0.5 mA is the same 10k load the other 1,018 nodes already
*   have. The level goes from 1.86 V -- ambiguous against a 1.1-1.5 V receiver
*   threshold, i.e. the CPU could read HIGH when it should read LOW -- to 2.9 mV,
*   which is unambiguous. Both halves of the defect are fixed, and the
*   functional half was the more dangerous one.
*
*   For the board: the eight measured contended nets go from +1.76 A / +8.8 W
*   to +4 mA / +20 mW, i.e. back to the 0.32 A / 1.6 W the plan used to claim.
*
* Q3 SWITCHING, one 25 us half-cycle at the 20 kHz ceiling, VCC = 5 V:
*
*                          rev A      rev B     rev A worst-Vth  rev B worst-Vth
*   n798 high level       4.466 V    5.019 V       4.068 V          4.629 V
*   db1  high level       3.811 V    4.377 V       3.014 V          3.587 V
*   db1  rise (to 1.5 V)   18 ns      271 ns        14 ns            275 ns
*   db1  fall              2.8 ns     2.7 ns
*   peak supply current   346 mA     0.92 mA
*
*   Rise slows by 15x and is still 90x inside the 25 us budget, so the speed
*   worry does not survive measurement. The fall is untouched, as expected --
*   no series resistor is in the pull-down path.
*
*   THE HIGH LEVELS GO UP, WHICH LOOKS WRONG AND IS NOT. Probed node by node:
*   db1 rising couples back into n798 through the second FET's Cgs (21 pF),
*   the ordinary bootstrap of cards/pass-pair-validation.md. In rev A the
*   pull-up's drain is a stiff VCC, so the moment n798 is pushed above VCC the
*   FET conducts backwards and dumps that charge straight into the supply. In
*   rev B the same path is 10k, so the charge is kept and bleeds off with a
*   10k*C time constant (n798 is seen decaying 5.16 -> 5.10 V over 45 us).
*   Rev B preserves bootstrap charge that rev A throws away. Treat this as a
*   bonus, NOT as something to depend on: it scales with the next stage's Cgs.
*
* Q3 at VCC = 3.3 V, worst-case Vth -- the corner that decides 3.3 V bring-up:
*
*                          rev A worst-Vth        rev B worst-Vth
*   db1 high level             1.306 V                1.579 V
*   db1 rise to 1.5 V       NEVER GETS THERE          16.9 us
*
*   Two source followers in series subtract Vth twice, and at 3.3 V with
*   Vto = 1.5 V (the datasheet max) that is enough to put the data bus output
*   below the threshold of the gate it drives. This is a PRE-EXISTING rev A
*   weakness, not something rev B introduces -- chain E exists in this deck
*   precisely so the comparison cannot blame it on rev B -- and rev B is the
*   one that clears the threshold. Independent support for the plan's existing
*   position that 3.3 V is the tighter operating point, not the safer one.
*
* Q3b PAD CAPACITANCE. cpad = 50 pF is an estimate for the 11.6 mm bond pad
*   plus its trace, so it was swept: 20 pF -> 500 pF moves db1's rise from
*   207 ns to 1.41 us and the high level not at all. The estimate does not
*   have to be right; nothing here is near the budget.
*
* Q3c THE CLOCK -- cclk, 482 gates = 13 nF, the one rev B site that could
*   break the CPU rather than one driver (rev B gives it 100R, not 10k, and
*   10k there would be 286 us and fatal):
*
*                      rev A        rev B
*   high level        4.143 V      4.141 V     (unchanged)
*   contended low     1.859 V      0.262 V     (invalid -> valid)
*   rise 2.0->3.5 V    226 ns       979 ns     (25x inside a 25 us half-cycle)
*   fall               140 ns       140 ns     (identical)
*
*   Rev B does not break the clock. It fixes cclk's low level too.
*
* Q4 THE RESISTORS THEMSELVES, contended at 5 V -- the one real caveat:
*
*   value   count   I          P          0402 rating 0.0625 W
*   10k      135    0.50 mA    2.5 mW     4% of rating           fine
*   1k         5    4.94 mA   24.4 mW     39% of rating          fine
*   100R       2    44.7 mA  200.1 mW     320% OF RATING         see below
*
*   The two 100R parts are cclk and cp1. Averaged over normal running this is
*   not a problem: contention there is transient (about 1 us per edge at
*   20 kHz, ~4% duty, so ~8 mW mean). It becomes a problem in exactly one
*   situation -- A STOPPED CLOCK WITH cclk PARKED CONTENDED, which is what the
*   tester's retention test (w/W) deliberately creates. So if rev B is ever
*   fabricated: put those two sites in 0805 (0.125 W) or accept that the
*   stall test must stay sub-millisecond there. All 142 resistors contending
*   at once would total 0.86 W, which the board carries easily.
*
* WHAT THIS DECK DOES NOT PROVE: one chain out of 142, chosen because it is
* the worst-measured contender. It shows the fix is sound and the speed cost
* is affordable; it does not show every site is safe.

.include 2N7002_onsemi.lib

* Same calibration as sim/driver_contention.sp: Rd=Rs=2.6 puts RDS(on) on the
* BSS138W datasheet figure of 6.0 ohm at Vgs = 4.5 V. This deck is
* resistance-dominated at DC and capacitance-dominated in the transient, so it
* needs both fitted; Cgs=21p/Cgd=6p is the datasheet Ciss = 27 pF split.
.model MB11 VDMOS(Vto=1.1 Kp=0.4 Rd=2.6 Rs=2.6 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)
.model MB15 VDMOS(Vto=1.5 Kp=0.4 Rd=2.6 Rs=2.6 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)

.param vsup=5.0
* rev B series R on n798  (R21, gate_load 1)
.param rs1=10k
* rev B series R on db1   (R12)
.param rs2=10k
* db1 edge pad + 290 mm trace over a plane. ESTIMATE,
.param cpad=50p
* deliberately pessimistic; swept at the end.

Vdd   VDD 0 {vsup}
* RnWstretched: the pull-down gate on n798
Vgdn  GDN 0 0
* dor1: the pull-up gate on n798
Vdor  DOR 0 0
* n794: the pull-down gate on db1
Vgdn2 GD2 0 0

* ==================================================================
*  A) rev A chain -- pull-up drain hard on VCC (what is in the fab)
* ==================================================================
VsA VDD VA 0
* Q401
MA1up VA  DOR NA MB11
* Q1867
MA1dn NA  GDN 0  MB11
* Q1722, gate n288 held low = off
MA1d2 NA  0   0  MB11
* Q192, gate = n798
MA2up VA  NA  DA MB11
* Q3910
MA2dn DA  GD2 0  MB11
* Q5   -- real gate, real Cgs/Cgd
MA2L1 0   DA  0  MB11
* Q460
MA2L2 0   DA  0  MB11
CApad DA  0  {cpad}
* R1228 to the Pico pin
RApic DA  PA 1k
CApic PA  0  5p

* ==================================================================
*  B) rev B chain -- same devices, series resistor added
* ==================================================================
VsB VDD VB 0
* R21
RB1   VB  MB1 {rs1}
MB1up MB1 DOR NB MB11
MB1dn NB  GDN 0  MB11
MB1d2 NB  0   0  MB11
* R12
RB2   VB  MB2 {rs2}
MB2up MB2 NB  DB MB11
MB2dn DB  GD2 0  MB11
MB2L1 0   DB  0  MB11
MB2L2 0   DB  0  MB11
CBpad DB  0  {cpad}
RBpic DB  PB 1k
CBpic PB  0  5p

* ==================================================================
*  C) worst-Vth copy of the rev B chain (Vto = 1.5, datasheet max).
*     Vth is subtracted from the source-follower's output TWICE down
*     this chain, so it is the level-critical corner, not the current one.
* ==================================================================
VsC VDD VC 0
RC1   VC  MC1 {rs1}
MC1up MC1 DOR NC MB15
MC1dn NC  GDN 0  MB15
MC1d2 NC  0   0  MB15
RC2   VC  MC2 {rs2}
MC2up MC2 NC  DC MB15
MC2dn DC  GD2 0  MB15
MC2L1 0   DC  0  MB15
MC2L2 0   DC  0  MB15
CCpad DC  0  {cpad}
RCpic DC  PC 1k
CCpic PC  0  5p

* ==================================================================
*  E) worst-Vth copy of the rev A chain. Without this the comparison is
*     unfair: two source followers in series subtract Vth TWICE, which at
*     3.3 V is marginal on its own, and chain C alone would let that
*     pre-existing weakness be blamed on rev B.
* ==================================================================
VsE2 VDD VE2 0
ME1up VE2 DOR NE MB15
ME1dn NE  GDN 0  MB15
ME1d2 NE  0   0  MB15
ME2up VE2 NE  DE MB15
ME2dn DE  GD2 0  MB15
ME2L1 0   DE  0  MB15
ME2L2 0   DE  0  MB15
CEpad DE  0  {cpad}
REpic DE  PE 1k
CEpic PE  0  5p

* ==================================================================
*  D) isolated series resistors, for the dissipation question (Q4).
*     One contended pull-up per BOM value actually used by rev B.
* ==================================================================
VsD VDD VD 0
RD10k VD  MD1 10k
MD1up MD1 DOR ND1 MB11
* pull-down hard on
MD1dn ND1 VDD 0   MB11
VsE VDD VE 0
RD1k  VE  MD2 1k
MD2up MD2 DOR ND2 MB11
MD2dn ND2 VDD 0   MB11
VsF VDD VF 0
RD100 VF  MD3 100
MD3up MD3 DOR ND3 MB11
MD3dn ND3 VDD 0   MB11

* ==================================================================
*  F) the highest-consequence rev B site: cclk. 482 gates = 13 nF behind a
*     100R series resistor. This is where rev B could plausibly break the
*     whole CPU rather than one driver, so it gets its own comparison.
*     cp1 (198 gates, 5.4 nF, also 100R) is the milder twin.
* ==================================================================
VsG VDD VG 0
MG1up VG  DOR NG MB11
MG1dn NG  GDN 0  MB11
CGclk NG  0   13n
VsH VDD VH 0
RH1   VH  MH1 100
MH1up MH1 DOR NH MB11
MH1dn NH  GDN 0  MB11
CHclk NH  0   13n

.control
set wr_singlescale

foreach sup 5.0 3.3
  alterparam vsup = $sup
  reset
  alter Vgdn  = $sup                $ RnWstretched HIGH: pull-down fully on
  alter Vgdn2 = 0
  dc Vdor 0 6.05 0.05

  echo ""
  echo "=================================================================="
  echo " Q1/Q2  CONTENTION at VCC = $sup V -- pull-down on, pull-up swept"
  echo "=================================================================="
  echo " Vdor is the pull-up's gate. It is a dynamic node, so the realistic"
  echo " band is VCC-Vth (driven through a pass gate) to about VCC+0.5"
  echo " (clock-edge bootstrap, cards/pass-pair-validation.md)."
  echo ""
  echo "   revA_I / revB_I  = supply current drawn by the whole 2-stage chain"
  echo "   revA_V / revB_V  = level on n798 while it is being contended"
  echo "   a receiving gate switches at Vth = 1.1 V (typ) .. 1.5 V (max)"

  let ia = abs(i(VsA))
  let ib = abs(i(VsB))
  let ic = abs(i(VsC))

  foreach g 3.5 4.0 4.5 5.0
    echo ""
    echo "  ---- Vdor = $g V ----"
    meas dc revA_I_A  find ia    when v(DOR)=$g
    meas dc revB_I_A  find ib    when v(DOR)=$g
    meas dc revA_V_V  find v(NA) when v(DOR)=$g
    meas dc revB_V_V  find v(NB) when v(DOR)=$g
    meas dc revAwo_V  find v(NE) when v(DOR)=$g
    meas dc revBwo_V  find v(NC) when v(DOR)=$g
  end
end

* ---------------- Q4: what the resistor itself has to survive ----------------
alterparam vsup = 5.0
reset
alter Vgdn = 5.0
dc Vdor 0 6.05 0.05
echo ""
echo "=================================================================="
echo " Q4  DISSIPATION IN THE SERIES RESISTOR ITSELF, contended, VCC = 5 V"
echo "=================================================================="
echo " 0402 thick film is rated 0.0625 W (some ranges 0.1 W). rev B uses"
echo " 135 x 10k, 5 x 1k, 2 x 100R -- the 100R pair is cclk and cp1, where"
echo " 10k would give a 286 us rise and destroy the clock."
let p10 = abs(i(VsD))*(v(VDD)-v(MD1))
let p1k = abs(i(VsE))*(v(VDD)-v(MD2))
let p100 = abs(i(VsF))*(v(VDD)-v(MD3))
let i10 = abs(i(VsD))
let i1k = abs(i(VsE))
let i100 = abs(i(VsF))
foreach g 4.5 5.0
  echo ""
  echo "  ---- Vdor = $g V ----"
  meas dc I_10k_A   find i10  when v(DOR)=$g
  meas dc P_10k_W   find p10  when v(DOR)=$g
  meas dc I_1k_A    find i1k  when v(DOR)=$g
  meas dc P_1k_W    find p1k  when v(DOR)=$g
  meas dc I_100R_A  find i100 when v(DOR)=$g
  meas dc P_100R_W  find p100 when v(DOR)=$g
end

* -------- Q3: does the stage still switch inside a half-cycle? --------
* One full cycle at the measured 20 kHz ceiling: 25 us half-period.
*   t = 0..5 us    the bug's own condition -- RnWstretched high AND dor1 high,
*                  so n798 is contended; db1's pull-down (n794) is on too, which
*                  is what defines db1 low and gives the rising edge below a
*                  real starting point instead of an operating-point accident.
*   t = 5 us       both pull-downs release: the chain must now drive db1 HIGH
*                  through the rev B resistors, and that is the speed question.
*   t = 55 us      dor1 falls and both pull-downs return: the falling edge,
*                  which no series resistor is in the path of.
foreach sup 5.0 3.3
  alterparam vsup = $sup
  reset
  alter Vdor  pwl = [ 0 $sup  55u $sup  55.1u 0  80u 0 ]
  alter Vgdn  pwl = [ 0 $sup  5u  $sup  5.1u  0  55u 0  55.1u $sup  80u $sup ]
  alter Vgdn2 pwl = [ 0 $sup  5u  $sup  5.1u  0  55u 0  55.1u $sup  80u $sup ]
  tran 20n 80u

  echo ""
  echo "=================================================================="
  echo " Q3  SWITCHING at VCC = $sup V -- 25 us half-cycle (20 kHz)"
  echo "=================================================================="
  echo " db1 is the data bus output pad: 2 internal gates + {cpad} pad/trace"
  echo " + 1k to the Pico. If rev B traded current for speed, it shows here."

  meas tran A_n798_hi   MAX v(NA) from=5u to=55u
  meas tran B_n798_hi   MAX v(NB) from=5u to=55u
  meas tran E_n798_hi   MAX v(NE) from=5u to=55u
  meas tran C_n798_hi   MAX v(NC) from=5u to=55u
  meas tran A_db1_hi    MAX v(DA) from=5u to=55u
  meas tran B_db1_hi    MAX v(DB) from=5u to=55u
  meas tran E_db1_hi    MAX v(DE) from=5u to=55u
  meas tran C_db1_hi    MAX v(DC) from=5u to=55u
  echo " (final levels above; rise times below, measured to 1.5 V --"
  echo "  the datasheet-max threshold the next gate must be taken past)"
  meas tran A_db1_rise  TRIG v(DA) VAL=0.5 RISE=1 TARG v(DA) VAL=1.5 RISE=1
  meas tran B_db1_rise  TRIG v(DB) VAL=0.5 RISE=1 TARG v(DB) VAL=1.5 RISE=1
* E_db1_rise is EXPECTED TO FAIL at 3.3 V, and the failure is the finding:
* rev A at worst-case Vth never takes db1 past 1.5 V at all (it stops at
* 1.306 V), so there is no crossing to measure. Do not "fix" this measurement.
  meas tran E_db1_rise  TRIG v(DE) VAL=0.5 RISE=1 TARG v(DE) VAL=1.5 RISE=1
  meas tran C_db1_rise  TRIG v(DC) VAL=0.5 RISE=1 TARG v(DC) VAL=1.5 RISE=1
* 2.0 -> 2.5 V, not 0.5 -> 1.5: in rev A this node never reaches 0.5 V,
* because contention parks it at 1.02-1.86 V. That is the bug, not a bad probe.
* The window is narrow so that it is traversed at BOTH rails, 5 V and 3.3 V.
  meas tran A_n798_rise TRIG v(NA) VAL=2.0 RISE=1 TARG v(NA) VAL=2.5 RISE=1
  meas tran B_n798_rise TRIG v(NB) VAL=2.0 RISE=1 TARG v(NB) VAL=2.5 RISE=1
  echo " and the falling edge, which the series resistor is NOT in the path of:"
  meas tran A_db1_fall  TRIG v(DA) VAL=1.5 FALL=1 TARG v(DA) VAL=0.5 FALL=1
  meas tran B_db1_fall  TRIG v(DB) VAL=1.5 FALL=1 TARG v(DB) VAL=0.5 FALL=1
  echo " peak supply current over the whole cycle (rev A vs rev B):"
  let ia = abs(i(VsA))
  let ib = abs(i(VsB))
  meas tran A_Ipk_A     MAX ia from=0 to=80u
  meas tran B_Ipk_A     MAX ib from=0 to=80u
end

* ---- Q3c: does rev B break the clock? cclk = 13 nF behind 100R ----
alterparam vsup = 5.0
reset
alter Vdor pwl = [ 0 5 55u 5 55.1u 0 80u 0 ]
alter Vgdn pwl = [ 0 5 5u 5 5.1u 0 55u 0 55.1u 5 80u 5 ]
alter Vgdn2 = 0
tran 20n 80u
echo ""
echo "=================================================================="
echo " Q3c THE CLOCK NET -- cclk, 482 gates = 13 nF, rev B series R = 100R"
echo "=================================================================="
echo " The single site where rev B could break the CPU rather than one"
echo " driver. Budget: a 25 us half-cycle at the 20 kHz ceiling."
meas tran cclk_A_hi   MAX v(NG) from=5u to=55u
meas tran cclk_B_hi   MAX v(NH) from=5u to=55u
* NOTE the trigger levels: rev A cannot be measured from 0.5 V, because in rev A
* this node never GETS to 0.5 V -- contention parks it at ~1.86 V, which is the
* bug itself. 2.0 -> 3.5 V is the widest window both revisions actually traverse.
meas tran cclk_A_rise TRIG v(NG) VAL=2.0 RISE=1 TARG v(NG) VAL=3.5 RISE=1
meas tran cclk_B_rise TRIG v(NH) VAL=2.0 RISE=1 TARG v(NH) VAL=3.5 RISE=1
meas tran cclk_A_low  MIN v(NG) from=1u to=5u
meas tran cclk_B_low  MIN v(NH) from=1u to=5u
meas tran cclk_A_fall TRIG v(NG) VAL=3.0 FALL=1 TARG v(NG) VAL=0.5 FALL=1
meas tran cclk_B_fall TRIG v(NH) VAL=3.0 FALL=1 TARG v(NH) VAL=0.5 FALL=1

* -------- Q3b: how much pad capacitance would rev B actually tolerate? -------
* cpad = 50p is an estimate, so find the point where the estimate would matter.
alterparam vsup = 5.0
echo ""
echo "=================================================================="
echo " Q3b SENSITIVITY -- db1 high level and rise vs assumed pad capacitance"
echo "=================================================================="
foreach cp 20p 50p 100p 200p 500p
  alterparam cpad = $cp
  reset
  alter Vdor  pwl = [ 0 5  55u 5  55.1u 0  80u 0 ]
  alter Vgdn  pwl = [ 0 5  5u  5  5.1u  0  55u 0  55.1u 5  80u 5 ]
  alter Vgdn2 pwl = [ 0 5  5u  5  5.1u  0  55u 0  55.1u 5  80u 5 ]
  tran 20n 60u
  echo ""
  echo "  ---- cpad = $cp ----"
  meas tran db1_hi   MAX v(DB) from=5u to=55u
  meas tran db1_rise TRIG v(DB) VAL=0.5 RISE=1 TARG v(DB) VAL=1.5 RISE=1
end

echo ""
echo "=================================================================="
echo "READ AGAINST"
echo "  BSS138W (JSCJ C504052): 220 mA continuous, SOT-323 about 0.3 W."
echo "  0402 thick film: 0.0625 W (some ranges 0.1 W)."
echo "  Receiving gate threshold: 1.1 V typ, 1.5 V datasheet max."
echo "  Half-cycle at the measured 20 kHz ceiling: 25 us."
.endc
.end
