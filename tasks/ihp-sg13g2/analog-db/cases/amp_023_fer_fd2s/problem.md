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
| `output_cm_v` | condition_0:output_cm_v, condition_1:output_cm_v, condition_2:output_cm_v, condition_3:output_cm_v, condition_4:output_cm_v, condition_5:output_cm_v | V | target / target | 0 … 1.2 | 1.2 |
| `output_dm_v` | condition_0:output_dm_v, condition_1:output_dm_v, condition_2:output_dm_v, condition_3:output_dm_v, condition_4:output_dm_v, condition_5:output_dm_v | V | target / target | −∞ … +∞ | 1.2 |
| `bias_v` | condition_0:bias_v, condition_1:bias_v, condition_2:bias_v, condition_3:bias_v, condition_4:bias_v, condition_5:bias_v | V | target / target | 0 … 1.2 | 1.2 |
| `power_w` | condition_0:power_w, condition_1:power_w, condition_2:power_w, condition_3:power_w, condition_4:power_w, condition_5:power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `dm_gain_db` | condition_0:dm_gain_db, condition_1:dm_gain_db, condition_2:dm_gain_db, condition_3:dm_gain_db, condition_4:dm_gain_db, condition_5:dm_gain_db | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_hz` | condition_0:unity_hz, condition_1:unity_hz, condition_2:unity_hz, condition_3:unity_hz, condition_4:unity_hz, condition_5:unity_hz | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin_deg` | condition_0:phase_margin_deg, condition_1:phase_margin_deg, condition_2:phase_margin_deg, condition_3:phase_margin_deg, condition_4:phase_margin_deg, condition_5:phase_margin_deg | deg | target / target | 0 … 180 | 180 |
| `cm_gain_vv` | condition_0:cm_gain_vv, condition_1:cm_gain_vv, condition_2:cm_gain_vv, condition_3:cm_gain_vv, condition_4:cm_gain_vv, condition_5:cm_gain_vv | V/V | target / target | −∞ … +∞ | 1.0 |
| `cm_peak_vv` | condition_0:cm_peak_vv, condition_1:cm_peak_vv, condition_2:cm_peak_vv, condition_3:cm_peak_vv, condition_4:cm_peak_vv, condition_5:cm_peak_vv | V/V | target / target | −∞ … +∞ | 1.0 |
| `dm_up_error_v` | condition_0:dm_up_error_v, condition_1:dm_up_error_v, condition_2:dm_up_error_v, condition_3:dm_up_error_v, condition_4:dm_up_error_v, condition_5:dm_up_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `dm_down_error_v` | condition_0:dm_down_error_v, condition_1:dm_down_error_v, condition_2:dm_down_error_v, condition_3:dm_down_error_v, condition_4:dm_down_error_v, condition_5:dm_down_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `cm_up_error_v` | condition_0:cm_up_error_v, condition_1:cm_up_error_v, condition_2:cm_up_error_v, condition_3:cm_up_error_v, condition_4:cm_up_error_v, condition_5:cm_up_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `cm_down_error_v` | condition_0:cm_down_error_v, condition_1:cm_down_error_v, condition_2:cm_down_error_v, condition_3:cm_down_error_v, condition_4:cm_down_error_v, condition_5:cm_down_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `cm_kick_error_v` | condition_0:cm_kick_error_v, condition_1:cm_kick_error_v, condition_2:cm_kick_error_v, condition_3:cm_kick_error_v, condition_4:cm_kick_error_v, condition_5:cm_kick_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `cm_kick_peak_v` | condition_0:cm_kick_peak_v, condition_1:cm_kick_peak_v, condition_2:cm_kick_peak_v, condition_3:cm_kick_peak_v, condition_4:cm_kick_peak_v, condition_5:cm_kick_peak_v | V | target / target | 0 … 1.2 | 1.2 |
| `dm_peak_v` | condition_0:dm_peak_v, condition_1:dm_peak_v, condition_2:dm_peak_v, condition_3:dm_peak_v, condition_4:dm_peak_v, condition_5:dm_peak_v | V | target / target | 0 … 1.2 | 1.2 |
| `mean_power_w` | condition_0:mean_power_w, condition_1:mean_power_w, condition_2:mean_power_w, condition_3:mean_power_w, condition_4:mean_power_w, condition_5:mean_power_w | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `dm_cm_error_v` | condition_0:dm_cm_error_v, condition_1:dm_cm_error_v, condition_2:dm_cm_error_v, condition_3:dm_cm_error_v, condition_4:dm_cm_error_v, condition_5:dm_cm_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `cm_dm_error_v` | condition_0:cm_dm_error_v, condition_1:cm_dm_error_v, condition_2:cm_dm_error_v, condition_3:cm_dm_error_v, condition_4:cm_dm_error_v, condition_5:cm_dm_error_v | V | minimize / ratio | 0 … +∞ | 1e-06 |
| `dm_high_v` | condition_0:dm_high_v, condition_1:dm_high_v, condition_2:dm_high_v, condition_3:dm_high_v, condition_4:dm_high_v, condition_5:dm_high_v | V | diagnostic | −∞ … +∞ | — |
| `cm_high_v` | condition_0:cm_high_v, condition_1:cm_high_v, condition_2:cm_high_v, condition_3:cm_high_v, condition_4:cm_high_v, condition_5:cm_high_v | V | diagnostic | −∞ … +∞ | — |

Area reference: **8435.0 um2**. 76 expanded device instances; sum of device/contact envelopes 5503.6687 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **9**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Discover task inputs, frozen requirements, reviewed resources and harness
feedback through `/protocol/task.json`, `/protocol/resources.json` and
`/protocol/harness.json`. Use the supplied IHP primitives and KLayout, Magic
and ngspice. Write `/workspace/output/final.gds` and explicitly submit using
the harness protocol. Reference GDS, source records and host configuration
remain outside standard solver inputs.
