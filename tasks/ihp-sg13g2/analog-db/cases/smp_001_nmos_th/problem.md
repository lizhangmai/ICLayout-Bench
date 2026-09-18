# Physical NMOS Sample-and-Hold Layout Task

## Objective

Implement `smp_001_nmos_th`: a single-NMOS sampling switch with an internal
physical storage capacitor. Preserve the switch and stored-charge node, and
meet acquisition, turn-off pedestal, isolated-input feedthrough, hold drift
and reacquisition requirements at the specified input and temperature points.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative native physical circuit.
- `materials/circuit.spice`: equivalent simulator representation.
- `materials/testbench.spice`: independent stimuli and measurements.

The ordered interface is `vin clk vout vss`. VIN is driven through an external
1 kohm source resistance; CLK receives the external clock; VOUT is the storage
node. The source's unused VDD port is removed. There is no DUT supply-current
metric or added artificial supply connection. Tie VSS to ground.

Retain the `sg13_lv_nmos` with W=2 um, L=0.13 um, m=1 and drain/gate/source
connected to VIN/CLK/VOUT. Its body connects through the explicit VSS substrate
tap. One `cap_cmim` with W=L=18.2 um connects its top plate to VOUT and bottom
plate to VSS, nominally 499.772 fF at TT, 27 C. Preserve plate orientation.
The capacitor is internal physical storage, not a testbench load or an ideal
replacement. The native and simulator circuits include the same explicit tap.

Preserve models, sizes and connectivity. Equivalent parallel fingering is
permitted only when all physical and electrical checks pass. Do not add a
buffer, complementary switch, dummy cancellation device, hold-node servo,
external storage capacitor or other topology change.

## Operating Conditions

Use typical MOS and capacitor models at 27 and 85 C. CLK is externally driven
between 0 and 1.2 V, with 2 ns linear transitions. The ideal signal source SRC
drives VIN through 1 kohm. Qualify four sampled levels, `sample_v` = 0.1, 0.4,
0.6 and 0.7 V, at both temperatures. At each point the off-state input is
separately driven to `hold_v` = 0 or 1.2 V: sixteen conditions. These are
specified sample points, not rail-to-rail or continuous-range qualification.

The finite sequence starts from a solved DC operating point with SRC=0 and
CLK=1.2 V. SRC moves to `sample_v` during 20–22 ns. CLK falls during
200–202 ns, isolating the storage node. SRC moves to `hold_v` during
400–402 ns while CLK remains zero. SRC returns to `sample_v` during
11.2–11.202 us; CLK rises during 11.4–11.402 us. Stop at 11.7 us.
No output load, DC bias source or discharge resistor is attached to VOUT.

Use Gear order 2, KLU, maximum time step 2 ns, `gmin=1e-15`,
`rshunt=1e15`, `reltol=1e-6`, `abstol=1e-15` and `vntol=1e-9`.
The numerical shunt is not a specified physical retention load. Save SRC,
VIN, CLK, VOUT and both ideal voltage-source currents.

## Physical Requirements

Submit GDSII top cell `smp_001_nmos_th`, at most 10 MiB, within an 80 × 80 um
functional outline. Pass native IHP main/maximal DRC without waivers
(standalone scope with density/antenna disabled), strict named-port LVS,
functional geometry and candidate-derived Magic RC extraction. Functional
area includes the complete device/contact/routing layers enumerated by the
runtime outline; annotation and pin layers do not count.

Post-layout simulation must consume the submitted layout's extracted NMOS,
physical MIM, junction geometry and interconnect RC. The isolated Magic import
uses half-grid subdivision and `gds_readonly=false`; the submitted GDS remains
immutable. No diagnostic is waived. Source simulation retains the finite tap
model; Magic idealizes the tap connection. Distributed substrate noise and
fabrication signoff are outside this contract.

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
| `track_error_v` | condition_0:track_error_v, condition_1:track_error_v, condition_2:track_error_v, condition_3:track_error_v, condition_4:track_error_v, condition_5:track_error_v, condition_6:track_error_v, condition_7:track_error_v, condition_8:track_error_v, condition_9:track_error_v, condition_10:track_error_v, condition_11:track_error_v, condition_12:track_error_v, condition_13:track_error_v, condition_14:track_error_v, condition_15:track_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `pedestal_abs_v` | condition_0:pedestal_abs_v, condition_1:pedestal_abs_v, condition_2:pedestal_abs_v, condition_3:pedestal_abs_v, condition_4:pedestal_abs_v, condition_5:pedestal_abs_v, condition_6:pedestal_abs_v, condition_7:pedestal_abs_v, condition_8:pedestal_abs_v, condition_9:pedestal_abs_v, condition_10:pedestal_abs_v, condition_11:pedestal_abs_v, condition_12:pedestal_abs_v, condition_13:pedestal_abs_v, condition_14:pedestal_abs_v, condition_15:pedestal_abs_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `feedthrough_peak_v` | condition_0:feedthrough_peak_v, condition_1:feedthrough_peak_v, condition_2:feedthrough_peak_v, condition_3:feedthrough_peak_v, condition_4:feedthrough_peak_v, condition_5:feedthrough_peak_v, condition_6:feedthrough_peak_v, condition_7:feedthrough_peak_v, condition_8:feedthrough_peak_v, condition_9:feedthrough_peak_v, condition_10:feedthrough_peak_v, condition_11:feedthrough_peak_v, condition_12:feedthrough_peak_v, condition_13:feedthrough_peak_v, condition_14:feedthrough_peak_v, condition_15:feedthrough_peak_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `hold_drift_v` | condition_0:hold_drift_v, condition_1:hold_drift_v, condition_2:hold_drift_v, condition_3:hold_drift_v, condition_4:hold_drift_v, condition_5:hold_drift_v, condition_6:hold_drift_v, condition_7:hold_drift_v, condition_8:hold_drift_v, condition_9:hold_drift_v, condition_10:hold_drift_v, condition_11:hold_drift_v, condition_12:hold_drift_v, condition_13:hold_drift_v, condition_14:hold_drift_v, condition_15:hold_drift_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `hold_error_v` | condition_0:hold_error_v, condition_1:hold_error_v, condition_2:hold_error_v, condition_3:hold_error_v, condition_4:hold_error_v, condition_5:hold_error_v, condition_6:hold_error_v, condition_7:hold_error_v, condition_8:hold_error_v, condition_9:hold_error_v, condition_10:hold_error_v, condition_11:hold_error_v, condition_12:hold_error_v, condition_13:hold_error_v, condition_14:hold_error_v, condition_15:hold_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `reacquire_error_v` | condition_0:reacquire_error_v, condition_1:reacquire_error_v, condition_2:reacquire_error_v, condition_3:reacquire_error_v, condition_4:reacquire_error_v, condition_5:reacquire_error_v, condition_6:reacquire_error_v, condition_7:reacquire_error_v, condition_8:reacquire_error_v, condition_9:reacquire_error_v, condition_10:reacquire_error_v, condition_11:reacquire_error_v, condition_12:reacquire_error_v, condition_13:reacquire_error_v, condition_14:reacquire_error_v, condition_15:reacquire_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `clock_energy_j` | condition_0:clock_energy_j, condition_1:clock_energy_j, condition_2:clock_energy_j, condition_3:clock_energy_j, condition_4:clock_energy_j, condition_5:clock_energy_j, condition_6:clock_energy_j, condition_7:clock_energy_j, condition_8:clock_energy_j, condition_9:clock_energy_j, condition_10:clock_energy_j, condition_11:clock_energy_j, condition_12:clock_energy_j, condition_13:clock_energy_j, condition_14:clock_energy_j, condition_15:clock_energy_j | J | minimize / ratio | 0 … +∞ | 1e-21 |
| `target` | condition_0:target, condition_1:target, condition_2:target, condition_3:target, condition_4:target, condition_5:target, condition_6:target, condition_7:target, condition_8:target, condition_9:target, condition_10:target, condition_11:target, condition_12:target, condition_13:target, condition_14:target, condition_15:target | V | diagnostic | −∞ … +∞ | — |
| `track_v` | condition_0:track_v, condition_1:track_v, condition_2:track_v, condition_3:track_v, condition_4:track_v, condition_5:track_v, condition_6:track_v, condition_7:track_v, condition_8:track_v, condition_9:track_v, condition_10:track_v, condition_11:track_v, condition_12:track_v, condition_13:track_v, condition_14:track_v, condition_15:track_v | V | diagnostic | −∞ … +∞ | — |
| `held_v` | condition_0:held_v, condition_1:held_v, condition_2:held_v, condition_3:held_v, condition_4:held_v, condition_5:held_v, condition_6:held_v, condition_7:held_v, condition_8:held_v, condition_9:held_v, condition_10:held_v, condition_11:held_v, condition_12:held_v, condition_13:held_v, condition_14:held_v, condition_15:held_v | V | diagnostic | −∞ … +∞ | — |
| `before_input_v` | condition_0:before_input_v, condition_1:before_input_v, condition_2:before_input_v, condition_3:before_input_v, condition_4:before_input_v, condition_5:before_input_v, condition_6:before_input_v, condition_7:before_input_v, condition_8:before_input_v, condition_9:before_input_v, condition_10:before_input_v, condition_11:before_input_v, condition_12:before_input_v, condition_13:before_input_v, condition_14:before_input_v, condition_15:before_input_v | V | diagnostic | −∞ … +∞ | — |
| `after_input_v` | condition_0:after_input_v, condition_1:after_input_v, condition_2:after_input_v, condition_3:after_input_v, condition_4:after_input_v, condition_5:after_input_v, condition_6:after_input_v, condition_7:after_input_v, condition_8:after_input_v, condition_9:after_input_v, condition_10:after_input_v, condition_11:after_input_v, condition_12:after_input_v, condition_13:after_input_v, condition_14:after_input_v, condition_15:after_input_v | V | diagnostic | −∞ … +∞ | — |
| `hold_start_v` | condition_0:hold_start_v, condition_1:hold_start_v, condition_2:hold_start_v, condition_3:hold_start_v, condition_4:hold_start_v, condition_5:hold_start_v, condition_6:hold_start_v, condition_7:hold_start_v, condition_8:hold_start_v, condition_9:hold_start_v, condition_10:hold_start_v, condition_11:hold_start_v, condition_12:hold_start_v, condition_13:hold_start_v, condition_14:hold_start_v, condition_15:hold_start_v | V | diagnostic | −∞ … +∞ | — |
| `hold_end_v` | condition_0:hold_end_v, condition_1:hold_end_v, condition_2:hold_end_v, condition_3:hold_end_v, condition_4:hold_end_v, condition_5:hold_end_v, condition_6:hold_end_v, condition_7:hold_end_v, condition_8:hold_end_v, condition_9:hold_end_v, condition_10:hold_end_v, condition_11:hold_end_v, condition_12:hold_end_v, condition_13:hold_end_v, condition_14:hold_end_v, condition_15:hold_end_v | V | diagnostic | −∞ … +∞ | — |
| `reacquired_v` | condition_0:reacquired_v, condition_1:reacquired_v, condition_2:reacquired_v, condition_3:reacquired_v, condition_4:reacquired_v, condition_5:reacquired_v, condition_6:reacquired_v, condition_7:reacquired_v, condition_8:reacquired_v, condition_9:reacquired_v, condition_10:reacquired_v, condition_11:reacquired_v, condition_12:reacquired_v, condition_13:reacquired_v, condition_14:reacquired_v, condition_15:reacquired_v | V | diagnostic | −∞ … +∞ | — |
| `pedestal_v` | condition_0:pedestal_v, condition_1:pedestal_v, condition_2:pedestal_v, condition_3:pedestal_v, condition_4:pedestal_v, condition_5:pedestal_v, condition_6:pedestal_v, condition_7:pedestal_v, condition_8:pedestal_v, condition_9:pedestal_v, condition_10:pedestal_v, condition_11:pedestal_v, condition_12:pedestal_v, condition_13:pedestal_v, condition_14:pedestal_v, condition_15:pedestal_v | V | diagnostic | −∞ … +∞ | — |
| `feedthrough_v` | condition_0:feedthrough_v, condition_1:feedthrough_v, condition_2:feedthrough_v, condition_3:feedthrough_v, condition_4:feedthrough_v, condition_5:feedthrough_v, condition_6:feedthrough_v, condition_7:feedthrough_v, condition_8:feedthrough_v, condition_9:feedthrough_v, condition_10:feedthrough_v, condition_11:feedthrough_v, condition_12:feedthrough_v, condition_13:feedthrough_v, condition_14:feedthrough_v, condition_15:feedthrough_v | V | diagnostic | −∞ … +∞ | — |
| `drift_v` | condition_0:drift_v, condition_1:drift_v, condition_2:drift_v, condition_3:drift_v, condition_4:drift_v, condition_5:drift_v, condition_6:drift_v, condition_7:drift_v, condition_8:drift_v, condition_9:drift_v, condition_10:drift_v, condition_11:drift_v, condition_12:drift_v, condition_13:drift_v, condition_14:drift_v, condition_15:drift_v | V | diagnostic | −∞ … +∞ | — |

Area reference: **661.39 um2**. 3 expanded device instances; sum of device/contact envelopes 407.6560 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **5**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Use `/protocol/task.json`, `/protocol/resources.json` and `/protocol/harness.json`
for the frozen inputs, requirements, reviewed IHP primitives and harness
feedback. Work with the supplied KLayout, Magic and ngspice resources.
Write `/workspace/output/final.gds` and explicitly submit through the harness.
Reference GDS, source records and host configuration are not standard inputs.
