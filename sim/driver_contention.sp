* discrete6502: how much current flows when a VCC-side FET fights a pull-down?
*
* WHY THIS DECK EXISTS (2026-08-01). The transform turned the 6502's depletion
* LOADS into 10k resistors (1,018 of them, 0.5 mA each -- safe). It did NOT
* touch the enhancement-mode transistors whose channel sits on VCC: 164 parts
* across 269 nets, role "vcc_side" in gen/netlist.json. Those are push-pull
* stages -- bus output drivers and clock superbuffers -- and a switch-level run
* of the real netlist (tools/switchsim.py) shows 5-8 of them at any moment with
* the VCC-side FET and a pull-down FET BOTH conducting on the same net, all the
* way through normal execution, not merely at power-on:
*
*   nets seen contended: dor1..dor5 vs RnWstretched (data bus out drivers),
*   adh1..adh6 (address high), n42/n373/n520/n798/n1076 ... 0-13 at a time,
*   median about 5, over 120 half-cycles of the test program.
*
* That is ordinary ratioed-NMOS behaviour and the original die does it too --
* but on-die channel resistance is kohms, while a BSS138W is ~6 ohm. Eric
* Schlaepfer hit exactly this on the MOnSter 6502 and had to add protective
* resistors between pullup and pulldown; those resistors are also what caps his
* clock speed. We have no such resistors, and the boards are already in fab.
*
* Switch-level simulation is binary: it says "both on", it cannot say how many
* milliamps. This deck answers that, and answers the only question that matters
* before first power-up: does a contended net destroy its FETs, or is it a
* current we can simply budget for?
*
* Topology (one contended net):
*
*      VDD ---- d
*               M_up  (gate = GUP, a source follower: source IS the output)
*               s ----+---- OUT
*                     |
*               d ----+
*               M_dn  (gate = GDN, held at VCC: the pull-down is fully on)
*               s ---- 0
*
* GUP is swept, because the pull-up's gate is a DYNAMIC node and its high level
* is not obvious: driven through a pass gate it lands near VCC-Vth, and the
* clock-edge bootstrap documented in cards/pass-pair-validation.md can push it
* AT or ABOVE VCC. The honest answer therefore spans that range.
*
* ============================ RESULT (2026-08-01) ============================
* Per contended net, pull-down fully on:
*
*   Vgup    I (typ Vth)   P in the upper FET   Vout      I (vendor model)
*   3.5 V     172 mA          0.69 W           1.02 V        138 mA
*   4.0 V     217 mA          0.80 W           1.29 V        217 mA
*   4.5 V     262 mA          0.90 W           1.57 V        300 mA
*   5.0 V     308 mA          1.00 W           1.86 V           -
*   (at 3.3 V: 224 mA and 0.39 W at 4.5 V gate)
*
* Calibration confirmed by the data itself: at Vgup = 5 V, Vout/I = 1.86/0.308
* = 6.0 ohm, exactly the BSS138W datasheet RDS(on).
*
* TWO CONSEQUENCES, and the second is worse than the first.
*
* 1. THERMAL. Against 220 mA continuous and ~0.3 W in SOT-323, the current is
*    over at >=4 V drive and the dissipation is over EVERYWHERE in the band.
*    Cross-referenced with switchsim duty cycles (8 nets contended 47-93% of
*    the time, mean 6.7 at once) that is +1.76 A and +8.8 W at 5 V, taking the
*    board to ~2.1 A / ~10.4 W against a recorded budget of 0.32 A / 1.6 W.
*    The MOnSter 6502 is published at 5 V, ~2 A, ~10 W -- same logic, same
*    style. Our 1.6 W figure was the outlier and nobody questioned it.
*
* 2. LOGIC LEVEL. The contended node does not sit at a valid low: Vout is
*    1.02 V at 3.5 V gate drive and 1.86 V at 5 V, against a receiving gate
*    threshold of 1.1-1.5 V. The stage may therefore read HIGH when it should
*    read LOW. This is a ratio failure, not just a heat problem.
*
* ROOT CAUSE: the transform preserved topology but NOT device ratios. Ratioed
* NMOS needs the pull-down several times stronger than the load. The 1,018
* depletion loads became 10k resistors, so their ratio (10k against 6 ohm) is
* fine. The 164 enhancement-mode VCC-side FETs kept the SAME BSS138W as their
* pull-down -- a 1:1 ratio where the die had a deliberately weak load.
*
* FIX (see project-plan.md "Driver contention"): 10k in series with each
* pull-up FET restores the ratio exactly like the other 1,018 nodes: 0.5 mA
* instead of 262 mA, Vout ~3 mV instead of 1.86 V, and the rise stays fast
* because each of these 8 nets drives exactly ONE gate (27 pF, so 2.2*10k*27p
* = 0.6 us against a 25 us half-cycle).

.include 2N7002_onsemi.lib

* Model flavours. NOTE THE CALIBRATION: the other decks in sim/ use Rd=Rs=1,
* which is fine there because those questions are capacitance-dominated. THIS
* question is resistance-dominated, so the hand models are re-fitted here to
* the BSS138W datasheet figure, RDS(on) = 6 ohm at Vgs = 4.5 V. With Kp=0.4 the
* channel contributes ~0.75 ohm at that drive, so Rd = Rs = 2.6 lands on 6 ohm.
* Leaving Rd=Rs=1 would have overstated the current by roughly 2x -- the deck
* prints its own RDS(on) below so the calibration is visible, not assumed.
*   MB11 - BSS138W typical  (Vto 1.1)
*   MB15 - BSS138W worst    (Vto 1.5, the datasheet max)
* plus the onsemi vendor BSIM3v3 subckt as an independent cross-check.
.model MB11 VDMOS(Vto=1.1 Kp=0.4 Rd=2.6 Rs=2.6 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)
.model MB15 VDMOS(Vto=1.5 Kp=0.4 Rd=2.6 Rs=2.6 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)

.param vsup=5.0

Vdd  VDD 0 {vsup}
Vgdn GDN 0 {vsup}
Vgup GUP 0 0

* ---- typical-Vth pair ----
M1up VDD GUP O1 MB11
M1dn O1  GDN 0  MB11
* ---- worst-Vth pair ----
M2up VDD GUP O2 MB15
M2dn O2  GDN 0  MB15
* ---- vendor model pair (drain gate source) ----
X3up VDD GUP O3 F2N7002
X3dn O3  GDN 0  F2N7002

* Each pair needs its own supply sense so the currents separate.
Vs1 VDD V1 0
Vs2 VDD V2 0
Vs3 VDD V3 0
M1upB V1 GUP O1B MB11
M1dnB O1B GDN 0  MB11
M2upB V2 GUP O2B MB15
M2dnB O2B GDN 0  MB15
X3upB V3 GUP O3B F2N7002
X3dnB O3B GDN 0  F2N7002

.control
* ---- calibration: what RDS(on) does each model actually give at Vgs=4.5? ----
alterparam vsup = 4.5
reset
dc Vgup 4.5 4.55 0.05
echo ""
echo "=== calibration: RDS(on) at Vgs = 4.5 V (datasheet BSS138W = 6.0 ohm) ==="
* drive the pull-down gate at 4.5 and read the divider: each FET sees vsup/2
let rds_t = v(O1B)/abs(i(Vs1))
let rds_w = v(O2B)/abs(i(Vs2))
let rds_v = v(O3B)/abs(i(Vs3))
meas dc rds_typ   find rds_t when v(GUP)=4.5
meas dc rds_worst find rds_w when v(GUP)=4.5
meas dc rds_vend  find rds_v when v(GUP)=4.5
echo "(each figure is the LOWER fet's on-resistance: Vout / I)"

foreach sup 5.0 3.3
  alterparam vsup = $sup
  reset
  dc Vgup 0 6.05 0.05

  echo ""
  echo "=================================================================="
  echo "   VCC = $sup V   pull-down gate at VCC (fully on), pull-up swept"
  echo "=================================================================="
  echo "GUP is the pull-up's gate voltage. It is a DYNAMIC node, so the"
  echo "realistic band is VCC-Vth (driven through a pass gate) up to about"
  echo "VCC+0.5 (clock-edge bootstrap, see cards/pass-pair-validation.md)."
  echo ""
  echo "         I through the pair, and dissipation in the UPPER fet"
  echo "         (the one holding VCC-Vout across it while it conducts)"

  let itp = abs(i(Vs1))
  let iwo = abs(i(Vs2))
  let ive = abs(i(Vs3))
  let ptp = itp*(v(VDD)-v(O1B))
  let pdn = itp*v(O1B)

  foreach g 2.5 3.0 3.5 4.0 4.5 5.0 5.5
    echo ""
    echo "  ---- Vgup = $g V ----"
    meas dc i_typ_A     find itp    when v(GUP)=$g
    meas dc i_worst_A   find iwo    when v(GUP)=$g
    meas dc i_vendor_A  find ive    when v(GUP)=$g
    meas dc P_upper_W   find ptp    when v(GUP)=$g
    meas dc P_lower_W   find pdn    when v(GUP)=$g
    meas dc Vout_V      find v(O1B) when v(GUP)=$g
  end
end

echo ""
echo "=================================================================="
echo "READ AGAINST THE PART LIMITS"
echo "  BSS138W (JSCJ C504052): 220 mA continuous drain current."
echo "  SOT-323: roughly 0.3 W at 25 C on a normal footprint."
echo "A contended net holds BOTH its fets at these values for as long as the"
echo "contention lasts. tools/switchsim.py says that is most of the time,"
echo "on 5-8 nets at once, during ordinary execution."
.endc
.end
