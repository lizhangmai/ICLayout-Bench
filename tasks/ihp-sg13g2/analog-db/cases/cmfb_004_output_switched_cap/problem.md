# MIM Switched-Capacitor Common-Mode Sampler Layout Task

## Objective

Implement `cmfb_004_output_switched_cap` in IHP SG13G2 and submit a self-contained GDS. Sixteen minimum-size MOS (W/L = 0.15/0.13 um) implement eight transmission paths. Four internal MIM capacitors retain the original connections: two separate vbias-to-vcm capacitors and two floating control-to-sense capacitors. Each is a 25.85 by 25.85 um cap_cmim, nominally about 1.00647 pF. Explicit physical substrate and well taps are included. The output samples common-mode displacement; this is a switched-capacitor sensing network with driven inputs, not a complete closed-loop amplifier or a loop-stability qualification.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical circuit; `materials/circuit.spice` is its equivalent simulator representation. `materials/testbench.spice` supplies measurement apparatus. This problem is the description input. The ordered ports are `vinp vinn vcmfb vcm vbias clk_phi clk_phi_not vdd vss`: sensed positive/negative inputs, sampled control output, common-mode reference, control reference, two independent clock nets, supply and return.

Preserve connectivity, MOS W/L/m, capacitor dimensions and unit multiplicities, and body/tap connections. Placement and routing are free. Device splitting/combination and source/drain interchange are allowed only when accepted by the declared native LVS equivalences. No common-centroid or statistical matching requirement is scored. All specified ideal external sources, loads and measurement apparatus belong outside the DUT.

## Operating Conditions

Typical IHP low-voltage MOS, typical resistor and capacitor models at 27 C; VDD = 1.5 V and VSS = 0 V. Each node has the declared 1e12 ohm numerical shunt. Transient integration uses Gear order 2 with a 1 ns output and maximum step. Physical taps have finite source-model resistance; Magic treats well/substrate ties ideally. Distributed silicon substrate resistance, statistical mismatch, PVT, noise and RF/EM are outside scope.

Vcm = 0.75 V; Vbias = 0.6 V. Each condition starts with input common mode 0.75 V. It changes linearly over 40–40.1 us to common_v, then holds through 100 us. Inputs are common mode +/- diff_v. The five (common_v, diff_v) pairs in volts are (0.65,0), (0.65,0.1), (0.75,0.1), (0.85,0), (0.85,0.1). Phi starts high, falls after 1 us, and alternates with its complementary independent clock; rise/fall times are 2 ns, low width 5 us and period 10 us. Phi high precharges the floating capacitors; phi low couples them to the sensed inputs and output. Finite complementary slopes permit overlap. An external 1 pF loads vcmfb; stop time is 100 us. The target after repeated transfers is 0.6 V + common_v - 0.75 V.

## Physical Requirements

The GDS top cell is `cmfb_004_output_switched_cap`, with a 10 MiB maximum file size. Provide physical, correctly connected and accessible labeled interface metal; retain every named port. Pass IHP main and maximal DRC (density and antenna excluded for this standalone block), strict named-interface LVS and a functional bounding box no larger than 320 by 70 um. No DRC waivers are used. The functional footprint includes device, passive, implant, well and complete routing layers; excludes annotations/pin text and nonfunctional markers. Its explicit GDS layer/datatype set is `[[1, 0], [3, 0], [5, 0], [6, 0], [7, 0], [8, 0], [10, 0], [11, 0], [13, 0], [14, 0], [19, 0], [24, 0], [26, 0], [28, 0], [29, 0], [30, 0], [31, 0], [32, 0], [33, 0], [35, 0], [36, 0], [40, 0], [44, 0], [46, 0], [49, 0], [50, 0], [51, 0], [52, 0], [53, 0], [55, 0], [58, 0], [66, 0], [67, 0], [90, 0], [101, 0], [111, 0], [125, 0], [126, 0], [128, 0], [129, 0], [133, 0], [134, 0], [139, 0], [152, 0]]`. The area is the bounding-box area of those layers, not summed metal area.

The candidate GDS must pass artifact, DRC, LVS and hard geometry before extraction. Magic candidate-derived distributed interconnect resistance and capacitance, with zero coupling-capacitance threshold, feed the supplied testbench. Internal MIM devices remain in candidate extraction. Source simulation alone cannot establish acceptance. This is nominal block qualification, not fabrication signoff.

## Electrical Requirements and Scoring

Every observation at every declared condition must meet its inclusive limits; aggregation cannot hide a failing code or condition. Endpoints use simulator interpolation. The zero interval gives lower/upper zero-attainment boundaries, separately from acceptance.

| Metric | Definition | Unit | Acceptance | Dimension | Zero interval |
| --- | --- | --- | --- | --- | --- |
| `output_v` | V(out) at 95 us | V | [0.49, 0.71] | bias | [0.3, 0.9] |
| `sample_error_v` | Maximum absolute V(out) minus [0.6 V + (V(vinp)+V(vinn))/2 - 0.75 V], over 92–95 us | V | [0, 0.005] | response | [0, 0.02] |
| `hold_drift_v` | Maximum absolute V(out) minus its 95 us sample, over 96.1–99 us | V | [0, 0.0005] | response | [0, 0.005] |
| `clock_power_w` | Mean of max(0,-V(phi) I(VPH)) + max(0,-V(phin) I(VPL)), over 80–100 us; returned energy is not credited | W | [0, 4e-08] | supply | [0, 8e-08] |

Coefficient 5 reflects periodic charge transfer, independent clock routing and interacting floating capacitors. The 5 mV sampling limit resolves a 100 mV common-mode disturbance, and the 0.5 mV hold limit constrains clock feedthrough during disconnection. Clock-power acceptance is 40 nW. It measures the two clock drivers, not total energy supplied by all reference/input sources. Fixed area target/zero anchors are 22000 / 88000 um2: the target accommodates a feasible complete MOS/MIM implementation and routing, while the zero anchor removes area credit at four times that absolute budget. Anchors are fixed values, not a candidate/reference area ratio.

The single score is `S = G * (60 E + 20 H + 20 H Q)`. G requires complete physical validity and evaluation; H is one only if every electrical acceptance passes. Each metric takes its worst observation; each dimension takes its worst metric; E averages the applicable dimensions. Attainment is 1 in acceptance, linearly falling to zero at the corresponding zero boundary. Q is `clip((88000-area)/(88000-22000),0,1)`. A completed physical rejection scores 0; a physically valid electrical violation scores below 60; full acceptance earns 80–100. Evaluation errors yield null rather than a guessed score. The coefficient is 5 and does not alter per-case scoring.

## Tools and Submission

Use the reviewed SG13G2 device/rule/model resources supplied through `/protocol/resources.json` and the task definitions in `/protocol/task.json`. KLayout supplies layout and physical checks; Magic supplies candidate RC; ngspice consumes the declared deck. Discover available feedback through the runtime harness protocol. Write `output/final.gds` in the workspace and explicitly submit that GDS through the submission protocol. Reference layouts, source checkouts and authoring scripts are not solver inputs.
