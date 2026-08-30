# fab, order and yield — what was paid, verified and expected

Split out of `project-plan.md` on 2026-08-30, verbatim and unedited. All of it is closed: the
order is paid, both confirmation gates passed, the boards are delivered. **Read it before any
respin, when reasoning about what rev B would cost, or when a defect on board #1 needs
to be judged against what the yield model predicted.**

The two verification sections are the reusable part — they record *methods* (identify a plane by
counting polygon vertices at known via positions; identify part rotation from the pattern rather
than from one part) that a future respin should re-run rather than trust a label for.

## Cost — AS ORDERED (paid 2026-07-28)

| Line | | |
|---|---|---|
| PCB, 5 pcs, 6-layer ENIG, build 5–6 days | €131.38 | $149.64 |
| — invoiced as 1 bare board @ €26.28 + 4 boards that go on to assembly | | |
| PCBA, 4 pcs, Standard, both sides, build 3–4 days +1 | €593.93 | $676.46 |
| — invoiced as 4 populated boards @ **€174.76** each (€699.04) | | |
| **Merchandise** | **€725.32** | **$826.10** |
| Shipping, UPS Worldwide Express Saver, 4.84 kg | €59.34 | $67.59 |
| Coupon | −€8.78 | −$10.00 |
| **Paid at checkout** (2026-07-28 18:39:59, status Paid) | **€775.88** | **$883.69** |
| Depaneling the two 5 mm edge rails — priced at "advanced option review finished", **paid separately 2026-07-29** | €2.60 | $2.96 |
| **Total paid to JLCPCB** | **€778.48** | **$886.65** |
| Swedish import VAT (25% of €778.48 goods + freight, billed by UPS) | ≈ €195 | |
| UPS customs clearance / disbursement fee | a few hundred SEK | |

Advanced options are excluded from the checkout total by design and invoiced after JLC's review,
so the order was paid in **two** transactions ($883.69 then $2.96) which sum exactly to the
$886.65 order total — not a double charge. The coupon also moved from its own discount line onto
the PCBA line item at that point, which is why the PCBA figure drops $10 without the order
getting cheaper.

**Personal purchase, no VAT number** [user, 2026-07-28] — the blank `VAT No:` on the invoice
is correct and intentional. The import VAT is a final cost, not reclaimable; do not raise this
again when the UPS clearance bill arrives.
| **Landed total** | **≈ €973** (≈ **€243 per assembled CPU**) | |

Shipping is **UPS Worldwide Express Saver** and the incoterm is **CPT** (carriage paid by JLC, import VAT borne by us) — both read off the commercial invoice, which is the authority; the cart panel's carrier label is clipped and easy to misread. JLCPCB's order page shows merchandise net of the coupon ($826.10 - $10.00 = $816.10, plus
$67.59 shipping = $883.69). JLCPCB's native currency is USD; the coupon is a flat $10 shown as €8.78, and both line items
convert at exactly 1.1390. Against the 2026-07-26 quote the order came in **€3.59 cheaper**
(merchandise €725.32 vs €728.88). Component cost is €404.20 for 9 items = **€101.05 of parts
per assembled board**.

Two settings changed between the quote and the order, both reviewed 2026-07-28:
**depaneling switched ON** (€2.60, +1 build day — the golden board has 130 MLCC joints within
10 mm of the break lines and ceramics are the parts most prone to flex cracking, so
hand-snapping four populated boards was not worth €2.60), and the previously empty **PCB Remark
now carries the stackup** (`6-layer stackup top to bottom: F_Cu, In1 GND plane, In2 sig, In3
sig, In4 VCC plane, B_Cu. Gerber ext .g1-.g4 = inner 1-4. Inner layer order is critical, do NOT
reorder.`, 169/200 chars).

## Cost (quote on the rev A upload, verified 2026-07-26 — superseded by the table above)

JLCPCB quote for **5 PCBs, 4 of them assembled** (6-layer, 290.7 × 322 mm ≈ 9.4 dm², ENIG,
Standard PCBA both sides — *Economic offers no double-sided* — 5,328 placements each).
**[user decision 2026-07-26]** the fifth board stays bare: the die artwork with no parts on
it photographs far better than a populated board, and it is a free spare.

| Item | Cost |
|---|---|
| **PCB fab, 5 pcs, 6-layer ENIG** — engineering €28.99, large size €22.84, surface finish €24.24, board €54.46, confirm production file €0.91 | **€131.44** |
| **PCBA, both sides, 4 boards** | **€597.44** |
| Shipping (UPS Worldwide Express Saver to Sweden; 4.84 kg) | €59.37 |
| Coupon | −€8.78 |
| **Cart subtotal** | **€779.47** |
| Depaneling the two 5 mm edge rails (billed after engineering review) | €2.88 |
| Swedish import VAT (25% of goods + freight) | ≈ €195.59 |
| **Landed total** | **≈ €978** (≈ **€245 per assembled CPU**) |

Assembly does not scale linearly — setup €44.90 + stencil €14.42 + feeders €12.10 are
one-time. At 5 assembled the PCBA line was €715.83 (€143.17/board; components 9 items
€509.20, SMT assembly €84.28, large size €50.47, packaging €0.46); at 4 it is €597.44
(€149.36/board). So dropping the fifth **saves €118.39 and costs €6.19 more per CPU** —
worth it when that board's job is to be looked at. Note the bare board will probably arrive
with its edge rails still attached, since depaneling is a PCBA-side option; snapping them off
a board with no solder joints on it is safe by hand.

Verified line-by-line against the rev A upload: via covering **€0.00** (Epoxy Filled & Capped
is free at 6 layers) and there is no via-hole-class line item at all, which confirms the
default 0.3 mm class carries no surcharge — the ≈ €25 for the 0.2 mm class was an *avoided*
cost, not a reduction. Parts dominate assembly — €509.20 of the 5-board quote's €715.83 was
components, i.e. **€101.84 of parts per assembled board** (the 4-board line item is not broken
down in the cart, but the per-board parts cost does not change). Free build
times selected: PCB 5–6 days, assembly 3–4 days (2–3 days would add €43.27). The design
changes since the 2026-07-25 cart (BSS138K, silk re-place, 0.3 mm vias) moved the total by
**€0.55**.

Cart as built (upload `discrete6502_gerbers_Y6`, not yet paid): PCB `Y6-2923600A`,
Standard PCBA `SMT026072660664-29…`, both line items checked, estimated ship **2026-08-04**.

(The 2026-07-18 preliminary estimate of ~$180–210/CPU assumed a 200×250 mm 4-layer board;
the die-mimicry directive and the 6-layer decision account for the difference.)

## Expected fab yield (estimate recorded 2026-07-28, before the boards arrive)

Not a JLCPCB-specific figure — published industry DPMO ranges applied to this board's real
joint count. Per assembled board (`gen/netlist.json`): **5,328 placements, ~14,700 solder
joints**, of which 12,153 are the 4,051 FETs × 3 pins. **The netlist has no redundancy** (the
271 parallel visual6502 transistors were merged), so ~95% of those joints are fatal if
defective; only the 55 LED taps and the decouplers are forgiving, and the decouplers only
against opens — a shorted decoupler is a dead rail.

P(perfect board) = e^(−joints × DPMO × 10⁻⁶):

| Assembly DPMO | Expected defects/board | P(board perfect) | P(≥1 of 4 perfect) |
|---|---|---|---|
| 10 (excellent) | 0.15 | 86% | ~100% |
| 25 (good) | 0.37 | 69% | ~99% |
| 50 (typical) | 0.74 | 48% | 93% |
| 100 (mediocre) | 1.5 | 23% | 65% |

Component-level failures add 0.1–0.5 per board (5,328 parts at 20–100 ppm for economy-brand
parts). **Central estimate: 0.5–2 defects per board.** Ordering four is what makes that
acceptable, and every FET being on the top face makes SOT-323 rework by hand realistic.

Random defects are the benign case, because they are independent across boards. The risks that
matter are **systematic and hit all four identically**:

0. ~~**Inner-layer order**~~ **CLOSED 2026-07-29 by measurement** — see "Stackup verified from
   JLC's production files" below. Kept in this list because it was one of the two all-four-boards
   failures, and because the method generalises to any future respin.
1. ~~**SOT-323 rotation**~~ **CLOSED 2026-07-30 on the DFM image** (see "Placement verified from JLC's DFM" below) — 4,051 parts from one reel. Wrong rotation is four dead boards with no
   worthwhile rework. This is why the order settings require Confirm Parts Placement plus the
   rotation note; it is the highest-value review step in the project.
2. **Via-in-pad** — 3,817 vias sit inside SMD pads, which is why Epoxy Filled & Capped is
   mandatory, not optional. Imperfect capping wicks solder down the via, giving opens and voids
   concentrated wherever the capping failed. The most design-specific risk we carry.
3. **Wrong part or value on a reel** — only 9 line items, but it is an all-boards-at-once fault.

**Density is NOT a risk factor — measured 2026-07-29, not assumed.** The intuition that 5,328
parts packed close together must raise the per-joint defect rate does not survive measurement:
across all 14,912 SMD pads, the **closest gap between pads of two different parts on different
nets is 0.955 mm** (C99/C100, the tightest pair on the board). Routine SMT handles 0.2–0.3 mm
gaps, so this board is ~4x more relaxed than ordinary work, and the parts are unremarkable
(SOT-323 is 0.65 mm pitch, 0402 is a standard chip size — nothing is fine-pitch). This is a
direct dividend of the die-mimicry directive: refusing to pack the transistors preserved the
die's empty space, so the board is physically huge but locally sparse. **Closeness is not the
risk; count is** — and count is what the DPMO model above already captures.

**Three size-driven risks the DPMO model does NOT capture**, all consequences of building on a
300 × 322 mm 6-layer board rather than of part density:

1. **Thermal mass** — six layers with two solid copper planes. A uniform reflow profile across
   that area is genuinely harder than on a small board: too little heat gives cold joints, too
   much cooks the edges. The most plausible source of a defect *cluster* rather than scattered
   singles.
2. **Warpage** — 1.6 mm thickness over a 300 mm span is a floppy ratio at reflow temperature.
   Bow can lift parts off their pads mid-profile and produce opens, typically toward the centre
   or the corners.
3. **Two reflow passes**, since assembly is double-sided — the bottom-side passives see the
   profile twice.

None of these move the 0.5–2 defects/board central estimate, but they widen the uncertainty
upward and they make defects **more likely to be clustered by region than uniformly scattered**.
That is useful at bring-up rather than merely bad news: if the functional test fails in a way
that maps onto one area of the die, suspect the process, not a random joint.

**The answer in one line: expect 2 of the 4 boards to work at first power-up** (plausibly 1–3),
**~85% chance at least one works immediately**, and **3–4 working after rework** — a
single-defect board is a repair job, not a loss, since every FET is on the top face and the
functional test localises the failure. That assumes no systematic fault: rotation or stackup
errors are all-or-nothing and give 0 of 4, which is why both were gated by explicit JLC
confirmation before production.

Bare-board risk is comparatively low: 5-mil rules and 0.3 mm drills are standard capability, and
JLC flying-probe tests every board before assembly.

**Consequence for bring-up:** Step 2 of the sequence in `pico-controller/README.md` (board-alone
current draw at 5 V against the 0.35 A prediction, before the Pico is fitted) is the
systematic-fault detector — a rotation error, a shorted decoupler or a wrong reel moves that
number grossly. Single-joint random defects will not move it; those surface as functional-test
failures, which is why the acceptance suite's per-`test_case` progress reporting matters: it
narrows 4,051 FETs to a functional block.

## Stackup verified from JLC's production files (2026-07-29)

JLC sent the PCB production package (the €0.91 "Confirm Production file" option — assembly/DFM
is a separate confirmation still pending). The check that mattered was inner-layer order, and it
was settled **by measurement, not by trusting the label**.

File sizes alone only prove that *planes* sit at L2/L5 (12.9 MB each vs 1.0 MB for L3/L4) — they
cannot tell which plane is which, and a GND/VCC swap is exactly the catastrophic case. So their
gerbers were aligned to `gen/board_routed_golden.kicad_pcb` (their CAM output is in inches, Y
flipped, +4.5 mm X offset from the 5 mm rails) and polygon vertices were counted within 0.5 mm
of the 2,501 known vss via positions and the 1,349 vcc ones. **A plane floods over vias of its
own net and cuts an antipad around foreign ones**, so the asymmetry identifies each plane with
no reference to any layer name:

| JLC layer | vertices/via near VSS | near VCC | verdict |
|---|---|---|---|
| l2 | 2.1 | **26.4** | voids at VCC vias → **GND plane** (= our In1) |
| l3 | 1.1 | 1.1 | no plane behaviour → signal (= In2) |
| l4 | 1.3 | 1.4 | no plane behaviour → signal (= In3) |
| l5 | **18.3** | 2.3 | voids at VSS vias → **VCC plane** (= our In4) |

One board-wide alignment fits all four layers; a per-layer alignment search is the trap, since
it finds spurious local optima (it put l5 at dy = −3.0 mm and halved the contrast). Alignment is
a property of the board, not of the layer.

Also confirmed in their metadata (`YG/4te.json`, GBK-encoded): `batCountRemark` records our
L1–L6 filename mapping verbatim, and the auto-appended order remark contains a Chinese
translation of our email **including the self-check** ("L2 and L5 are solid copper, L3 and L4
sparse; if L2 or L5 shows sparse traces the layer order is reversed") and the 13,000-via
rationale — the CAM engineer propagated the reasoning rather than just ticking a box. Board
parameters all match: 6 layers, FR-4, 1.6 mm, inner 0.5 oz / outer 1 oz, 300.7 × 322 mm, 沉金
(ENIG), green mask, white silk, `[不加客编]` (no customer code — the "Remove Mark" selection).

Two incidental findings: a `vcut` file is present, so **the edge rails are V-scored** (that is
what gets snapped at depaneling); and `qrCodeFlag` is true but the remark places the SMT QR and
plain code **on the process edge, both sides**, so the code lives on the rails and leaves with
them — the board itself stays unmarked.

**Lesson worth keeping:** the PCB Remark did its job, but the *proof* came from geometry. Any
future respin should re-run this vertex-density test rather than reading layer names.

**Confirmed and released 2026-07-29 — the PCB is in production.** The bare boards are now
committed; no further change to the fab data is possible. The assembly/DFM confirmation is the
remaining gate, and SOT-323 rotation is the last all-four-boards risk still open.

## Placement verified from JLC's DFM (2026-07-30)

The assembly gate, separate from the PCB one. Ground truth pulled from
`gen/board_routed_golden.kicad_pcb` first, because the useful check is whether the *pattern* of
orientations matches rather than whether one part looks plausible:

| Family | Count | Rotation | Side | Cathode = pad 1 |
|---|---|---|---|---|
| Q1–Q4051 (SOT-323) | 4,051 | **all 0°** | top | n/a (pad 1 = gate, at −0.89, −0.65 = upper-left) |
| D1–D55 (LED 0603) | 55 | all 0° | top | **−x (left)** |
| D56–D67 (SOD-323) | 12 | all 180° | **bottom** | **+x (right)** |

- **FETs ✓** Every FET is at 0°, so the DFM's uniform appearance — pin-1 marker at upper-left on
  all of them — is correct. A uniform 180° misread would have put the marker at lower-right.
  **This closes the last all-four-boards risk.**
- **LEDs ✓** Unambiguous in the top view: DFM draws the minus bar left and `+` right, matching
  cathode on −x.
- **SOD-323 ✓** Needed care, because the bottom view's mirroring was unknown and the answer flips
  with it. Resolved three ways: (a) D66/D67 are the **rightmost** of the six pairs (x = 243.1 of
  290.7) and render at the **left**, so screen-left = increasing board X, i.e. the view IS
  mirrored, making the left-hand bar the +x pad = pad 1 = cathode; (b) the cursor readout
  (X 252.36, Y 310.85) fits `Y_display = 322 − y_board` with D66/D67 at y = 9.90/12.00, so the
  coordinate mapping is confirmed; (c) **our own silk asymmetry agrees** — the SOD-323 silk spans
  −1.05..+1.61 mm, poking past the pad on the cathode side and stopping inside it on the anode
  side, and on screen the outline pokes out on the same side as their bar. Since JLC derive
  polarity from the silkscreen, (c) is their reading agreeing with our drawing.

Also confirmed: part numbers C504052 / C2286 / C2128 match the BOM, sides match the board
(FETs + LEDs top, clamp diodes bottom), and R1079 (the 100R clk0 protection resistor, y = 7.80)
renders directly above D66 as it should.

**Bounded-risk note kept for the record:** had the 12 clamp diodes been reversed, the cost was
repairable, not fatal — they would forward-conduct from the rail and hold res/irq/nmi/rdy/so/clk0
at a fixed level, obvious on first power-up and fixable by reworking or simply removing 12
back-side SOD-323s, since they are protection only and not in the signal path. That asymmetry of
consequence is why the FET rotation deserved the greater scrutiny.

**Released to production 2026-07-30.** Both systematic risks are now closed by inspection, and
what remains is the random-defect picture in "Expected fab yield": expect 2 of 4 working at first
power-up, 3–4 after rework.


