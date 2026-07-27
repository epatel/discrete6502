* discrete6502: how long a dynamic node holds its bit -- the clock's LOWER bound.
*
* The design is faithful dynamic NMOS: a stored bit is charge on a wire's own
* capacitance, refreshed every clock.  sim/fanout_speed.sp fixed the UPPER bound
* (~20 kHz at 5 V: the decode-PLA lines are slow to charge through 10k).  This
* deck is about the lower one -- clock too slowly and the charge leaks away
* before it is refreshed.  Both bounds come from the same fact (huge discrete
* capacitance) pointing in opposite directions.
*
* Worst node, identified by tools/dynamic_nodes.py: the internal special-bus
* bits sb1..sb7.  Each drives just ONE gate (32 pF, including ~5 pF of copper)
* but has TWELVE FET channel terminals sitting on it, so it holds the least
* charge per leakage path on the board.  The big obvious nets are the SAFE
* ones -- cclk carries 13 nF against 2 channels.
*
* ---------------------------------------------------------------------------
* RESULT: this deck does NOT produce a retention figure, and the reason is
* worth recording so nobody burns another afternoon on it.
*
* Retention is t = C*dV/I_leak.  Section C measures C*dV/I directly and
* confirms the relation exactly, so the physics is not in doubt.  The unknown
* is I_leak, the off-state leakage of twelve BSS138K channels, which is tens
* to hundreds of picoamps -- and ngspice with this BSIM3 model cannot resolve
* it:
*
*   - the operating point does not converge reliably there ("source stepping
*     failed"), and adding a single extra device changes the answer;
*   - the result moves by 3.5 ORDERS OF MAGNITUDE with solver tolerances
*     (0.49 nA at defaults, 2.3 uA with abstol/gmin tightened);
*   - the temperature sweep comes out NON-MONOTONIC, and in section B below
*     leakage *falls* as the part gets hotter, which is physically impossible.
*     That is the tell: these are solver artifacts, not device physics.
*     ngspice's default gmin alone injects 5 pA per node at 5 V, which is the
*     same order as the quantity being measured.
*
* So the honest split is:
*   - the RELATION is proven here (section C);
*   - the LEAKAGE must come from the datasheet bound or from measurement.
*     tools/dynamic_nodes.py tabulates retention across the whole plausible
*     range and prints the crossover: at 5 V the worst node must leak less
*     than ~53 nA per FET, or the floor rises above the 20 kHz ceiling and
*     there is no working clock at all.  Typical parts are ~1 nA, so the
*     expected margin is ~50x, but that is an expectation, not a spec.
*   - MEASURE IT AT BRING-UP.  It is a two-line experiment with the firmware
*     that already exists: run a program, stop the clock for N ms, restart,
*     and see whether the CPU carries on or has forgotten itself.  Bisect N.
*     That measures the real number on the real board, which no model here
*     can substitute for.
* ---------------------------------------------------------------------------
*
* Run: cd sim && ngspice -b retention.sp

.include 2N7002_onsemi.lib

.param vsup=5.0
.param cnode=32p

* the storage node, held at the rail so its leakage can be read directly
Vprobe NA 0 {vsup}
Vgoff  GOFF 0 0

* twelve off FET channel terminals on the node -- the state an sb bit is in
* while it is holding a bit: every path off, nothing driving it.
X1  NA GOFF NB1 F2N7002
X2  NB1 GOFF 0 F2N7002
X3  NA GOFF 0 F2N7002
X4  NA GOFF 0 F2N7002
X5  NA GOFF 0 F2N7002
X6  NA GOFF 0 F2N7002
X7  NA GOFF 0 F2N7002
X8  NA GOFF 0 F2N7002
X9  NA GOFF 0 F2N7002
X10 NA GOFF 0 F2N7002
X11 NA GOFF 0 F2N7002
X12 NA GOFF 0 F2N7002

* the single gate this node drives, with its pull-up load
Vdd VDD 0 {vsup}
Xrd D1 NA 0 F2N7002
Rd1 VDD D1 10k

* CONTROL node: identical, but WITHOUT the twelve channel FETs, so the
* simulator's own artifact current can be subtracted from the measurement.
Vprobe2 NC 0 {vsup}
Xrd2 D3 NC 0 F2N7002
Rd3 VDD D3 10k

* section C: the linear-droop relation in isolation -- a bare capacitor
* drained by a known current, no devices to confuse the numerics.
Cb  NB 0 {cnode} ic={vsup}
Ib  NB 0 12n

.control
set noaskquit

echo ""
echo "=============================================================="
echo " A. attempt to read the model's own off-state leakage"
echo "    (i_fets is the measurement minus the artifact control)"
echo "=============================================================="
foreach sup 5.0 3.3
  alterparam vsup = $sup
  reset
  op
  let i_with = abs(i(vprobe))
  let i_ref  = abs(i(vprobe2))
  let i_fets = i_with - i_ref
  echo "--- VCC = $sup V ---"
  print i_with
  print i_ref
  print i_fets
end

echo ""
echo "=============================================================="
echo " B. the same over temperature -- THIS IS THE CONTROL THAT"
echo "    INVALIDATES A: real leakage roughly DOUBLES every 10 C."
echo "    If i_fets falls as the part heats up, the solver is"
echo "    reporting noise and section A must not be believed."
echo "=============================================================="
alterparam vsup = 5.0
foreach tmp 27 45 65 85
  reset
  option temp = $tmp
  op
  let i_fets = abs(i(vprobe)) - abs(i(vprobe2))
  echo "--- $tmp degC ---"
  print i_fets
end

echo ""
echo "=============================================================="
echo " C. the relation t = C*dV/I, which IS trustworthy here."
echo "    12 nA draining 32 pF is 375 V/s, so from 5 V the node"
echo "    should read 4.625 V at 1 ms and 4.000 V at 2.67 ms."
echo "=============================================================="
reset
option temp = 27
alterparam vsup = 5.0
tran 5u 4m 0 5u uic
meas tran v_at_1ms FIND v(nb) AT=1m
meas tran v_at_2p67ms FIND v(nb) AT=2.67m
echo ""
echo "  -> retention scales as C/I: at 12 nA total the node holds 2.67 ms."
echo "     Per-FET leakage of 1 nA (12 nA total) => floor ~375 Hz."
echo "     See tools/dynamic_nodes.py for the full table and the crossover."
.endc
.end
