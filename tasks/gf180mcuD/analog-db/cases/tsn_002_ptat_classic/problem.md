# Self-Starting Isolated-Body PTAT Core Layout Task

## Objective

Implement `tsn_002_ptat_classic` in GF180MCU D and submit self-contained GDS.
The resistor-degenerated four-MOS core produces a positive temperature slope.
A maintained three-MOS startup branch establishes its operating state after
power-up. Supply sensitivity remains: this is not a precision temperature
reference or a calibrated thermometer.

## Inputs and Interface

`materials/circuit.cdl` is the physical LVS authority;
`materials/circuit.spice` is its simulator representation.
`materials/testbench.spice` defines stimuli and observations. This problem is
the description input. Ordered ports are `vdd vout vss`: supply,
temperature-dependent output and return.

Retain all device dimensions, multiplicities and four-terminal connections.
The 8/1 um core NMOS has both source and body on `vout`; its body must remain
isolated from VSS. The physical primitive `MM0 ... nfet_03v3_dn` maps to
`XM0 ... nfet_03v3` in the simulator, with the same D/G/S/B and W/L/m.
Use an isolated P-well inside a supply-tied deep N-well, with explicit
N-well enclosure and physical well/substrate contacts. Extraction must retain
the separation between the output body and substrate return. No body-to-VSS
substitution is permitted. The core resistor is physical 1 kohm/square poly,
W=2 um, L=40 um, nominal 20 kohm.

The added startup devices have W/L of 0.42/20 um (weak PMOS pull-up),
2/0.28 um (NMOS detector) and 0.42/1 um (NMOS injector). The detector reduces
the startup control voltage after bias is established, turning off the
injection path. The weak pull-up/detector branch still draws static current;
all DUT supply power is measured. Preserve this branch as part of the DUT.
Placement, routing, splitting and source/drain interchange are permitted only
where accepted by the declared LVS equivalence rules. No statistical matching
or placement style is scored. External stimulus and the output load belong to
the testbench and must not be placed inside the DUT.

## Operating Conditions

Use typical GF180 3.3 V MOS and poly models with statistical variation disabled.
VSS is 0 V. Evaluate all 18 combinations of VDD = 2.7/3.0/3.3 V,
temperature = -20/27/100 C and supply rise time = 0.1/10 us.
Each condition measures its DC operating point and a -20 to 100 C sweep in
1 C steps. The temperature is then restored to the selected value before
startup simulation. The external output capacitance is exactly 100 fF.

For startup, ramp VDD linearly from 0 to its selected value, then hold it.
Use a zero-initial-state `uic` transient through 100 us with no internal
initial-condition bias or auxiliary startup source. Gear order 2 and a
maximum timestep of 1 ns are declared. Measure final error, ripple and average
power over 90–100 us. Success establishes settling by this window; it does
not bound the first crossing or transient overshoot.

## Physical Requirements

Submit top cell `tsn_002_ptat_classic`, all named electrical ports, resolved
hierarchy and at most 10 MiB. Artifact, GF180 variant-D DRC including antenna,
strict named-port LVS and geometry must pass with no DRC waivers. Chip-level
density and seal-ring closure are outside this standalone-block scope.

The functional bounding box must fit within 220 by 65 um. Its area includes
all declared device and routing drawing layers: wells (including deep N-well
and isolated P-well), implants, active, poly, contacts, metals/vias and device
markers. Annotation and pin-purpose shapes are excluded. All functional
routing must use drawing layers. `/protocol/task.json` freezes the layer set.

Independent candidate extraction retains MOS and resistor geometry and adds
distributed wiring RC. All scored simulation consumes that extracted DUT.
This does not include a distributed silicon substrate model. Larger output
loads are unqualified and can cause oscillation; this is not a pF-load output
buffer. Brownout/restart, arbitrary supply ramps, process/statistical corners,
noise, absolute temperature accuracy, supply rejection, EM and fabrication
signoff are outside scope.

## Electrical Requirements and Scoring

Every observation in every condition must be finite and satisfy its inclusive
acceptance band. Aggregation cannot hide a failing condition. Temperature
measurements use the complete sampled sweep; startup measurements use the
explicit final window. Saved operating-point, temperature and transient
waveforms support independent reconstruction.

| Metric | Definition | Unit | Acceptance | Zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- | --- |
| `output_v` | DC output at the selected supply and temperature | V | 0.1 to 0.19 | <= 0 or >= 0.3 | bias |
| `power_w` | DC delivered supply power, -V(vdd)*I(VDD), including startup bias | W | 0 to 8e-05 | < 0 or >= 0.00016 | supply |
| `cold_v` | Output at -20 C | V | 0.11 to 0.13 | <= 0 or >= 0.25 | bias |
| `hot_v` | Output at 100 C | V | 0.16 to 0.18 | <= 0 or >= 0.3 | bias |
| `slope_v_per_c` | (hot_v - cold_v)/120 C | V/C | 0.0004 to 0.00047 | <= 0.0002 or >= 0.0006 | response |
| `curvature_v` | Maximum absolute deviation from the endpoint line at all 121 temperatures | V | 0 to 0.003 | < 0 or >= 0.01 | response |
| `minimum_slope` | Minimum ngspice deriv(output) over temperature | V/C | 0.0003 to 0.00055 | <= 0 or >= 0.001 | response |
| `maximum_slope` | Maximum ngspice deriv(output) over temperature | V/C | 0.0003 to 0.00055 | <= 0 or >= 0.001 | response |
| `peak_power_w` | Maximum delivered supply power over temperature | W | 0 to 8e-05 | < 0 or >= 0.00016 | supply |
| `startup_error_v` | Maximum absolute output error against the selected DC operating point during 90–100 us | V | 0 to 0.001 | < 0 or >= 0.02 | response |
| `ripple_v` | Maximum minus minimum output during 90–100 us | V | 0 to 0.001 | < 0 or >= 0.02 | response |
| `final_power_w` | Time-average delivered supply power during 90–100 us | W | 0 to 8e-05 | < 0 or >= 0.00016 | supply |

Scoring is `S = G * (60*E + 20*H + 20*H*Q)`. `G` requires passing physical
checks and complete extraction/measurements. `E` averages response, bias and
supply, each using its worst observation's attainment. Attainment is 1 in the
acceptance band and decreases linearly to its zero boundary. `H` is 1 only
when all electrical observations pass.
`Q = clip((56000 - area_um2)/(56000 - 14000), 0, 1)` uses fixed absolute
area anchors. Physical rejection scores 0; blocking evaluator errors have no
score. Coefficient 6 reflects coupled startup, temperature behavior and
isolated-body physical implementation.

## Tools and Submission

Use the reviewed GF180 resources in `/protocol/resources.json`. KLayout checks
physical validity and geometry, Magic extracts RC and ngspice simulates the
circuit. `/protocol/task.json` provides frozen requirements and
`/protocol/harness.json` describes the harness. When `process-feedback.v1` is
exposed, use its published helper for interim checks. Write
`/workspace/output/final.gds`, then submit with `python -I /protocol/submit.py`.
