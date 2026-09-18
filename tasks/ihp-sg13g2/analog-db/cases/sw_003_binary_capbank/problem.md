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
| `gain_vv` | Magnitude V(out)/V(vinp) at 10 kHz, unit AC input | V/V | target / target | −∞ … +∞ | 1.0 |
| `phase_deg` | Phase of V(out)/V(vinp) at 10 kHz, in degrees | deg | target / target | −∞ … +∞ | 180 |
| `input_cap_f` | Imaginary part of -I(VI), divided by 2 pi f at 10 kHz, unit AC input | F | minimize / ratio | 0 … +∞ | 1e-21 |
| `gain_error` | Absolute gain_vv minus (1+code)/8 | V/V | minimize / ratio | 0 … +∞ | 1e-09 |
| `step_gain` | [V(out) at 29 us minus V(out) at 9 us] / 0.2 V | V/V | target / target | −∞ … +∞ | 1.0 |
| `step_error` | Absolute step_gain minus (1+code)/8 | V/V | minimize / ratio | 0 … +∞ | 1e-09 |
| `return_error_v` | Absolute V(out) at 49 us minus V(out) at 9 us | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `settling_error_v` | Maximum absolute V(out) minus its 29 us value, over 20–29 us | V | minimize / ratio | 0 … +∞ | 1e-06 |

Area reference: **9532.78 um2**. 22 expanded device instances; sum of device/contact envelopes 6227.9559 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the reviewed SG13G2 device/rule/model resources supplied through `/protocol/resources.json` and the task definitions in `/protocol/task.json`. KLayout supplies layout and physical checks; Magic supplies candidate RC; ngspice consumes the declared deck. Discover available feedback through the runtime harness protocol. Write `output/final.gds` in the workspace and explicitly submit that GDS through the submission protocol. Reference layouts, source checkouts and authoring scripts are not solver inputs.
