# Self-Biased Cascode Common-Source Gain Stage Layout Task

## Objective

Implement the fixed `gs_001_cascode_cs` circuit in GF180MCU D and submit self-contained GDS.
Nine MOS devices form a cascode common-source stage with PMOS and NMOS bias ladders. An external 20 uA sink biases the PMOS ladder. Total widths, lengths and multiplicities follow the fixed GF180 binding. Physical body contacts and an independently constructed reference complete the circuit.

## Inputs and Interface

`materials/circuit.spice` is authoritative for LVS and source calibration;
`materials/testbench.spice` defines every electrical measurement. This problem
is the description input. Ordered ports: `vdd vout vin ibias vss`.
In order, these are: Supply, output, signal input, PMOS reference-current sink, and return.

Preserve the netlist's device connectivity, dimensions, multiplicities and body
connections. Provide physical well/substrate contacts to the declared rails.
Placement, routing, splitting and source/drain interchange are permitted only
where accepted by the declared LVS equivalence rules. No common-centroid or
statistical matching requirement is scored. Ideal external stimulus, bias and
load devices remain testbench apparatus and must not be placed inside the DUT.

## Operating Conditions

Use the typical GF180 3.3 V MOS models and physical poly models where present,
with statistical variation disabled. Unless swept explicitly, temperature is 27 C.
VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V; external 20 uA sink from ibias to VSS; external 1 pF output load. A 1 TH external inductor connects output to input for the DC trip-point solve. A 1 F external coupling capacitor injects a unit AC input through acin while isolating the DC fixture. This measures open-loop small-signal gain at each self-biased trip point; it does not prescribe a fixed DC input voltage.

AC uses 100 points per decade from 1 Hz to 1 GHz. Gain-stage transfer is
V(vout) for unit AC injection; differential-pair transfer is V(voutn)-V(voutp)
for unit differential excitation; the OTA transfer is defined above.

## Physical Requirements

Submit top cell `gs_001_cascode_cs` with every named electrical port, resolved hierarchy
and a file size at most 10 MiB. Artifact, GF180 variant-D DRC including antenna,
strict named-port LVS and geometry must pass, without DRC waivers. Chip-level
density and seal-ring closure are outside this standalone-block scope.

The functional bounding box must fit within 220 by 120 um. Area includes all
process device and routing drawing layers listed in runtime constraints:
wells, implants, active, poly, contacts, metals/vias and passive/device markers.
Annotation and pin-purpose shapes are excluded; all functional routing must use
drawing layers. The complete layer list is frozen in `/protocol/task.json`.

The judge independently extracts distributed wiring resistance and capacitance
from the submitted GDS, retaining candidate-derived MOS/passive geometry and
external body connections. Every scored simulation consumes that extracted DUT.
This model boundary does not include a distributed silicon substrate network.
Transient settling, fixed-input bias robustness, noise, mismatch, PVT and EM are outside scope. Manufacturing signoff is not claimed.

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
| `bias_v` | DC V(ibias) | V | target / target | 0 … 3.3 | 3.3 |
| `power_w` | DC power delivered by VDD, -V(vdd)*I(VDD) | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `gain_db` | 20 log10(abs(transfer)) at 10 Hz | dB | maximize / db20 | −∞ … +∞ | — |
| `bandwidth_hz` | First frequency where transfer gain falls 3 dB below its 10 Hz value | Hz | maximize / ratio | 0 … +∞ | — |

Area reference: **394.4 um2**. 9 expanded device instances; sum of device/contact envelopes 220.6500 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

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
