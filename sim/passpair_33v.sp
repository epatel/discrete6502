* discrete6502 M6 pre-bring-up: does the dynamic pass-pair latch still work at VCC = 3.3 V?
*
* Why: the recommended first power-up runs the whole board at 3.3 V so the Pico and the
* CPU share one supply domain (no level-shifting questions).  The bootstrap mechanism that
* saves the stored '1' from the pass-gate threshold drop (see cards/pass-pair-validation.md)
* has only ever been checked at 5 V, where Vgs headroom is generous.  At 3.3 V a 1.5 V
* threshold eats 45% of the rail, so this must be verified, not assumed.
*
* Topology = the worst dynamic path from the M4 vendor testbench:
*   driver inverter -> pass pair (phi1) -> 20pF bus -> pass pair (phi2) -> 5pF storage node
*   (with LED-tap gate load) -> output inverter.
*
* Three FET flavours in parallel, all with the real 10k pull-ups:
*   _v = onsemi vendor BSIM3v3 2N7002 (F2N7002)   -- pessimistic: highest Vth of the three
*   _b = BSS138 typical  (VDMOS Vto=1.1)          -- the part we ordered, typical unit
*   _w = BSS138W worst   (VDMOS Vto=1.5)          -- the part we ordered, datasheet Vth max
*
* Supplies swept by the control block: 5.0 (baseline), 3.3 (proposed), 3.0 (margin probe).
* Run: cd sim && ngspice -b passpair_33v.sp

.include 2N7002_onsemi.lib

.model MBSS VDMOS(Vto=1.1 Kp=0.4 Rd=1 Rs=1 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)
.model MB15 VDMOS(Vto=1.5 Kp=0.4 Rd=1 Rs=1 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)

.param vsup=3.3

Vdd VDD 0 {vsup}
* phi1 closes 5-14us and 45-54us; phi2 closes 16-25us and 56-65us
Vp1 PHI1 0 PULSE(0 {vsup} 5u 100n 100n 9u 40u)
Vp2 PHI2 0 PULSE(0 {vsup} 16u 100n 100n 9u 40u)
* D low until 40us -> write '1'; D high after -> write '0'
Vd  D    0 PULSE(0 {vsup} 40u 100n 100n 40u 200u)

* ---------------- variant v: onsemi vendor 2N7002 model ----------------
Xdrv_v A_v D 0 F2N7002
Rpu1_v VDD A_v 10k
X1_v A_v   PHI1 MID1_v F2N7002
X2_v BUS_v PHI1 MID1_v F2N7002
CBUS_v BUS_v 0 20p
X3_v BUS_v PHI2 MID2_v F2N7002
X4_v STO_v PHI2 MID2_v F2N7002
CSTO_v STO_v 0 5p
Xled_v LEDK_v STO_v 0 F2N7002
Rled_v VDD LEDK_v 2.2k
Xout_v OUT_v STO_v 0 F2N7002
Rpu2_v VDD OUT_v 10k
COUT_v OUT_v 0 5p

* ---------------- variant b: BSS138 typical (Vto 1.1) ----------------
Mdrv_b A_b D 0 MBSS
Rpu1_b VDD A_b 10k
M1_b A_b   PHI1 MID1_b MBSS
M2_b BUS_b PHI1 MID1_b MBSS
CBUS_b BUS_b 0 20p
M3_b BUS_b PHI2 MID2_b MBSS
M4_b STO_b PHI2 MID2_b MBSS
CSTO_b STO_b 0 5p
Mled_b LEDK_b STO_b 0 MBSS
Rled_b VDD LEDK_b 2.2k
Mout_b OUT_b STO_b 0 MBSS
Rpu2_b VDD OUT_b 10k
COUT_b OUT_b 0 5p

* ---------------- variant w: BSS138W worst case (Vto 1.5) ----------------
Mdrv_w A_w D 0 MB15
Rpu1_w VDD A_w 10k
M1_w A_w   PHI1 MID1_w MB15
M2_w BUS_w PHI1 MID1_w MB15
CBUS_w BUS_w 0 20p
M3_w BUS_w PHI2 MID2_w MB15
M4_w STO_w PHI2 MID2_w MB15
CSTO_w STO_w 0 5p
Mled_w LEDK_w STO_w 0 MB15
Rled_w VDD LEDK_w 2.2k
Mout_w OUT_w STO_w 0 MB15
Rpu2_w VDD OUT_w 10k
COUT_w OUT_w 0 5p

.control
foreach sup 5.0 3.3 3.0
  alterparam vsup = $sup
  reset
  tran 0.02u 120u
  echo ""
  echo "================ VCC = $sup V ================"
  * write '1' path
  meas tran sto1_v  find v(STO_v) at=26u
  meas tran sto1h_v find v(STO_v) at=39u
  meas tran outlo_v find v(OUT_v) at=39u
  meas tran sto1_b  find v(STO_b) at=26u
  meas tran sto1h_b find v(STO_b) at=39u
  meas tran outlo_b find v(OUT_b) at=39u
  meas tran sto1_w  find v(STO_w) at=26u
  meas tran sto1h_w find v(STO_w) at=39u
  meas tran outlo_w find v(OUT_w) at=39u
  * write '0' path
  meas tran sto0_v  find v(STO_v) at=66u
  meas tran outhi_v find v(OUT_v) at=79u
  meas tran sto0_b  find v(STO_b) at=66u
  meas tran outhi_b find v(OUT_b) at=79u
  meas tran sto0_w  find v(STO_w) at=66u
  meas tran outhi_w find v(OUT_w) at=79u
  * driven transfers through ONE pass pair (what the 6502 actually relies on):
  * A is held by the driver inverter, so BUS sees a source-driven '1' then '0'.
  meas tran bus1_v  find v(BUS_v) at=15u
  meas tran bus0_v  find v(BUS_v) at=55u
  meas tran bus1_b  find v(BUS_b) at=15u
  meas tran bus0_b  find v(BUS_b) at=55u
  meas tran bus1_w  find v(BUS_w) at=15u
  meas tran bus0_w  find v(BUS_w) at=55u
  * LED tap cathode (driver saturation) and pull-up speed on the driver output
  meas tran led_w   find v(LEDK_w) at=39u
  * pull-up speed: D returns low at 80us, so the driver output A rises through 10k
  meas tran arise_v trig v(A_v) val='0.1*$sup' rise=1 td=80u targ v(A_v) val='0.9*$sup' rise=1 td=80u
  meas tran arise_w trig v(A_w) val='0.1*$sup' rise=1 td=80u targ v(A_w) val='0.9*$sup' rise=1 td=80u
  * charge retention on the stored '1' over a further 13us of hold
  meas tran sto1d_w find v(STO_w) at=52u

  * ---- pass/fail gates (the questions bring-up actually cares about) ----
  * 1. bootstrap still lifts the stored '1' to at least the rail
  if sto1h_v >= $sup
    echo "  PASS  bootstrapped '1' >= rail (vendor 2N7002, the pessimistic model)"
  else
    echo "  FAIL  bootstrapped '1' fell below the rail -- threshold drop is winning"
  end
  * 2. that stored '1' fully turns on the next stage
  if outlo_v < 0.1*$sup
    echo "  PASS  next stage pulled low by the stored '1'"
  else
    echo "  FAIL  next stage not driven -- insufficient gate overdrive"
  end
  * 3. a source-driven '0' through a pass pair reaches a valid low
  if bus0_v < 0.2*$sup
    echo "  PASS  source-driven '0' through the pass pair"
  else
    echo "  FAIL  driven '0' does not reach a valid low"
  end
  * 4. pull-up recovery fits a 50 kHz half-cycle (10us) with margin
  if arise_v < 4e-6
    echo "  PASS  10k pull-up recovery fits a 50 kHz half-cycle"
  else
    echo "  FAIL  pull-up too slow for the target clock"
  end
end
.endc
.end
