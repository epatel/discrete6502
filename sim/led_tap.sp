* discrete6502: register-LED tap brightness vs supply rail.
*
* The 55 register/counter LEDs are driven by a gate-tap FET (capacitive load only on the
* dynamic node it monitors) sinking a red 0603 LED + 2.2k ballast from VCC:
*
*     VCC --[2.2k]-- LEDK --|>|-- ... no: actual topology is
*     VCC --[2.2k Rled]-- (LED anode) LED (cathode) -- LEDK -- drain of tap FET -- 0
*
* Question for bring-up: how much dimmer are the LEDs during the recommended 3.3 V
* first power-up compared with 5 V operation?  The pass-pair deck (passpair_33v.sp)
* models the ballast only, so this deck adds a real diode model for the LED.
*
* LED model: red 0603 (LCSC C2286 class, AlGaInP/GaAsP).  Calibrated to Vf ~ 1.90 V at
* 2 mA, n = 2.0, Rs = 10 ohm -- typical for this part class.  Brightness of an LED is
* proportional to forward current over this range; perceived brightness follows roughly
* the cube root of luminous intensity.
*
* Run: cd sim && ngspice -b led_tap.sp

.include 2N7002_onsemi.lib

.model MB15 VDMOS(Vto=1.5 Kp=0.4 Rd=1 Rs=1 Rg=10 Cgdmax=6p Cgdmin=1p Cgs=21p Cjo=12p Is=1n Rb=1)
.model DLEDR D(Is=3.2e-19 N=2.0 Rs=10 Cjo=30p)

.param vsup=5.0

Vdd  VDD 0 {vsup}
* tap gate driven to the stored '1' level the pass-pair deck measured at this rail
Vg   G   0 {vsup}

* ---- variant w: BSS138W worst case (Vto 1.5) as fitted on the board ----
Rled_w VDD LA_w 2.2k
Dled_w LA_w LK_w DLEDR
Mtap_w LK_w G 0 MB15

* ---- variant v: onsemi vendor 2N7002 model, cross-check on the driver ----
Rled_v VDD LA_v 2.2k
Dled_v LA_v LK_v DLEDR
Xtap_v LK_v G 0 F2N7002

* ---- model calibration probes: the same diode driven at known currents ----
Ic1 0 C1 0.5m
Dc1 C1 0 DLEDR
Ic2 0 C2 1m
Dc2 C2 0 DLEDR
Ic3 0 C3 2m
Dc3 C3 0 DLEDR
Ic4 0 C4 5m
Dc4 C4 0 DLEDR

.control
* first: confirm the LED model is sane -- Vf at 0.5 / 1 / 2 / 5 mA
op
echo ""
echo "LED model check -- forward voltage at 0.5mA, 1mA, 2mA, 5mA:"
print v(C1) v(C2) v(C3) v(C4)

foreach sup 5.0 3.3 3.0
  alterparam vsup = $sup
  reset
  op
  let iled_w = (v(VDD) - v(LA_w))/2200
  let iled_v = (v(VDD) - v(LA_v))/2200
  let vf_w   = v(LA_w) - v(LK_w)
  let vsat_w = v(LK_w)
  echo ""
  echo "================ VCC = $sup V ================"
  print iled_w vf_w vsat_w iled_v
end
.endc
.end
