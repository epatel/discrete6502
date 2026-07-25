* monster6502v2 M2 feasibility: back-to-back 3-terminal FET pair as NMOS transmission
* gate in a 6502-style dynamic latch, with resistor pull-ups (ratioed NMOS logic).
* Three candidate FETs simulated as identical parallel circuits:
*   _b = BSS138       (logic-level, Vto~1.1V, Ciss~27pF)
*   _w = 2N7002 worst (Vto=2.4V max-ish, Ciss~25pF)  -- threshold-drop stress case
*   _a = AO3400A      (Vto~0.9V, Ciss~1nF)           -- high-capacitance case
*
* Topology per variant:
*   D -> driver inverter (FET + 10k pullup) -> A -> [M1 <- mid -> M2] -> B (storage)
*   B -> output inverter (FET + 10k pullup) -> C
*   Pass pair: drains face A and B, common source node = mid, gates on CLK.
* Timeline (80us): D=0 until 40us (A=high), CLK pulses 5-14us -> write '1' to B.
*   D=1 from 40us (A=low), CLK pulses 45-54us -> write '0' to B. Hold otherwise.

.model MBSS VDMOS(Vto=1.1 Kp=0.4 Rd=1 Rs=1 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)
.model MW02 VDMOS(Vto=2.4 Kp=0.3 Rd=1 Rs=1 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=19p Cjo=10p Is=1n Rb=1)
.model MA34 VDMOS(Vto=0.9 Kp=5.0 Rd=0.02 Rs=0.02 Rg=5 Cgdmax=150p Cgdmin=30p Cgs=750p Cjo=280p Is=1n Rb=0.5)

Vdd VDD 0 5
Vclk CLK 0 PULSE(0 5 5u 100n 100n 9u 40u)
Vd   D   0 PULSE(0 5 40u 100n 100n 40u 200u)

* ---- variant b: BSS138 ----
Mdrv_b A_b D 0 MBSS
Rpu1_b VDD A_b 10k
M1_b A_b CLK mid_b MBSS
M2_b B_b CLK mid_b MBSS
CB_b B_b 0 5p
Mout_b C_b B_b 0 MBSS
Rpu2_b VDD C_b 10k
CC_b C_b 0 5p

* ---- variant w: 2N7002 worst-case Vto ----
Mdrv_w A_w D 0 MW02
Rpu1_w VDD A_w 10k
M1_w A_w CLK mid_w MW02
M2_w B_w CLK mid_w MW02
CB_w B_w 0 5p
Mout_w C_w B_w 0 MW02
Rpu2_w VDD C_w 10k
CC_w C_w 0 5p

* ---- variant a: AO3400A ----
Mdrv_a A_a D 0 MA34
Rpu1_a VDD A_a 10k
M1_a A_a CLK mid_a MA34
M2_a B_a CLK mid_a MA34
CB_a B_a 0 5p
Mout_a C_a B_a 0 MA34
Rpu2_a VDD C_a 10k
CC_a C_a 0 5p

.tran 0.02u 80u

.control
run
* write '1': B right after clock closes (14us) and after 16us hold (30us)
meas tran B1_written_b  find v(B_b) at=14.5u
meas tran B1_held_b     find v(B_b) at=39u
meas tran C_low_b       find v(C_b) at=39u
meas tran B1_written_w  find v(B_w) at=14.5u
meas tran B1_held_w     find v(B_w) at=39u
meas tran C_low_w       find v(C_w) at=39u
meas tran B1_written_a  find v(B_a) at=14.5u
meas tran B1_held_a     find v(B_a) at=39u
meas tran C_low_a       find v(C_a) at=39u
* write '0': B after write (54.5us) and after hold (79us); C should be high
meas tran B0_written_b  find v(B_b) at=54.5u
meas tran C_high_b      find v(C_b) at=79u
meas tran B0_written_w  find v(B_w) at=54.5u
meas tran C_high_w      find v(C_w) at=79u
meas tran B0_written_a  find v(B_a) at=54.5u
meas tran C_high_a      find v(C_a) at=79u
* speed: driver output A rising edge (10k pullup charging pass-pair + wiring)
meas tran A_rise_b trig v(A_b) val=0.5 rise=2 targ v(A_b) val=4.0 rise=2
meas tran A_rise_a trig v(A_a) val=0.5 rise=2 targ v(A_a) val=4.0 rise=2
.endc
.end
