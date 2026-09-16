# Two-Input NAND Layout Task

## Objective

Implement ZN = NOT (A1 AND A2) using the supplied VTL transistors. Preserve the authoritative netlist's model classes, W/L, interface and connectivity. Submit top cell `NAND2_X1`.

## Inputs and Interface

Ordered SPICE ports: `A1 A2 ZN VDD VSS`. Names are case-insensitive; different names are not interchangeable. The delivered inputs are this problem, `materials/circuit.spice`, and `materials/testbench.spice`. The model and extraction resources are supplied as reviewed support bundles. Reference geometry and qualification evidence are maintainer materials, excluded from solver inputs.

## Operating Conditions

Use the nominal FreePDK45 BSIM4 models at **1.0 V and 27 C**, with ground at 0 V. All transistor lengths are 50 nm; widths and model classes come from the netlist.

ZN drives 5 fF. Apply 00, 01, 11, 10, 00, 10, 11, 01, 00 to A1/A2 in 500 ps slots, with 10 ps edges. Sample ZN at slot start + 110 ps. This visits the full truth table and both directions of each single-input transition. Average DUT supply power over 0–4.4 ns.

The deck defines stimuli and observation times exactly. Tests use only external ports. Qualification covers these nominal conditions, not PVT, mismatch, array abutment, substrate noise or manufacturing signoff.

## Physical Requirements

Submit a nonempty GDSII of at most 10 MiB. Enable all checks present in the supplied KLayout DRC deck, including grid and antenna checks, with no waivers. Strict LVS checks named ports, models, W/L and actual well/tap connectivity; library-specific implicit or global rail connections are disabled. The upstream deck does not implement its documented different-potential well-spacing rule; it is not a complete foundry signoff deck.

The hard functional envelope is 100 um by 100 um. Its bounding rectangle includes every drawing layer 1/0 through 29/0: active, wells, implants, threshold markers, poly, contacts, all ten metals and all nine vias. It supplies the scored footprint in um2. Put functional geometry on these layers; pin-purpose and annotation geometry is excluded. Electrical labels use poly or metal drawing layers (9/0 and 11/0, 13/0, ..., 29/0). Non-electrical annotation text is ignored by extraction.

Translation, equivalent hierarchy and internal instance renaming are allowed. LVS permits source/drain exchange and equivalent parallel devices; any such layout must also pass the same RC-based electrical requirements. Preserve top-level port identities and explicit body connections.

## Electrical Requirements and Scoring

Artifact, DRC, LVS and geometry gates precede candidate GDS extraction. Simulation consumes the candidate's Magic RC netlist unchanged; source simulation is calibration only. VTG/VTL device classes are checked by independent LVS before the matching extraction profile is used. Extraction includes poly/metal sheet resistance, contacts/vias, geometry-dependent coupling and ground capacitance, and device junction area/perimeter. Wells are lumped connections; BSIM4 supplies device/junction behavior. Interconnect capacitances use published FreePDK45 ElCap table fits and dielectric overlap terms with Magic's native capacitance placement; this is a predictive approximation, not a field-solver signoff extraction.

Every observation must meet its inclusive bounds. Supply power is in W and voltages are in V. Timing requirements are defined as output or differential voltage at a fixed deadline, so a missing transition remains a measurable failure.

| Metric | Native ngspice observation | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `state_0` | `find v(ZN) at=0.110n` | V | 0.9 <= value | lower: 0.5 | response |
| `state_1` | `find v(ZN) at=0.610n` | V | 0.9 <= value | lower: 0.5 | response |
| `state_2` | `find v(ZN) at=1.110n` | V | value <= 0.1 | upper: 0.5 | response |
| `state_3` | `find v(ZN) at=1.610n` | V | 0.9 <= value | lower: 0.5 | response |
| `state_4` | `find v(ZN) at=2.110n` | V | 0.9 <= value | lower: 0.5 | response |
| `state_5` | `find v(ZN) at=2.610n` | V | 0.9 <= value | lower: 0.5 | response |
| `state_6` | `find v(ZN) at=3.110n` | V | value <= 0.1 | upper: 0.5 | response |
| `state_7` | `find v(ZN) at=3.610n` | V | 0.9 <= value | lower: 0.5 | response |
| `state_8` | `find v(ZN) at=4.110n` | V | 0.9 <= value | lower: 0.5 | response |
| `supply` | `avg par('-v(vdd)*i(Vdd)') from=0 to=4.400n` | W | 0 <= value <= 6e-05 | lower: 0, upper: 0.0003 | supply |

Use the unified score `S = G * (60*E + 20*H + 20*H*Q)`. G requires all validity gates and complete, valid evaluation; H requires every electrical bound. E averages the applicable response and supply attainments; each dimension uses its worst observation, with linear interpolation to the zero boundaries above. Area utility is `Q = clip((3.4 - area) / (3.4 - 1.7), 0, 1)` using absolute um2 anchors. Electrical acceptance earns 80–100 points; a physical pass with an electrical failure earns less than 60; conclusive invalidity earns zero. Evaluator errors give a null score when no independent validity rejection is established. Coefficient: **1**.

## Tools and Submission

Use the reviewed FreePDK45 KLayout, Magic and ngspice resources from `/protocol/resources.json`. Runtime `/protocol/task.json` publishes the same constraints, measurements and scoring. Only declared inputs appear under `/task`. Write `/workspace/output/final.gds`, then explicitly submit with `python -I /protocol/submit.py`. A harness that declares `process-feedback.v1` uses the same frozen plan and backend identities for process checks; those snapshots do not count as final submissions.
