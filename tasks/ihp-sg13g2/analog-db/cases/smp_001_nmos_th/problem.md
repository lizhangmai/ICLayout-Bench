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

Point values below use linear interpolation of saved transient samples.
Extrema use simulator samples in the stated windows. No smoothing, offset
correction or clock-edge blanking modifies the reported storage voltage.
Let T be SRC at 180 ns; it equals the commanded sampled level. Define:

- `track_v`: VOUT at 180 ns. `track_error_v`: maximum |VOUT−T| over 80–190 ns,
  requiring sustained acquisition after the finite input transition.
- `held_v`: VOUT at 220 ns. `pedestal_v=held_v−track_v`, with scored
  `pedestal_abs_v=abs(pedestal_v)`. It includes actual clock turn-off injection.
- `before_input_v` and `after_input_v`: VOUT at 390 and 450 ns.
  `feedthrough_v=after_input_v−before_input_v` is diagnostic;
  `feedthrough_peak_v` is maximum |VOUT−before_input_v| over 400–450 ns,
  including the input transition while the switch is off.
- `hold_start_v` and `hold_end_v`: VOUT at 1 and 11 us.
  `drift_v=hold_end_v−hold_start_v` is signed drift over a quiet 10 us interval;
  `hold_drift_v=abs(drift_v)` is scored. The input is fixed during this interval.
- `hold_error_v`: maximum |VOUT−T| over 220 ns–11 us, including pedestal,
  off-state input coupling and retention error.
- `reacquired_v`: VOUT at 11.65 us. `reacquire_error_v`: maximum |VOUT−T|
  over 11.48–11.69 us, after input restoration and switch closure.
- `clock_energy_j`: integral of `max(−V(CLK)*I(VCLK),0)` over 0–11.7 us.
  This is positive supplied clock energy for the finite high/low/high sequence,
  excluding initial DC charging and without crediting returned energy. It is
  not periodic average power or the full energy of a physical clock driver.

The named point voltages, signed differences and T (`target`) are diagnostics.
Every scored bound must hold independently at all sixteen conditions.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `track_error_v` | V | 0–0.002 | 0 / 0.1 | response |
| `pedestal_abs_v` | V | 0–0.009 | 0 / 0.05 | response |
| `feedthrough_peak_v` | V | 0–0.00075 | 0 / 0.01 | response |
| `hold_drift_v` | V | 0–0.013 | 0 / 0.1 | response |
| `hold_error_v` | V | 0–0.022 | 0 / 0.15 | response |
| `reacquire_error_v` | V | 0–0.0001 | 0 / 0.02 | response |
| `clock_energy_j` | J | 0–2e-14 | 0 / 1e-13 | supply |

Coefficient **5** represents a complete compact loaded sampling block whose
stored-charge behavior must survive acquisition, isolation and reacquisition.
Unified `layout-v1` scoring is `G × (60E + 20H + 20HQ)`: G requires physical
validity and complete measurements, E averages worst attainment in response
and supply, and H requires every electrical bound. Each attainment falls
linearly between its acceptance edge and zero-score boundary. Fixed area
anchors are 1400/5600 um²: `Q=clip((5600−area)/4200,0,1)`. Physical rejection
scores zero; incomplete measurements cannot establish success or an invented
score. An aggregate cannot conceal a failed condition.

This contract establishes model-based retention for the specified 10 us quiet
hold and finite sequence. Higher sampled voltages and longer holds are not
qualified. It does not establish precision ADC resolution, capacitor dielectric
leakage, measured-silicon retention, noise, aperture jitter, distortion, process
corners, statistical mismatch, arbitrary source impedance or clock slopes.

## Tools and Submission

Use `/protocol/task.json`, `/protocol/resources.json` and `/protocol/harness.json`
for the frozen inputs, requirements, reviewed IHP primitives and harness
feedback. Work with the supplied KLayout, Magic and ngspice resources.
Write `/workspace/output/final.gds` and explicitly submit through the harness.
Reference GDS, source records and host configuration are not standard inputs.
