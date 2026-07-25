* monster6502v2 M4 track B: vendor-model re-validation of the pass-pair approach.
* onsemi BSIM3v3 subckt F2N7002 (sim/2N7002_onsemi.lib), pins: drain gate source.
* Topology (worst dynamic path): driver inverter -> pass pair (phi1) -> bus node
* -> pass pair (phi2) -> storage node (with LED-tap gate load) -> output inverter.
* Non-overlapping clocks; write '1' then '0'; check levels after each transfer.

.include 2N7002_onsemi.lib

Vdd VDD 0 5
* phi1: 5-14us and 45-54us; phi2: 16-25us and 56-65us (80us period each)
Vp1 PHI1 0 PULSE(0 5 5u 100n 100n 9u 40u)
Vp2 PHI2 0 PULSE(0 5 16u 100n 100n 9u 40u)
Vd  D    0 PULSE(0 5 40u 100n 100n 40u 200u)

Xdrv A D 0 F2N7002
Rpu1 VDD A 10k

* pass pair 1: A <-> BUS, gated by PHI1
X1 A   PHI1 MID1 F2N7002
X2 BUS PHI1 MID1 F2N7002
CBUS BUS 0 20p

* pass pair 2: BUS <-> STO, gated by PHI2
X3 BUS PHI2 MID2 F2N7002
X4 STO PHI2 MID2 F2N7002
CSTO STO 0 5p

* LED tap on the storage node (gate load only) + indicator resistor
Xled LEDK STO 0 F2N7002
Rled VDD LEDK 2.2k

* next logic stage
Xout OUT STO 0 F2N7002
Rpu2 VDD OUT 10k
COUT OUT 0 5p

.tran 0.02u 80u

.control
run
* write '1' (D=0 -> A high): after phi1 (15us), after phi2 (26us), held (39us)
meas tran bus_1  find v(BUS) at=15u
meas tran sto_1  find v(STO) at=26u
meas tran sto_1h find v(STO) at=39u
meas tran out_lo find v(OUT) at=39u
meas tran led_on find v(LEDK) at=39u
* write '0' (D=1 -> A low): same checkpoints
meas tran bus_0  find v(BUS) at=55u
meas tran sto_0  find v(STO) at=66u
meas tran sto_0h find v(STO) at=79u
meas tran out_hi find v(OUT) at=79u
.endc
.end
