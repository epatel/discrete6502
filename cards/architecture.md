# architecture

Intended system architecture of the discrete6502 board — what is being built and from which sources.

The deliverable is a single PCB implementing the MOS 6502 CPU out of discrete surface-mount transistors (no microcontroller, no FPGA, no 6502 die). It is a functional re-creation in the spirit of the MOnSter 6502 by Eric Schlaepfer / Evil Mad Scientist, but targeting a smaller board and JLCPCB pick-and-place assembly instead of the original's larger hand-designed board.

Planned structure:

- **Transistor-level netlist** derived from the visual6502 project's reverse-engineered 6502 netlist (transistor + node lists extracted from die photos). This is the ground truth for logic correctness.
- **Original 6502 is dynamic NMOS logic**: enhancement-mode NMOS transistors, depletion-load pull-ups, pass-transistor latches that store state as charge. A discrete re-creation must either replicate this with MOSFETs plus explicit pull-up resistors/transistors (the MOnSter approach, which also added small capacitors where charge storage was needed) or convert sections to static logic. This choice is the single biggest design decision (tracked in project-plan.md).
- **Clocking**: two-phase clock like the real 6502; achievable speed is limited by discrete-transistor capacitance — expect tens of kHz, not MHz.
- **External interface**: standard 6502 bus pinout (address bus, data bus, RDY, IRQ, NMI, RES, φ2, R/W) exposed on a header so the board can drop into a host/test rig.
- **Scale**: on the order of 4,000+ placed components (≈3,200 transistors plus pull-ups/resistors), which forces a scripted flow — netlist-to-schematic and placement must be generated programmatically, not drawn by hand.

Repo layout is not yet established; expect directories for netlist tooling (scripts), EDA project files, and fab outputs once M3 (toolchain) is decided.
