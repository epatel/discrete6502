# resources

External references this project is built from — where to look things up during research and design.

- **MOnSter 6502** — https://monster6502.com/ — the original discrete-transistor 6502 replica by Eric Schlaepfer and Evil Mad Scientist Laboratories. Study for: how they mapped dynamic NMOS logic to discrete MOSFETs, where they needed added capacitors, achievable clock speed, and their component counts. Their talks/write-ups (Hackaday Supercon talk, project updates) contain the practical lessons.
- **visual6502** — http://visual6502.org/JSSim/index.html — transistor-level simulator of the real 6502 built from die photographs. The underlying data (segment/transistor definition files in the visual6502 GitHub repo, e.g. `segdefs.js` / `transdefs.js`) is the machine-readable netlist to generate schematics from, and the simulator is the behavioral reference to verify against.
- **JLCPCB capabilities** — https://jlcpcb.com/capabilities/pcb-capabilities — authoritative fab/assembly limits; also the JLCPCB SMT parts library (https://jlcpcb.com/parts) for choosing the transistor and resistor parts by stock and economic/extended class.
- **6502.org** — https://6502.org/ — the 6502 community's reference archive. The parts that matter to us: [Tools → Emulators](https://6502.org/tools/emu/) carries a *6502 Test Programs (for Emulators and Re-implementations)* section, source of our bring-up acceptance test (**Klaus Dormann's suite**, https://github.com/Klaus2m5/6502_65C02_functional_tests, GPLv3 — fits our 16 KB mirrored map, see `pico-controller/README.md`); the [Documents archive](https://6502.org/documents/) has the original MOS datasheets with the Φ1/Φ2 timing diagrams — the [6500-family datasheet](https://6502.org/documents/datasheets/mos/mos_6500_mpu_nov_1985.pdf) is a scan but its text extracts with `pdftotext`, and it is the primary source for the original's **"Minimum clock frequency = 50 KHz"** (clock-window comparison in `cards/monster6502-lessons.md`); [Garth Wilson's 6502 Primer](http://wilsonminesco.com/6502primer/) covers hardware bring-up practice; and the [forum](https://6502.org/forum) is where this project's audience lives, if the repo ever goes public. Wolfgang Lorenz's C64 test suite is listed there too but is **not** usable for us — it chains its programs through C64 facilities we do not have.
- **initial-idea.md** (repo root) — the original one-paragraph project brief.

## 6502 SVG schematic (bring-up debugging aid)

https://github.com/epatel/6502/ (fork of davidmjc/6502) — hand-drawn SVG circuit
diagram closely following the visual6502 netlist, with click-to-highlight wires
(`cd.svg`) and a block-diagram overlay (`bcd.svg`). NOT a source for placement or
routing: its layout deliberately deviates from the real die (`diff.txt` lists the
author's changes — reordered pads, moved flip-flops, simplified circuits) and our
segdefs-derived placement is more die-faithful. Use it in M6 bring-up to read a
netlist node in human circuit context when probing the physical board.
