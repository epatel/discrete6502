# resources

External references this project is built from — where to look things up during research and design.

- **MOnSter 6502** — https://monster6502.com/ — the original discrete-transistor 6502 replica by Eric Schlaepfer and Evil Mad Scientist Laboratories. Study for: how they mapped dynamic NMOS logic to discrete MOSFETs, where they needed added capacitors, achievable clock speed, and their component counts. Their talks/write-ups (Hackaday Supercon talk, project updates) contain the practical lessons.
- **visual6502** — http://visual6502.org/JSSim/index.html — transistor-level simulator of the real 6502 built from die photographs. The underlying data (segment/transistor definition files in the visual6502 GitHub repo, e.g. `segdefs.js` / `transdefs.js`) is the machine-readable netlist to generate schematics from, and the simulator is the behavioral reference to verify against.
- **JLCPCB capabilities** — https://jlcpcb.com/capabilities/pcb-capabilities — authoritative fab/assembly limits; also the JLCPCB SMT parts library (https://jlcpcb.com/parts) for choosing the transistor and resistor parts by stock and economic/extended class.
- **initial-idea.md** (repo root) — the original one-paragraph project brief.

## 6502 SVG schematic (bring-up debugging aid)

https://github.com/epatel/6502/ (fork of davidmjc/6502) — hand-drawn SVG circuit
diagram closely following the visual6502 netlist, with click-to-highlight wires
(`cd.svg`) and a block-diagram overlay (`bcd.svg`). NOT a source for placement or
routing: its layout deliberately deviates from the real die (`diff.txt` lists the
author's changes — reordered pads, moved flip-flops, simplified circuits) and our
segdefs-derived placement is more die-faithful. Use it in M6 bring-up to read a
netlist node in human circuit context when probing the physical board.
