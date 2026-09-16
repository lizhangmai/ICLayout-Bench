# Externally Biased PMOS-Input Folded-Cascode OTA Layout Task

## Objective

Implement the fixed `amp_004_folded_cascode` circuit in GF180MCU D and submit self-contained GDS.
Fourteen MOS entries (17 instances after multiplicity expansion) form a PMOS-input folded-cascode OTA with a bias mirror and cascode branches. The two ideal internal voltage sources become explicit vb1/vb2 ports. Total MOS widths, lengths and multiplicities are retained; the maintained devices use single-finger geometry instead of the upstream nf settings. Source and extracted simulation both represent this maintained implementation.

## Inputs and Interface

`materials/circuit.spice` is authoritative for LVS and source calibration;
`materials/testbench.spice` defines every electrical measurement. This problem
is the description input. Ordered ports: `vinn vinp vout vdd ibias vss vb1 vb2`.
In order, these are: Negative input, positive input, output, supply, PMOS reference-current sink, return, NMOS cascode bias, and PMOS cascode bias.

Preserve the netlist's device connectivity, dimensions, multiplicities and body
connections. Provide physical well/substrate contacts to the declared rails.
Placement, routing, splitting and source/drain interchange are permitted only
where accepted by the declared LVS equivalence rules. No common-centroid or
statistical matching requirement is scored. Ideal external stimulus, bias and
load devices remain testbench apparatus and must not be placed inside the DUT.

## Operating Conditions

Use the typical GF180 3.3 V MOS models and physical poly models where present,
with statistical variation disabled. Unless swept explicitly, temperature is 27 C.
VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V; a 20 uA sink from ibias to VSS; VB1 = 1.2 V and VB2 = 1.95 V; external 1 pF output load. VINP has DC 1.65 V and AC +0.5 V. A 1 TH output-to-VINN inductor closes DC feedback; a 1 F coupling capacitor injects AC -0.5 V at VINN. The open-loop transfer is V(vout)/(V(vinp)-V(vinn)). These large L/C elements are external measurement apparatus. At 2.7 V the reduced headroom lowers gain and shifts the DC operating point.

AC uses 100 points per decade from 1 Hz to 1 GHz. Gain-stage transfer is
V(vout) for unit AC injection; differential-pair transfer is V(voutn)-V(voutp)
for unit differential excitation; the OTA transfer is defined above.

## Physical Requirements

Submit top cell `amp_004_folded_cascode` with every named electrical port, resolved hierarchy
and a file size at most 10 MiB. Artifact, GF180 variant-D DRC including antenna,
strict named-port LVS and geometry must pass, without DRC waivers. Chip-level
density and seal-ring closure are outside this standalone-block scope.

The functional bounding box must fit within 400 by 340 um. Area includes all
process device and routing drawing layers listed in runtime constraints:
wells, implants, active, poly, contacts, metals/vias and passive/device markers.
Annotation and pin-purpose shapes are excluded; all functional routing must use
drawing layers. The complete layer list is frozen in `/protocol/task.json`.

The judge independently extracts distributed wiring resistance and capacitance
from the submitted GDS, retaining candidate-derived MOS/passive geometry and
external body connections. Every scored simulation consumes that extracted DUT.
This model boundary does not include a distributed silicon substrate network.
The case measures small-signal unity-crossing phase margin with the declared load. Startup, large-signal settling, other loads, mismatch, noise, PVT and EM are outside scope. Manufacturing signoff is not claimed.

## Electrical Requirements and Scoring

All three operating conditions must complete and every observation must be finite
and meet its inclusive band. Aggregation cannot hide a failing condition;
missing crossings or incomplete extraction/simulation cannot establish success.
Saved waveforms provide the inputs for independently reconstructing observations.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output voltage; average of both outputs for the differential pair | V | 1.5 to 1.7 | <= 1.2 or >= 2 | bias |
| `bias_v` | DC V(ibias) | V | 1.75 to 2.55 | <= 1.4 or >= 2.9 | bias |
| `power_w` | DC power delivered by VDD, -V(vdd)*I(VDD) | W | 0 to 0.0003 | < 0 or >= 0.0006 | supply |
| `gain_db` | 20 log10(abs(transfer)) at 10 Hz | dB | >= 40 | <= 0 | response |
| `bandwidth_hz` | First frequency where transfer gain falls 3 dB below its 10 Hz value | Hz | >= 1000 | <= 0 | response |
| `unity_hz` | First falling 0 dB crossing of open-loop transfer | Hz | >= 9e+06 | <= 0 | response |
| `phase_margin` | 180 degrees plus unwrapped transfer phase at the unity crossing | deg | >= 55 | <= 0 | response |

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires passing physical
checks and complete extraction/measurements. `E` averages the applicable
response, bias and supply dimensions, each using its worst observation's
attainment. Attainment is 1 inside a band and falls linearly to its zero
boundary. `H` is 1 only when every electrical requirement passes.
`Q = clip((136000 - area_um2)/(136000 - 34000), 0, 1)` uses fixed absolute area
budgets. Physical rejection scores 0; blocking evaluator errors produce no
score. The coefficient is 5; it describes the circuit's required capability,
not its source device count or observed model performance.

## Tools and Submission

Use the reviewed GF180 resources listed in `/protocol/resources.json`.
KLayout checks the layout, Magic extracts RC and ngspice simulates the circuit.
`/protocol/task.json` provides frozen constraints and evaluation requirements;
`/protocol/harness.json` describes the harness. If `process-feedback.v1` is
exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then explicitly submit with
`python -I /protocol/submit.py`.
