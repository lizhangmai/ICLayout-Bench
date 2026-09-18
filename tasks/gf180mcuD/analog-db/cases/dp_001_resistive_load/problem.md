# Resistively Loaded Differential Pair Layout Task

## Objective

Implement the fixed `dp_001_resistive_load` circuit in GF180MCU D and submit self-contained GDS.
Four NMOS devices form a differential input pair and tail-current mirror. Two physical GF180 ppolyf_u_1k loads each have width 2 um and length 44 um (22 squares, nominally 22 kohm). MOS dimensions and the resistor ratio follow the fixed binding; the ideal source resistors become process devices with substrate terminals at VSS.

## Inputs and Interface

`materials/circuit.spice` is authoritative for LVS and source calibration;
`materials/testbench.spice` defines every electrical measurement. This problem
is the description input. Ordered ports: `vdd voutp voutn vinp vinn ibias vss`.
In order, these are: Supply, output on the vinp branch, output on the vinn branch, positive input, negative input, NMOS reference-current input, and return.

Preserve the netlist's device connectivity, dimensions, multiplicities and body
connections. Provide physical well/substrate contacts to the declared rails.
Placement, routing, splitting and source/drain interchange are permitted only
where accepted by the declared LVS equivalence rules. No common-centroid or
statistical matching requirement is scored. Ideal external stimulus, bias and
load devices remain testbench apparatus and must not be placed inside the DUT.

## Operating Conditions

Use the typical GF180 3.3 V MOS models and physical poly models where present,
with statistical variation disabled. Unless swept explicitly, temperature is 27 C.
VDD = 3.3 V, VSS = 0 V; 20 uA from VDD into ibias; input common mode = 1.2, 1.65 and 2.1 V; external 1 pF on each output. The input differential signal is split +0.5/-0.5 around common mode. AC differential amplitude is 1 V. DC transfer sweeps differential input from -10.1 to +10.1 mV in 0.1 mV increments; requirements use only -10 to +10 mV. Output differential voltage is V(voutn)-V(voutp).

AC uses 100 points per decade from 1 Hz to 1 GHz. Gain-stage transfer is
V(vout) for unit AC injection; differential-pair transfer is V(voutn)-V(voutp)
for unit differential excitation; the OTA transfer is defined above.

## Physical Requirements

Submit top cell `dp_001_resistive_load` with every named electrical port, resolved hierarchy
and a file size at most 10 MiB. Artifact, GF180 variant-D DRC including antenna,
strict named-port LVS and geometry must pass, without DRC waivers. Chip-level
density and seal-ring closure are outside this standalone-block scope.

The functional bounding box must fit within 160 by 160 um. Area includes all
process device and routing drawing layers listed in runtime constraints:
wells, implants, active, poly, contacts, metals/vias and passive/device markers.
Annotation and pin-purpose shapes are excluded; all functional routing must use
drawing layers. The complete layer list is frozen in `/protocol/task.json`.

The judge independently extracts distributed wiring resistance and capacitance
from the submitted GDS, retaining candidate-derived MOS/passive geometry and
external body connections. Every scored simulation consumes that extracted DUT.
This model boundary does not include a distributed silicon substrate network.
The output has a high common-mode level; it is not a rail-to-rail amplifier. Transient settling, mismatch, noise, PVT and EM are outside scope. Manufacturing signoff is not claimed.

## Electrical Requirements and Scoring

All three operating conditions must complete and every observation must be finite
and meet its inclusive band. Aggregation cannot hide a failing condition;
missing crossings or incomplete extraction/simulation cannot establish success.
Saved waveforms provide the inputs for independently reconstructing observations.

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
| `output_v` | DC output voltage; average of both outputs for the differential pair | V | target / target | 0 … 3.3 | 3.3 |
| `imbalance_v` | Absolute DC difference between the two outputs | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `bias_v` | DC V(ibias) | V | target / target | 0 … 3.3 | 3.3 |
| `power_w` | DC power delivered by VDD, -V(vdd)*I(VDD) | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `gain_db` | 20 log10(abs(transfer)) at 10 Hz | dB | maximize / db20 | −∞ … +∞ | — |
| `bandwidth_hz` | First frequency where transfer gain falls 3 dB below its 10 Hz value | Hz | maximize / ratio | 0 … +∞ | — |
| `linearity_v` | Maximum absolute differential-output deviation from the line joining the -10/+10 mV samples | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `slope` | Differential-output endpoint difference divided by 20 mV | V/V | target / target | −∞ … +∞ | 5 |

Area reference: **925.98 um2**. 6 expanded device instances; sum of device/contact envelopes 552.0000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **4**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use the reviewed GF180 resources listed in `/protocol/resources.json`.
KLayout checks the layout, Magic extracts RC and ngspice simulates the circuit.
`/protocol/task.json` provides frozen constraints and evaluation requirements;
`/protocol/harness.json` describes the harness. If `process-feedback.v1` is
exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then explicitly submit with
`python -I /protocol/submit.py`.

Use a GDS database unit of 0.001 um, as required by the GF180MCU DRC deck.
