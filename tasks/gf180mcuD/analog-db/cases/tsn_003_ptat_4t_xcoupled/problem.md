# Four-Transistor Positive-Temperature-Slope Core Layout Task

## Objective

Implement the fixed `tsn_003_ptat_4t_xcoupled` circuit in GF180MCU D and submit self-contained GDS.
Two NMOS and two PMOS devices form a resistorless temperature-dependent voltage core with cross-coupled bias connections. The fixed GF180 sizes are retained. The output increases with temperature under each declared supply, but both voltage and slope depend strongly on supply. This is a temperature-slope layout task, not a precision reference or calibrated thermometer.

## Inputs and Interface

`materials/circuit.spice` is authoritative for LVS and source calibration;
`materials/testbench.spice` defines every electrical measurement. This problem
is the description input. Ordered ports: `vdd vout vss`.
In order, these are: Supply, unloaded temperature-dependent output, and return.

Preserve the netlist's device connectivity, dimensions, multiplicities and body
connections. Provide physical well/substrate contacts to the declared rails.
Placement, routing, splitting and source/drain interchange are permitted only
where accepted by the declared LVS equivalence rules. No common-centroid or
statistical matching requirement is scored. Ideal external stimulus, bias and
load devices remain testbench apparatus and must not be placed inside the DUT.

## Operating Conditions

Use the typical GF180 3.3 V MOS models and physical poly models where present,
with statistical variation disabled. Unless swept explicitly, temperature is 27 C.
VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V. Measure the operating point at 27 C, then sweep temperature from -20 to 100 C inclusive in 1 C steps at each supply. The output is unloaded except for the measurement probe. No ideal internal source or passive is added.

## Physical Requirements

Submit top cell `tsn_003_ptat_4t_xcoupled` with every named electrical port, resolved hierarchy
and a file size at most 10 MiB. Artifact, GF180 variant-D DRC including antenna,
strict named-port LVS and geometry must pass, without DRC waivers. Chip-level
density and seal-ring closure are outside this standalone-block scope.

The functional bounding box must fit within 120 by 60 um. Area includes all
process device and routing drawing layers listed in runtime constraints:
wells, implants, active, poly, contacts, metals/vias and passive/device markers.
Annotation and pin-purpose shapes are excluded; all functional routing must use
drawing layers. The complete layer list is frozen in `/protocol/task.json`.

The judge independently extracts distributed wiring resistance and capacitance
from the submitted GDS, retaining candidate-derived MOS/passive geometry and
external body connections. Every scored simulation consumes that extracted DUT.
This model boundary does not include a distributed silicon substrate network.
The temperature sweep is a nominal model sweep, not process-corner or statistical qualification. Startup, output drive, absolute temperature accuracy, supply rejection, mismatch, noise and EM are outside scope. Manufacturing signoff is not claimed.

## Electrical Requirements and Scoring

All three operating conditions must complete and every observation must be finite
and meet its inclusive band. Aggregation cannot hide a failing condition;
missing crossings or incomplete extraction/simulation cannot establish success.
Saved waveforms provide the inputs for independently reconstructing observations.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output voltage; average of both outputs for the differential pair | V | 0.11 to 0.18 | <= 0 or >= 0.3 | bias |
| `power_w` | DC power delivered by VDD, -V(vdd)*I(VDD) | W | 0 to 0.0003 | < 0 or >= 0.0006 | supply |
| `cold_v` | Output at -20 C | V | 0.1 to 0.16 | <= 0 or >= 0.3 | bias |
| `hot_v` | Output at 100 C | V | 0.13 to 0.21 | <= 0 or >= 0.35 | bias |
| `slope_v_per_c` | (Output at 100 C - output at -20 C)/120 C | V/C | 0.00024 to 0.00036 | <= 0 or >= 0.0006 | response |
| `curvature_v` | Maximum deviation from the endpoint line over all 121 temperature samples | V | 0 to 0.0002 | < 0 or >= 0.002 | response |
| `minimum_slope` | Minimum ngspice deriv(output) over the temperature sweep | V/C | >= 0.00024 | <= 0 | response |
| `maximum_slope` | Maximum ngspice deriv(output) over the temperature sweep | V/C | <= 0.00036 | >= 0.0006 | response |
| `peak_power_w` | Maximum -V(vdd)*I(VDD) over the full temperature sweep or comparator transient | W | 0 to 0.00032 | < 0 or >= 0.0006 | supply |

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires passing physical
checks and complete extraction/measurements. `E` averages the applicable
response, bias and supply dimensions, each using its worst observation's
attainment. Attainment is 1 inside a band and falls linearly to its zero
boundary. `H` is 1 only when every electrical requirement passes.
`Q = clip((6000 - area_um2)/(6000 - 1500), 0, 1)` uses fixed absolute area
budgets. Physical rejection scores 0; blocking evaluator errors produce no
score. The coefficient is 3; it describes the circuit's required capability,
not its source device count or observed model performance.

## Tools and Submission

Use the reviewed GF180 resources listed in `/protocol/resources.json`.
KLayout checks the layout, Magic extracts RC and ngspice simulates the circuit.
`/protocol/task.json` provides frozen constraints and evaluation requirements;
`/protocol/harness.json` describes the harness. If `process-feedback.v1` is
exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then explicitly submit with
`python -I /protocol/submit.py`.
