#!/usr/bin/env python3
"""Flash the Pico without touching the BOOTSEL button.

WHY THIS EXISTS. Pin 39 is soldered, so VSYS *is* board VCC: unplugging USB does
not reset the module, and BOOTSEL is only sampled at reset. Getting into BOOTSEL
therefore means cycling the BOARD supply while holding the button -- fiddly on a
board that is also being probed, and on 2026-08-30 it cost most of an hour.

There is a better way, and the firmware already supports it: pico_stdio_usb
implements the 1200-baud touch, so *opening the serial port at 1200 baud and
closing it* reboots the module straight into BOOTSEL. No button, no power cycle.

    python3 tools/pico_flash.py wifi           # build_trace/wifi.uf2 if --trace
    python3 tools/pico_flash.py selftest
    python3 tools/pico_flash.py path/to.uf2

It waits for a serial port to appear, touches it, waits for RP2350 to mount, and
copies. On a board that boot-loops the port only exists for a fraction of a
second, which is why this polls at 20 Hz rather than asking you to be quick.

If no serial port ever appears, the firmware is not reaching stdio_init_all()
and only the button will do -- hold BOOTSEL, cycle the BOARD supply, release.
"""
import argparse
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMED = {
    "wifi": "pico-controller/wifi/build/wifi.uf2",
    "trace": "pico-controller/wifi/build_trace/wifi.uf2",
    "selftest": "pico-controller/selftest/build/selftest.uf2",
    "usbonly": "pico-controller/selftest/build_usbonly/selftest.uf2",
    "busonly": "pico-controller/selftest/build_busonly/selftest.uf2",
    "tester": "pico-controller/tester/build/tester.uf2",
    "general": "pico-controller/general/build/general.uf2",
}
VOL = "/Volumes/RP2350"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def touch_1200(dev):
    """The reboot-to-BOOTSEL handshake: open at 1200 baud, close."""
    subprocess.run(["stty", "-f", dev, "1200"], capture_output=True)
    try:
        with open(dev, "rb", buffering=0):
            pass
    except OSError:
        pass  # the module resets mid-open; that IS the success case


def copy_uf2(uf2):
    # cp rather than shutil: copying xattrs onto a FAT bootloader volume fails
    # with EPERM after the data is already written, which looks like an error
    # and is not.
    subprocess.run(["cp", uf2, f"{VOL}/{os.path.basename(uf2)}"], capture_output=True)
    subprocess.run(["sync"])
    time.sleep(1.5)
    return not os.path.isdir(VOL)  # it dismounts itself on a good image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target",
                    help="wifi | trace | selftest | usbonly | busonly | tester | general | a .uf2 path")
    ap.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args()

    uf2 = NAMED.get(a.target, a.target)
    if not os.path.isabs(uf2):
        uf2 = os.path.join(ROOT, uf2)
    if not os.path.exists(uf2):
        sys.exit(f"no such image: {uf2}")
    log(f"{os.path.basename(uf2)}, {os.path.getsize(uf2) // 1024} KB")

    end = time.time() + a.timeout
    touched = False
    while time.time() < end:
        if os.path.isdir(VOL):
            log("BOOTSEL volume present -- copying")
            if copy_uf2(uf2):
                log("flashed; the board is rebooting")
                return 0
            log("copy did not take, retrying")
            time.sleep(1)
            continue
        ports = sorted(glob.glob("/dev/cu.usbmodem*"))
        if ports and not touched:
            log(f"{ports[0]} -- 1200-baud touch, rebooting into BOOTSEL")
            touch_1200(ports[0])
            touched = True
            time.sleep(0.5)
        elif not ports:
            touched = False  # it went away; re-arm for the next appearance
        time.sleep(0.05)

    log("timed out. No serial port and no BOOTSEL volume means the firmware is")
    log("not reaching stdio_init_all() -- hold BOOTSEL and cycle the BOARD supply.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
