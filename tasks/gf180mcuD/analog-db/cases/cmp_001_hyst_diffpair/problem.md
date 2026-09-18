# Resistive-Feedback Hysteretic Comparator Layout Task

## Objective

Implement the fixed `cmp_001_hyst_diffpair` circuit in GF180MCU D and submit self-contained GDS.
A differential input stage, resistive positive feedback and three output inverters form a hysteretic comparator. Twelve MOS entries expand to 28 physical instances. The physical ppolyf_u_1k resistors are width 2 um: two 600 um feedback devices (300 squares) and one 12 um tail device (6 squares). MOS sizes and multiplicities are retained; ideal resistors become substrate-connected process devices.

## Inputs and Interface

`materials/circuit.spice` is authoritative for LVS and source calibration;
`materials/testbench.spice` defines every electrical measurement. This problem
is the description input. Ordered ports: `vdd vout vinp vinn vss`.
In order, these are: Supply, digital output, swept positive input, fixed negative input, and return.

Preserve the netlist's device connectivity, dimensions, multiplicities and body
connections. Provide physical well/substrate contacts to the declared rails.
Placement, routing, splitting and source/drain interchange are permitted only
where accepted by the declared LVS equivalence rules. No common-centroid or
statistical matching requirement is scored. Ideal external stimulus, bias and
load devices remain testbench apparatus and must not be placed inside the DUT.

## Operating Conditions

Use the typical GF180 3.3 V MOS models and physical poly models where present,
with statistical variation disabled. Unless swept explicitly, temperature is 27 C.
VDD = 3.3 V, VSS = 0 V, VINN = 1.65 V. VINP stays at 1.45 V through 0.1 ms, ramps to 1.85 V at 1.1 ms, holds through 1.2 ms, ramps back to 1.45 V at 2.2 ms, then holds through 2.3 ms. Each ramp magnitude is 0.4 V/ms. Evaluate external loads of 1, 5 and 10 pF separately with a 0.2 us transient output step. The transient starts from its DC operating point.

## Physical Requirements

Submit top cell `cmp_001_hyst_diffpair` with every named electrical port, resolved hierarchy
and a file size at most 10 MiB. Artifact, GF180 variant-D DRC including antenna,
strict named-port LVS and geometry must pass, without DRC waivers. Chip-level
density and seal-ring closure are outside this standalone-block scope.

The functional bounding box must fit within 1300 by 200 um. Area includes all
process device and routing drawing layers listed in runtime constraints:
wells, implants, active, poly, contacts, metals/vias and passive/device markers.
Annotation and pin-purpose shapes are excluded; all functional routing must use
drawing layers. The complete layer list is frozen in `/protocol/task.json`.

The judge independently extracts distributed wiring resistance and capacitance
from the submitted GDS, retaining candidate-derived MOS/passive geometry and
external body connections. Every scored simulation consumes that extracted DUT.
This model boundary does not include a distributed silicon substrate network.
Thresholds include this finite ramp rate and output load. Offset is intentional and is not zero-centered about VINN. Metastability, fast decision delay, startup, noise, statistical offset, PVT and EM are outside scope. Manufacturing signoff is not claimed.

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
| `rising_input` | Interpolated VINP at the first rising VOUT = 1.65 V crossing | V | target / target | 0 … 3.3 | 3.3 |
| `falling_input` | Interpolated VINP at the first falling VOUT = 1.65 V crossing | V | target / target | 0 … 3.3 | 3.3 |
| `hysteresis_v` | Rising-input threshold minus falling-input threshold | V | target / target | 0 … 3.3 | 3.3 |
| `mean_power_w` | Time-average -V(vdd)*I(VDD) over the full 0–2.3 ms transient | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `low_v` | Maximum VOUT over 0.02–0.08 ms | V | functional check | 0 … 0.1 | — |
| `high_v` | Minimum VOUT over 1.12–1.18 ms | V | functional check | 3.2 … 3.31 | — |

Area reference: **8386.58 um2**. 31 expanded device instances; sum of device/contact envelopes 5392.5600 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
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
