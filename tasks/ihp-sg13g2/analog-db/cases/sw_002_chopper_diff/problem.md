# Differential Polarity-Commutating Switch Layout Task

## Objective

Implement `sw_002_chopper_diff` in ihp-sg13g2 and submit self-contained GDS. Eight MOS devices form four transmission paths that connect a differential input directly or with reversed polarity. The two complementary clock nets are independent layout ports. Fixed IHP W/L/m are retained; explicit substrate/well taps are included in both maintained circuit representations.

## Inputs and Interface

`materials/circuit.cdl` is the authoritative physical circuit. `materials/circuit.spice` is its equivalent simulator model-call representation. `materials/testbench.spice` defines measurements, and this problem is the description input.
Ordered ports: `va_p va_n vb_p vb_n vctl vctl_not vdd vss`. In order: Positive input, negative input, positive output, negative output, direct-path clock, complementary clock, supply, and return.

Preserve connectivity, W/L/m, passive geometry and body connections. Provide physical contacts. Placement and routing are free; splitting and source/drain interchange are allowed only under the declared LVS equivalences. No statistical matching or common-centroid constraint is scored. Ideal external sources, loads and fixtures belong to the testbench, not the DUT.

## Operating Conditions

Temperature is 27 C. Typical IHP low-voltage MOS and resistor models; explicit finite physical tap models and a 1e12 ohm ngspice numerical shunt at each node. Candidate Magic RC is extracted with zero coupling-capacitance threshold.

VDD = 1.5 V; VSS = 0 V; input common mode = 0.75 V; differential input = -0.2 or +0.2 V. Each output has an external 10 kohm resistor to common mode and 1 pF to ground. DC checks both clock states (vctl = 0 or 1.5 V), giving four conditions. Transient clocks are complementary 0/1.5 V pulses, delay 1 us, rise/fall 2 ns, high width 5 us and period 10 us; output/max step is 0.1 ns with Gear order 2, stop time 12 us. A second transient sets both inputs to 0.75 V to separate clock feedthrough/injection from signal reversal. The finite clock slopes deliberately permit overlap; non-overlap operation is not claimed.

## Physical Requirements

Top cell `sw_002_chopper_diff`, named ports, resolved hierarchy, at most 10 MiB. Pass artifact, IHP main and maximal DRC, with density and antenna outside this standalone scope; strict named-port LVS; geometry, without DRC waivers. Functional bounding box must fit within 90 by 40 um. The footprint includes every process device and routing drawing layer in the frozen runtime outline list: active, wells, implants, poly, contacts, metals/vias and device/passive markers. Annotation and pin-purpose shapes are excluded. All functional routing must use drawing layers.

Every scored simulation consumes the submitted GDS-derived distributed wiring RC and extracted device geometry. Ron includes the declared terminal loading and common mode. Injection is net terminal charge integrated under driven equal inputs, not stored charge on a disconnected sampler. Noise, chopping an amplifier, RF/EM, mismatch and other clock rates are outside scope. Fabrication signoff is not claimed.

## Electrical Requirements and Scoring

All 4 operating conditions must complete. Every finite observation must meet its inclusive band; aggregation cannot hide a failing condition. Missing measurements/crossings or incomplete extraction do not establish success.

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
| `ron_p` | Absolute (selected positive-output input minus V(vb_p)) / current through its 10 kohm load | ohm | minimize / ratio | 0 … +∞ | 1e-06 |
| `ron_n` | Absolute (selected negative-output input minus V(vb_n)) / current through its 10 kohm load | ohm | minimize / ratio | 0 … +∞ | 1e-06 |
| `transfer` | DC output differential divided by the selected signed input differential | V/V | target / target | −∞ … +∞ | 1.0 |
| `common_error_v` | Absolute DC output common-mode minus 0.75 V | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `straight_gain` | Output differential / input differential at 4 us | V/V | target / target | −∞ … +∞ | 1.0 |
| `crossed_gain` | Output differential / input differential at 9 us | V/V | target / target | −∞ … +∞ | 1.0 |
| `common_glitch_v` | Maximum absolute output common-mode minus 0.75 V over 1–1.1 us with equal inputs | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `differential_glitch_v` | Maximum absolute output differential over 1–1.1 us with equal inputs | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `input_charge_c` | Absolute integral of I(VAP)+I(VAN) over 1–1.1 us with equal inputs | C | minimize / ratio | 0 … +∞ | 1e-21 |
| `clock_power_w` | Average positive supplied power from both clock sources over 2–12 us with equal inputs; returned energy is not credited | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **459.68 um2**. 10 expanded device instances; sum of device/contact envelopes 278.7760 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use reviewed resources from `/protocol/resources.json`. KLayout checks, Magic extracts RC, and ngspice simulates. Frozen constraints and requirements are in `/protocol/task.json`; `/protocol/harness.json` describes the harness. If available, use the published `process-feedback.v1` helper for interim checks. Write `/workspace/output/final.gds` and explicitly submit using `python -I /protocol/submit.py`.
