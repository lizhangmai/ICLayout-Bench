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

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output voltage; average of both outputs for the differential pair | V | 2.9 to 3.15 | <= 2.5 or >= 3.3 | bias |
| `imbalance_v` | Absolute DC difference between the two outputs | V | 0 to 0.002 | < 0 or >= 0.02 | bias |
| `bias_v` | DC V(ibias) | V | 0.6 to 0.67 | <= 0.4 or >= 0.9 | bias |
| `power_w` | DC power delivered by VDD, -V(vdd)*I(VDD) | W | 0 to 0.00018 | < 0 or >= 0.0003 | supply |
| `gain_db` | 20 log10(abs(transfer)) at 10 Hz | dB | >= 10 | <= 0 | response |
| `bandwidth_hz` | First frequency where transfer gain falls 3 dB below its 10 Hz value | Hz | >= 7e+06 | <= 0 | response |
| `linearity_v` | Maximum absolute differential-output deviation from the line joining the -10/+10 mV samples | V | 0 to 0.0001 | < 0 or >= 0.001 | response |
| `slope` | Differential-output endpoint difference divided by 20 mV | V/V | 3 to 5 | <= 0 or >= 8 | response |

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires passing physical
checks and complete extraction/measurements. `E` averages the applicable
response, bias and supply dimensions, each using its worst observation's
attainment. Attainment is 1 inside a band and falls linearly to its zero
boundary. `H` is 1 only when every electrical requirement passes.
`Q = clip((26000 - area_um2)/(26000 - 6500), 0, 1)` uses fixed absolute area
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
