# Two-Stage CMOS OTA Layout Task

## Objective

Create an IHP SG13G2 layout for the `two_stage_OTA_layout` two-stage CMOS
operational transconductance amplifier. Preserve the MOS and MIM devices,
dimensions, connectivity, well and substrate connections, and six-port
interface in the authoritative materials. The submitted GDS must pass the
physical checks, fit the functional outline, and meet the nominal DC-bias and
AC-response limits after candidate-derived RC extraction.

## Inputs and Interface

In addition to this problem, the solver receives the following declared
materials. The structured constraints
and evaluation plan are also available at runtime through `/protocol/task.json`.

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist for `two_stage_OTA_layout` |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Nominal bias, feedback fixture, AC sweep, and measurements |

Use one external label on each distinct conductor. Internal nodes must not be
declared as external ports.

| Port | Function | Nominal connection |
|---|---|---|
| `v-` | Inverting input | DC feedback from `vout`; AC feedback fixture return |
| `v+` | Non-inverting input | 0.6 V DC and unit AC excitation |
| `vss` | Ground and substrate supply | 0 V |
| `vdd` | Positive supply | 1.2 V |
| `iout` | Bias-current node | Ideal 80 µA sink to ground |
| `vout` | Single-ended output | 500 fF load to ground |

The extraction port order is `v- v+ vss vdd iout vout`.

## Operating Conditions

The pre-layout and candidate-derived simulations use the supplied deck and the
same nominal model and fixture.

| Parameter | Setting |
|---|---|
| Process corner | `mos_tt`, `cap_typ`, `res_typ` |
| Temperature | 27 °C |
| Supply | `VDD = 1.2 V`, `VSS = 0 V` |
| Input DC level | `V+ = 0.6 V` |
| Bias and load | 80 µA sink at `iout`; 500 fF from `vout` to ground |
| Feedback fixture | 4 GH inductor from `vout` to `v-`; 4 GF capacitor from `v-` to ground |
| AC sweep | 100 points/decade from 1 Hz through 10 MHz |
| Numerical conditioning | `rshunt = 1e12`: 1 TΩ from every analog node to ground, identical pre-layout and post-layout |

The feedback fixture closes the DC loop while opening the AC loop for transfer
measurement. Supply power is `-V(vdd) × I(VDD)` at the operating point and
excludes external input and bias-source power.

## Physical Requirements

Submit a readable GDSII file with a nonempty `two_stage_OTA_layout` top cell. The
file must be at most 10 MiB (10,485,760 bytes) and must contain the complete
hierarchy needed by the target cell.

The evaluator runs the pinned SG13G2 main and additional maximal DRC rules in
deep mode, with density and antenna checks disabled and no waivers. LVS uses the
current `lvs-upstream.json` profile and strict named-port matching against
`materials/circuit.cdl`; every declared port must stay on its own conductor with
the declared connectivity and device parameters. Port names are matched
case-insensitively.

The functional outline is the recursive bounding box of polygons on these
SG13G2 datatype-0 layers, including child cells and the complete routing stack:

`1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 19, 24, 26, 28, 29, 30, 31, 32, 33, 35, 36, 40, 44, 46, 49, 50, 51, 52, 53, 55, 58, 66, 67, 90, 101, 111, 125, 126, 128, 129, 133, 134, 139, 152`.

The maximum width is 80 µm and the maximum height is
50 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

After the physical and geometry gates pass, Magic extracts distributed wire
resistance and layout capacitance from the submitted GDS. Device merging and
resistor-network simplification are disabled. The compact-device extraction
boundary represents MOS bodies at ideal model rails; explicit taps remain in the
physical LVS netlist but are not emitted as extracted tap elements. Substrate
sheet and tap resistance as extracted quantities, body coupling, and noise are
outside the declared scope. The finite source tap elements are covered by the
same-condition source calibration and are not treated as additional post-layout
requirements.

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
| `low_frequency_gain` | `response` | dB | maximize / db20 | −∞ … +∞ | — |
| `unity_gain_bandwidth` | `response` | Hz | maximize / ratio | 0 … +∞ | — |
| `phase_margin` | `response` | deg | target / target | 0 … 180 | 180 |
| `supply_power` | `supply` | W | minimize / ratio | 0 … +∞ | 1e-12 |
| `output_bias` | `bias` | V | target / target | 0 … 1.2 | 1.2 |

Area reference: **2936.48 um2**. 24 expanded device instances; sum of device/contact envelopes 1887.1830 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **6**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

Runtime environment and support resources are declared in
`/protocol/resources.json` and `/protocol/harness.json`; the working directory is
`/workspace`. KLayout performs artifact, DRC, LVS, and geometry checks; Magic
performs RC extraction; ngspice runs the supplied deck with the reviewed SG13G2
models. The evaluator provides the tool and PDK resources named by the case
toolchain.

For pre-layout simulation, use `materials/circuit.spice` as `dut.spice` beside
the supplied testbench, with the model paths and settings exposed by the runtime
resource bundle. For the submitted layout, the evaluator supplies the
candidate-derived extracted netlist. If the harness declares
`process-feedback.v1`, the optional command is
`python -I /protocol/process_check.py`; the final evaluation remains independent.

Write the result to `/workspace/output/final.gds`, then run
`python -I /protocol/submit.py` and wait for the submission receipt. Solver
netlists, waveforms, and measurements are not accepted as substitutes for the
independent evaluator inputs.
