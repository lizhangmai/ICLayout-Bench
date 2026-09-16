# Two-Stage Fully Differential OTA with RC Common-Mode Feedback Layout Task

## Objective

Implement `amp_023_fer_fd2s`: an NMOS-input folded first stage, two NMOS
common-source output stages, dual series R/C compensation and transistor
common-mode feedback sensing both outputs through physical R/C arms. Preserve
all device groups and validate both differential and common-mode behavior in
the specified unity differential feedback connection.

## Inputs and Interface

- `materials/circuit.cdl`: authoritative physical circuit for native LVS.
- `materials/circuit.spice`: equivalent process-model simulator representation.
- `materials/testbench.spice`: declared stimuli, differential feedback and measurements.

Ordered ports are `vinp vinn voutp voutn vdd vss ibias vcmr`.
VINP/VINN are differential inputs; VOUTP/VOUTN are differential outputs;
VDD/VSS are supply/return; IBIAS receives 20 uA from VDD; VCMR receives the
common-mode reference relative to VSS. The bias mirrors and common-mode
controller stay in the DUT. Do not replace the internal controller with an
ideal servo or omit physical passive devices.

Retain all 28 MOS groups' fixed W/L/m (50 individual transistors), models and
connectivity. Equivalent parallel fingering/native merging is allowed if all
checks pass. NMOS and resistor bodies connect through the explicit substrate
tap to VSS; PMOS bodies connect through the well tap to VDD. Keep supplies,
body connections and ordered ports faithful to the circuit.

Each output compensation path has a W=1 um, L=0.96 um `rhigh` (nominally
1.52 kohm at 27 C) between `o1a`/`o1b` and `za`/`zb`, followed by two parallel
25.85 × 25.85 um `cap_cmim` units to the corresponding output (2.01294 pF).
Each output-to-`vsen` sensing arm contains eight series W=1 um, L=18 um
`rhigh` segments (nominally 205.28 kohm total), in parallel with a
9.95 × 9.95 um MIM (150.096 fF). Resistors use m=1, b=0. These internal
devices are separate from external output loads; they must be physically
implemented with the same terminal mapping. Internal nodes are not bias ports.

## Operating Conditions

Use typical MOS, capacitor and resistor models, 27 C, 1.2 V supply, 20 uA
from VDD to IBIAS, and input common mode 0.5 V. Each output has an external
1, 5 or 10 pF load. For each load, evaluate paired positive and negative
stimuli: `step_v` is +0.1 or −0.1 V and `kick_a` is respectively +100 or
−100 uA. All six conditions must pass.

Define `d=VOUTP−VOUTN` and `c=(VOUTP+VOUTN)/2`. The external differential
feedback apparatus drives `VINP=0.5+(VSIG−d)/2` and
`VINN=0.5−(VSIG−d)/2`, through zero-volt series probes. It holds input
common mode and closes differential unity feedback. It does not force output
common mode: the actual DUT controller, its two R/C sense arms and actual
output stages close that loop.

At DC, VSIG=0 and VCMR=0.75 V. Differential AC uses opposite +0.5/−0.5 V
series probe excitations and sweeps 1 Hz–1 GHz at 150 points/decade. Measure
`A=d/(VINP−VINN)`; its sign is retained. Low-frequency gain is dB magnitude
at 1 Hz; unity frequency is the first falling 0 dB crossing; phase margin is
180 degrees plus continuous phase there, without subtracting an arbitrary
phase offset. A missing crossing is an error. This voltage-injection return
ratio is scoped to the high-impedance input and declared unity feedback.

Common-mode AC sets both series probe AC magnitudes to zero and VCMR AC=1 V,
keeping differential feedback closed. Sweep 1 Hz–1 GHz at 100 points/decade.
Measure `abs(c/VCMR)` at 1 Hz and its maximum over the complete sweep.
This is closed-loop common-mode tracking/peaking, not an internal common-mode
loop phase-margin measurement.

The transient sequence runs 0–8 us using Gear order 2 with maximum step 1 ns.
Use `rshunt=1e12`, `reltol=1e-5`, `abstol=1e-13`, `vntol=1e-8`.
VSIG rises from zero to `step_v` during 1–1.005 us, holds for 4 us, and
returns during 5.005–5.010 us. VCMR rises 0.75→0.8 V during 3–3.005 us,
holds for 1 us, and returns during 4.005–4.010 us. Thus reference tracking
is tested while a nonzero differential output is present. Equal current
sources inject `kick_a` into both outputs during a 6–6.060 us pulse:
5 ns rise, 50 ns hold and 5 ns fall. Negative `kick_a` withdraws current.
The pulse periods are 20 us; only this finite 8 us sequence is measured.
No startup initialization is imposed; transient starts from the solved DC point.

## Physical Requirements

Submit GDSII top cell `amp_023_fer_fd2s`, at most 10 MiB. Pass native IHP
main/maximal DRC without waivers (standalone scope, density/antenna disabled),
strict named-port LVS with physical taps, and a 1200 × 400 um functional
outline. Include all device, contact and routing drawing layers enumerated by
the runtime outline constraint. Pin-purpose and annotation layers do not
contribute to bounding-box area and cannot conceal functional geometry.

Post-layout measurements must consume the candidate-derived Magic RC netlist,
including physical passives, transistor junction geometry and interconnect.
The extraction configuration subdivides Magic's initial grid by two before
GDS import and imports its isolated copy with `gds_readonly=false`; the submitted
GDS remains immutable. No extraction error is waived. Device parameters,
geometry and port connectivity must survive extraction. Magic idealizes
well/substrate taps; source simulation retains their finite process models.
Distributed substrate resistance/noise and fabrication signoff are outside scope.

## Electrical Requirements and Scoring

`output_cm_v`, `output_dm_v`, `bias_v` and `power_w` measure DC c, d, IBIAS
voltage and positive VDD-supplied power. The VDD measurement includes the
external 20 uA source's draw from VDD, but not bias-generator overhead.
`mean_power_w` averages `−VDD×I(VDD)` over 0–8 us. External feedback,
reference-drive and disturbance-source energy are outside this VDD-only metric;
no recovered energy is credited. The nominal supply remains positive-current
supplying during this sequence.

The error metrics are maxima of absolute error over the following sustained
windows, including endpoint interpolation:

| Metric | Quantity | Window (us) |
| --- | --- | --- |
| `dm_up_error_v` | abs(d−VSIG) after the signed step | 1.5–1.95 |
| `dm_down_error_v` | abs(d−VSIG) after return to zero | 5.5–5.95 |
| `dm_cm_error_v` | abs(d−VSIG) during the common-mode reference step | 3.5–3.95 |
| `cm_dm_error_v` | abs(c−VCMR) during the differential step | 1.5–1.95 |
| `cm_up_error_v` | abs(c−VCMR) after the reference rise | 3.5–3.95 |
| `cm_down_error_v` | abs(c−VCMR) after reference return, including differential return | 4.5–5.9 |
| `cm_kick_error_v` | abs(c−VCMR) after the simultaneous output-current pulse | 6.5–7.9 |
| `cm_kick_peak_v` | abs(c−VCMR) throughout disturbance and early recovery | 6–6.5 |

`dm_peak_v` is maximum abs(d) over 1–5 us. `dm_high_v` (mean d over
1.8–1.95 us) and `cm_high_v` (mean c over 3.8–3.95 us) are diagnostic
observations without separate score bounds. All AC definitions appear above.
Every scored bound below applies independently at every load and polarity.

| Metric | Unit | Acceptance | Lower / upper zero-score boundaries | Dimension |
| --- | --- | --- | --- | --- |
| `output_cm_v` | V | 0.74–0.765 | 0.65 / 0.85 | bias |
| `output_dm_v` | V | -0.0005–0.0005 | -0.01 / 0.01 | bias |
| `bias_v` | V | 0.37–0.42 | 0.25 / 0.55 | bias |
| `power_w` | W | 0–0.00065 | 0 / 0.0013 | supply |
| `dm_gain_db` | dB | ≥ 55 | 40 / — | response |
| `unity_hz` | Hz | ≥ 1.8e+07 | 0 / — | response |
| `phase_margin_deg` | deg | 60–150 | 0 / 180 | response |
| `cm_gain_vv` | V/V | 0.95–1.15 | 0.5 / 1.5 | response |
| `cm_peak_vv` | V/V | 0.95–1.8 | 0.5 / 2.5 | response |
| `dm_up_error_v` | V | 0–0.0005 | 0 / 0.01 | response |
| `dm_down_error_v` | V | 0–0.0005 | 0 / 0.01 | response |
| `cm_up_error_v` | V | 0–0.01 | 0 / 0.05 | response |
| `cm_down_error_v` | V | 0–0.0075 | 0 / 0.05 | response |
| `cm_kick_error_v` | V | 0–0.0075 | 0 / 0.05 | response |
| `cm_kick_peak_v` | V | 0–0.09 | 0 / 0.2 | response |
| `dm_peak_v` | V | 0.095–0.12 | 0 / 0.2 | response |
| `mean_power_w` | W | 0–0.00065 | 0 / 0.0013 | supply |
| `dm_cm_error_v` | V | 0–0.0005 | 0 / 0.01 | response |
| `cm_dm_error_v` | V | 0–0.0075 | 0 / 0.05 | response |

Coefficient **9** represents the coupled differential compensation and actual
common-mode feedback requirements. Unified `layout-v1` scoring is
`G × (60E + 20H + 20HQ)`. G requires physical validity and complete valid
measurements; E averages worst attainment in response, bias and supply; H
requires every electrical bound. Attainment declines linearly from each
acceptance edge to its declared zero boundary. Area utility is
`Q=clip((380000−area)/285000,0,1)`, with fixed absolute functional-area anchors
95000/380000 um². A completed physical rejection scores zero; incomplete
measurement cannot establish success or receive an invented score. Aggregation
cannot conceal a failed condition. Qualification is limited to the stated
nominal bias, feedback, loads and sequence, not PVT, mismatch, zero-state
startup, rail-to-rail operation, noise/distortion or arbitrary-loop stability.

## Tools and Submission

Discover task inputs, frozen requirements, reviewed resources and harness
feedback through `/protocol/task.json`, `/protocol/resources.json` and
`/protocol/harness.json`. Use the supplied IHP primitives and KLayout, Magic
and ngspice. Write `/workspace/output/final.gds` and explicitly submit using
the harness protocol. Reference GDS, source records and host configuration
remain outside standard solver inputs.
