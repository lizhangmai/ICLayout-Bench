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

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output voltage; average of both outputs for the differential pair | V | 0.68 to 0.76 | <= 0.5 or >= 0.95 | bias |
| `bias_v` | DC V(ibias) | V | 0.4 to 1.15 | <= 0 or >= 1.5 | bias |
| `power_w` | DC power delivered by VDD, -V(vdd)*I(VDD) | W | 0 to 0.00022 | < 0 or >= 0.0004 | supply |
| `gain_db` | 20 log10(abs(transfer)) at 10 Hz | dB | >= 30 | <= 0 | response |
| `bandwidth_hz` | First frequency where transfer gain falls 3 dB below its 10 Hz value | Hz | >= 450000 | <= 0 | response |

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires passing physical
checks and complete extraction/measurements. `E` averages the applicable
response, bias and supply dimensions, each using its worst observation's
attainment. Attainment is 1 inside a band and falls linearly to its zero
boundary. `H` is 1 only when every electrical requirement passes.
`Q = clip((28000 - area_um2)/(28000 - 7000), 0, 1)` uses fixed absolute area
budgets. Physical rejection scores 0; blocking evaluator errors produce no
score. The coefficient is 4; it describes the circuit's required capability,
not its source device count or observed model performance.

## Tools and Submission

Use the reviewed GF180 resources listed in `/protocol/resources.json`.
KLayout checks the layout, Magic extracts RC and ngspice simulates the circuit.
`/protocol/task.json` provides frozen constraints and evaluation requirements;
`/protocol/harness.json` describes the harness. If `process-feedback.v1` is
exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then explicitly submit with
`python -I /protocol/submit.py`.
