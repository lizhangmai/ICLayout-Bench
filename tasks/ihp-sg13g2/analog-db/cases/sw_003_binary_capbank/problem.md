# Three-Bit MIM Capacitive Transfer Bank Layout Task

## Objective

Implement `sw_003_binary_capbank` in IHP SG13G2 and submit a self-contained GDS. Twelve minimum-size MOS (W/L = 0.15/0.13 um) select the bottom plates of a 1:1:2:4 MIM capacitor bank between vinp and VCM. Eight identical 25.85 by 25.85 um cap_cmim units implement those weights, each nominally about 1.00647 pF. Explicit physical substrate and well taps are included. For code k, the ideal capacitive transfer is (1+k)/8. Qualification covers all eight static codes and bipolar input steps at each fixed code; live code transitions, ADC conversion, charge redistribution after a code change and mismatch linearity are outside scope.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical circuit; `materials/circuit.spice` is its equivalent simulator representation. `materials/testbench.spice` supplies measurement apparatus. This problem is the description input. The ordered ports are `vinp vout VCM VDD VSS V_D0 V_D0_NOT V_D1 V_D1_NOT V_D2 V_D2_NOT`: signal input, floating output, common-mode reference, supply/return and three independent pairs of complementary code controls. SPICE names are case-insensitive; preserve these physical labels.

Preserve connectivity, MOS W/L/m, capacitor dimensions and unit multiplicities, and body/tap connections. Placement and routing are free. Device splitting/combination and source/drain interchange are allowed only when accepted by the declared native LVS equivalences. No common-centroid or statistical matching requirement is scored. All specified ideal external sources, loads and measurement apparatus belong outside the DUT.

## Operating Conditions

Typical IHP low-voltage MOS, typical resistor and capacitor models at 27 C; VDD = 1.5 V and VSS = 0 V. Each node has the declared 1e12 ohm numerical shunt. Transient integration uses Gear order 2 with a 1 ns output and maximum step. Physical taps have finite source-model resistance; Magic treats well/substrate ties ideally. Distributed silicon substrate resistance, statistical mismatch, PVT, noise and RF/EM are outside scope.

All eight binary codes are separate required conditions. Bit k is driven by 1.5*bk V and its complement by 1.5*(1-bk) V; controls remain static. VCM = 0.75 V. VINP has DC 0.65 V and unit AC amplitude. AC uses 50 points/decade from 1 kHz to 100 MHz; acceptance measurements are at 10 kHz. VINP stays at 0.65 V through 10 us, rises to 0.85 V at 10.002 us, holds through 30 us, returns to 0.65 V at 30.002 us and holds through 50 us. Vout has an external 1e12 ohm return to ground, in addition to the numerical shunt; no ideal external holding capacitor is added. Absolute output DC is not a retained sample requirement: measurements compare increments. The testbench expected-value voltage source is measurement apparatus only.

## Physical Requirements

The GDS top cell is `sw_003_binary_capbank`, with a 10 MiB maximum file size. Provide physical, correctly connected and accessible labeled interface metal; retain every named port. Pass IHP main and maximal DRC (density and antenna excluded for this standalone block), strict named-interface LVS and a functional bounding box no larger than 460 by 75 um. No DRC waivers are used. The functional footprint includes device, passive, implant, well and complete routing layers; excludes annotations/pin text and nonfunctional markers. Its explicit GDS layer/datatype set is `[[1, 0], [3, 0], [5, 0], [6, 0], [7, 0], [8, 0], [10, 0], [11, 0], [13, 0], [14, 0], [19, 0], [24, 0], [26, 0], [28, 0], [29, 0], [30, 0], [31, 0], [32, 0], [33, 0], [35, 0], [36, 0], [40, 0], [44, 0], [46, 0], [49, 0], [50, 0], [51, 0], [52, 0], [53, 0], [55, 0], [58, 0], [66, 0], [67, 0], [90, 0], [101, 0], [111, 0], [125, 0], [126, 0], [128, 0], [129, 0], [133, 0], [134, 0], [139, 0], [152, 0]]`. The area is the bounding-box area of those layers, not summed metal area.

The candidate GDS must pass artifact, DRC, LVS and hard geometry before extraction. Magic candidate-derived distributed interconnect resistance and capacitance, with zero coupling-capacitance threshold, feed the supplied testbench. Internal MIM devices remain in candidate extraction. Source simulation alone cannot establish acceptance. This is nominal block qualification, not fabrication signoff.

## Electrical Requirements and Scoring

Every observation at every declared condition must meet its inclusive limits; aggregation cannot hide a failing code or condition. Endpoints use simulator interpolation. The zero interval gives lower/upper zero-attainment boundaries, separately from acceptance.

| Metric | Definition | Unit | Acceptance | Dimension | Zero interval |
| --- | --- | --- | --- | --- | --- |
| `gain_vv` | Magnitude V(out)/V(vinp) at 10 kHz, unit AC input | V/V | [0.1, 1.02] | response | [0, 1.2] |
| `phase_deg` | Phase of V(out)/V(vinp) at 10 kHz, in degrees | deg | [-1, 1] | response | [-10, 10] |
| `input_cap_f` | Imaginary part of -I(VI), divided by 2 pi f at 10 kHz, unit AC input | F | [0, 3e-12] | response | [0, 6e-12] |
| `gain_error` | Absolute gain_vv minus (1+code)/8 | V/V | [0, 0.015] | response | [0, 0.03] |
| `step_gain` | [V(out) at 29 us minus V(out) at 9 us] / 0.2 V | V/V | [0.1, 1.02] | response | [0, 1.2] |
| `step_error` | Absolute step_gain minus (1+code)/8 | V/V | [0, 0.015] | response | [0, 0.03] |
| `return_error_v` | Absolute V(out) at 49 us minus V(out) at 9 us | V | [0, 2e-05] | response | [0, 0.0001] |
| `settling_error_v` | Maximum absolute V(out) minus its 29 us value, over 20–29 us | V | [0, 1e-05] | response | [0, 0.0001] |

Coefficient 5 reflects multi-bit switched capacitors and interconnect-dependent capacitive division. Absolute AC and step-gain error limits of 0.015 V/V preserve separation of the 0.125 V/V code intervals, with explicit return and settling limits. These are transfer accuracy requirements under driven input and fixed codes, not DAC INL/DNL or floating-node DC accuracy. Fixed area target/zero anchors are 33000 / 132000 um2: the target accommodates a feasible complete MOS/MIM implementation and routing, while the zero anchor removes area credit at four times that absolute budget. Anchors are fixed values, not a candidate/reference area ratio.

The single score is `S = G * (60 E + 20 H + 20 H Q)`. G requires complete physical validity and evaluation; H is one only if every electrical acceptance passes. Each metric takes its worst observation; each dimension takes its worst metric; E averages the applicable dimensions. Attainment is 1 in acceptance, linearly falling to zero at the corresponding zero boundary. Q is `clip((132000-area)/(132000-33000),0,1)`. A completed physical rejection scores 0; a physically valid electrical violation scores below 60; full acceptance earns 80–100. Evaluation errors yield null rather than a guessed score. The coefficient is 5 and does not alter per-case scoring.

## Tools and Submission

Use the reviewed SG13G2 device/rule/model resources supplied through `/protocol/resources.json` and the task definitions in `/protocol/task.json`. KLayout supplies layout and physical checks; Magic supplies candidate RC; ngspice consumes the declared deck. Discover available feedback through the runtime harness protocol. Write `output/final.gds` in the workspace and explicitly submit that GDS through the submission protocol. Reference layouts, source checkouts and authoring scripts are not solver inputs.
