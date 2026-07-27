* discrete6502: how fast can the clock actually run?  Pull-up recovery on the
* highest-fanout nets, which is what sets the maximum clock -- not the pass pairs.
*
* The M2 speed estimate (2.2 * 10k * 30pF = 0.3us) assumed a node driving ONE gate.
* Extracting real fanout from gen/netlist.json tells a different story: the
* instruction-register lines feeding the decode PLA drive 30-71 gates each, and
* every one of those gates is a discrete BSS138W with Ciss ~ 27 pF:
*
*   net       gates   C = gates * 27pF   pulled up by
*   cclk        482      13.0 nF         FET (vcc_side source follower) -- fast
*   cp1         198       5.4 nF         FET -- fast
*   ir2          71       1.9 nF         10k resistor  <- worst resistor-pulled net
*   ir4          69       1.9 nF         10k resistor
*   irline3      63       1.7 nF         10k resistor
*   (760 resistor-pulled nets total; 17 of them above 10us rise, 2 above 40us)
*
* This deck drives the real worst case: a 10k pull-up recovering a 1.92 nF PLA
* input line after its pull-down releases, with a receiving inverter on the far
* end, and measures the delay until the receiving stage has actually flipped.
* Compared against a median 1-gate net for reference.
*
* Run: cd sim && ngspice -b fanout_speed.sp

.include 2N7002_onsemi.lib

.model MB15 VDMOS(Vto=1.5 Kp=0.4 Rd=1 Rs=1 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)

.param vsup=5.0

Vdd VDD 0 {vsup}
* pull-down releases the node at t=10us (gate driven low), re-asserts at 200us
Vg  G   0 PULSE({vsup} 0 10u 100n 100n 180u 400u)

* ---- worst case: ir2-class PLA input line, 71 gate loads = 1.92 nF ----
Rpu_w  VDD NW 10k
Mpd_w  NW G 0 MB15
Cfan_w NW 0 1.92n
* one representative receiving gate at the far end, with its own pull-up
Mrx_w  RW NW 0 MB15
Rrx_w  VDD RW 10k
Crx_w  RW 0 30p

* ---- reference: median net, single gate load = 27 pF ----
Rpu_m  VDD NM 10k
Mpd_m  NM G 0 MB15
Cfan_m NM 0 27p
Mrx_m  RM NM 0 MB15
Rrx_m  VDD RM 10k
Crx_m  RM 0 30p

.control
foreach sup 5.0 3.3
  alterparam vsup = $sup
  reset
  tran 0.05u 190u
  echo ""
  echo "================ VCC = $sup V ================"
  * node rise (10-90%) on the loaded line vs the median line
  meas tran rise_w trig v(NW) val='0.1*$sup' rise=1 targ v(NW) val='0.9*$sup' rise=1
  meas tran rise_m trig v(NM) val='0.1*$sup' rise=1 targ v(NM) val='0.9*$sup' rise=1
  * what actually matters: delay until the RECEIVING stage has flipped low
  meas tran prop_w trig v(G) val='0.5*$sup' fall=1 targ v(RW) val='0.1*$sup' fall=1
  meas tran prop_m trig v(G) val='0.5*$sup' fall=1 targ v(RM) val='0.1*$sup' fall=1
  * level actually reached on the loaded line after 10us (a 50 kHz half-cycle)
  meas tran n_at10us find v(NW) at=20u
  meas tran n_at25us find v(NW) at=35u
  meas tran n_at50us find v(NW) at=60u
end
.endc
.end
