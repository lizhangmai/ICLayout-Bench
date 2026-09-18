# Resistor-Pullup NMOS Shunt Trim Layout Task

## Objective

Implement `trm_001_vcr`, a voltage-controlled NMOS shunt with a physical
approximately 200 kohm supply pullup. Preserve the source W=2 um / L=0.5 um
NMOS, eight series high-poly segments and explicit substrate tap. Qualification
measures loaded trim range, monotonic control, operating-point conductance,
temperature/load sensitivity and finite control-step recovery. This is an
unbuffered nonlinear control node, not an ideal programmable resistor or DAC.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native LVS circuit.
- `materials/circuit.spice`: matching process-model representation.
- `materials/testbench.spice`: control sweeps, conductance and loaded recovery.

Ordered ports: `vdd vcode vout vss`. VDD is supply, VCODE controls the shunt
MOS gate, VOUT is the pullup/shunt junction and VSS is return. The NMOS source
and substrate connect through the explicit VSS tap; the physical poly body
uses the same substrate. Eight series `rhigh` segments connect VDD to VOUT,
each W=1 um / L=17.465 um, m=1 and b=0. They replace the source ideal 200 kohm
resistor and remain inside the DUT. Preserve device models, dimensions and
connectivity; native equivalent resistor merging is allowed only when LVS and
all other checks pass. There are no internal ideal sources or extra bias ports.

## Operating Conditions

Typical IHP LV MOS/poly models, all eight combinations of supplies 1.1/1.3 V,
temperatures 27/85 C and external output loads 500 kohm/1 Mohm. A 1 pF output
load is external test apparatus. DC operating point uses VCODE=0.4 V.
Sweep VCODE from 0.2 to 0.8 V in 2 mV increments; every sampled slope must
satisfy maximum_slope <= 0 V/V: increasing NMOS gate control must not
increase the pullup/shunt output voltage. This is the declared sampled sweep,
not a proof of global monotonicity beyond the control interval.

For transient, VCODE rises 0.3→0.5 V at 2–2.02 us and falls at
10.02–10.04 us, repeating every 16 us. Run to 18 us with 2 ns maximum step,
Gear order 2, `rshunt=1e12`, `reltol=1e-5`, `abstol=1e-14`, `vntol=1e-8`.
No output clamp, feedback servo or ideal storage is internal to the DUT.

## Physical Requirements

Submit GDSII top cell `trm_001_vcr`, at most 10 MiB. Pass native main/maximal DRC
without waivers (standalone scope, density/antenna disabled), strict named-port
LVS with explicit tap and a 110 × 80 um functional outline. The runtime
outline includes complete device, resistor, contact and routing drawing layers;
annotation/pin-purpose layers do not contribute to its area.
Candidate Magic RC must preserve physical MOS/poly and interconnect parasitics.
The extractor idealizes the substrate contact; source simulation includes the
finite tap model. Distributed substrate effects, PVT, mismatch, noise,
precision trimming and fabrication signoff remain outside qualification.

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
| `output_v` | condition_0:output_v, condition_1:output_v, condition_2:output_v, condition_3:output_v, condition_4:output_v, condition_5:output_v, condition_6:output_v, condition_7:output_v | V | target / target | 0 … 1.3 | 1.3 |
| `power_w` | condition_0:power_w, condition_1:power_w, condition_2:power_w, condition_3:power_w, condition_4:power_w, condition_5:power_w, condition_6:power_w, condition_7:power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `high_v` | condition_0:high_v, condition_1:high_v, condition_2:high_v, condition_3:high_v, condition_4:high_v, condition_5:high_v, condition_6:high_v, condition_7:high_v | V | target / target | 0 … 1.3 | 1.3 |
| `low_v` | condition_0:low_v, condition_1:low_v, condition_2:low_v, condition_3:low_v, condition_4:low_v, condition_5:low_v, condition_6:low_v, condition_7:low_v | V | target / target | 0 … 1.3 | 1.3 |
| `knee_code_v` | condition_0:knee_code_v, condition_1:knee_code_v, condition_2:knee_code_v, condition_3:knee_code_v, condition_4:knee_code_v, condition_5:knee_code_v, condition_6:knee_code_v, condition_7:knee_code_v | V | target / target | 0 … 1.3 | 1.3 |
| `maximum_slope` | condition_0:maximum_slope, condition_1:maximum_slope, condition_2:maximum_slope, condition_3:maximum_slope, condition_4:maximum_slope, condition_5:maximum_slope, condition_6:maximum_slope, condition_7:maximum_slope | V/V | target / target | −∞ … 0 | 0.1 |
| `span_v` | condition_0:span_v, condition_1:span_v, condition_2:span_v, condition_3:span_v, condition_4:span_v, condition_5:span_v, condition_6:span_v, condition_7:span_v | V | target / target | 0 … 1.3 | 1.3 |
| `conductance_04_s` | condition_0:conductance_04_s, condition_1:conductance_04_s, condition_2:conductance_04_s, condition_3:conductance_04_s, condition_4:conductance_04_s, condition_5:conductance_04_s, condition_6:conductance_04_s, condition_7:conductance_04_s | S | target / target | −∞ … +∞ | 0.00015 |
| `conductance_06_s` | condition_0:conductance_06_s, condition_1:conductance_06_s, condition_2:conductance_06_s, condition_3:conductance_06_s, condition_4:conductance_06_s, condition_5:conductance_06_s, condition_6:conductance_06_s, condition_7:conductance_06_s | S | target / target | −∞ … +∞ | 0.0005 |
| `conductance_ratio` | condition_0:conductance_ratio, condition_1:conductance_ratio, condition_2:conductance_ratio, condition_3:conductance_ratio, condition_4:conductance_ratio, condition_5:conductance_ratio, condition_6:conductance_ratio, condition_7:conductance_ratio | 1 | target / target | −∞ … +∞ | 5 |
| `recovery_down_v` | condition_0:recovery_down_v, condition_1:recovery_down_v, condition_2:recovery_down_v, condition_3:recovery_down_v, condition_4:recovery_down_v, condition_5:recovery_down_v, condition_6:recovery_down_v, condition_7:recovery_down_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `recovery_up_v` | condition_0:recovery_up_v, condition_1:recovery_up_v, condition_2:recovery_up_v, condition_3:recovery_up_v, condition_4:recovery_up_v, condition_5:recovery_up_v, condition_6:recovery_up_v, condition_7:recovery_up_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `mean_power_w` | condition_0:mean_power_w, condition_1:mean_power_w, condition_2:mean_power_w, condition_3:mean_power_w, condition_4:mean_power_w, condition_5:mean_power_w, condition_6:mean_power_w, condition_7:mean_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `step_span_v` | condition_0:step_span_v, condition_1:step_span_v, condition_2:step_span_v, condition_3:step_span_v, condition_4:step_span_v, condition_5:step_span_v, condition_6:step_span_v, condition_7:step_span_v | V | target / target | 0 … 1.3 | 1.3 |

High/low endpoints are continuous source-paired quality observations. Their
0–1.3 V bounds express the nonnegative, supply-limited output domain; shunt-control function does not require a narrower absolute endpoint range.

Area reference: **636.57 um2**. 10 expanded device instances; sum of device/contact envelopes 391.7515 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **4**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover inputs, resources and feedback through `/protocol/task.json`,
`/protocol/resources.json` and `/protocol/harness.json`. Use the supplied IHP
primitives with KLayout, Magic and ngspice. Write `/workspace/output/final.gds`
and explicitly submit through the harness. Host configuration, source records
and reference layouts are outside the standard solver inputs.
