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

Physical checks and declared functional bounds remain mandatory. Quality has no
fixed allowed-degradation threshold. Each `source_*` job simulates the declared
source circuit with exactly the same testbench, model resources, parameters,
load and measurement window as its paired extracted-candidate job. A source
observation is the 100-point electrical baseline; it is independent of the
submitted GDS. All individual pairs are retained in the evaluation report.

For a post-layout observation x and its source observation b:

- Maximize: q = x/b; minimize: q = b/x. When a numerical scale s is declared,
  use (x+s)/(b+s) or its inverse. This handles zero-valued error measurements;
  s is a normalization floor, not an allowed degradation or pass threshold.
- Amplitude dB: q = 10^((x-b)/20) for maximize, its inverse for minimize.
- Target: q = 1/(1+abs(x-b)/s), with a declared physical scale s. Signed and
  zero-valued operating points are never divided directly.

A metric uses its worst paired q. Each response/bias/supply dimension takes the
geometric mean of its scored metrics; E is the geometric mean of applicable
dimensions. Q = area_reference / candidate_functional_area. The overall score is
S = 100 * sqrt(E * Q). The baseline is 100, not a ceiling; directional and area
improvements can earn more than 100. Failed physical or functional checks score
zero; missing/invalid evaluation or source measurements produce an unknown score.
Diagnostic observations do not earn points. The runtime task plan publishes the
exact pairing, dimensions, scales and any functional bounds.

| Metric | Definition / observations | Unit | Quality rule | Functional bounds | Scale |
| --- | --- | --- | --- | --- | --- |
| `output_v` | V(out) at 95 us | V | target / target | 0 … 1.5 | 1.5 |
| `sample_error_v` | Maximum absolute V(out) minus [0.6 V + (V(vinp)+V(vinn))/2 - 0.75 V], over 92–95 us | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `hold_drift_v` | Maximum absolute V(out) minus its 95 us sample, over 96.1–99 us | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `clock_power_w` | Mean of max(0,-V(phi) I(VPH)) + max(0,-V(phin) I(VPL)), over 80–100 us; returned energy is not credited | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **5263.8 um2**. 22 expanded device instances; sum of device/contact envelopes 3414.7414 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the reviewed SG13G2 device/rule/model resources supplied through `/protocol/resources.json` and the task definitions in `/protocol/task.json`. KLayout supplies layout and physical checks; Magic supplies candidate RC; ngspice consumes the declared deck. Discover available feedback through the runtime harness protocol. Write `output/final.gds` in the workspace and explicitly submit that GDS through the submission protocol. Reference layouts, source checkouts and authoring scripts are not solver inputs.
