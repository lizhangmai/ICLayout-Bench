# PMOS Differential Input Pair Layout Task

## Objective

Create an IHP SG13G2 layout for the `input_common_centroid` matched PMOS
differential input pair. Preserve the device topology, dimensions, dummy
devices, explicit well and substrate connections, and six-port interface in the
authoritative materials. The submitted GDS must pass the physical checks, fit
the functional outline, and meet the nominal differential-response limits after
candidate-derived RC extraction.

## Inputs and Interface

In addition to this problem, the solver receives the following declared
materials. The structured constraints
and evaluation plan are also available at runtime through `/protocol/task.json`.

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist for `input_common_centroid` |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Bias, load, AC sweep, and public measurement expressions |

Use one external label on each distinct conductor. Internal nodes must not be
declared as external ports.

| Port | Function | Nominal connection |
|---|---|---|
| `v-` | Inverting PMOS gate | Differential input |
| `v+` | Non-inverting PMOS gate | Differential input |
| `vdd` | PMOS well and dummy-device supply | 1.2 V supply |
| `dn3`, `dn4` | Differential drain outputs | 50 kΩ loads to ground |
| `tail` | Shared source and dummy-drain node | 20 µA source current from `vdd` |

The extraction port order is `v- v+ vdd dn3 dn4 tail`.

## Operating Conditions

The pre-layout and candidate-derived simulations use the supplied deck and the
same nominal model and parameter values.

| Parameter | Setting |
|---|---|
| Process corner | `mos_tt`, `res_typ` |
| Temperature | 27 °C |
| Supply | `VDD = 1.2 V` |
| Bias | 20 µA current source from `vdd` to `tail` |
| Input DC level | `v- = v+ = 0.5 V` common mode |
| Input AC stimulus | Equal and opposite small-signal inputs, −0.5 V and +0.5 V |
| Drain loads | 50 kΩ from each of `dn3` and `dn4` to ground |
| AC sweep | 40 points/decade from 1 Hz through 1 GHz |
| Numerical conditioning | `rshunt = 1e12`: 1 TΩ from every analog node to ground, identical pre-layout and post-layout |

Supply power is `-V(vdd) × I(VDD)` at the DC operating point. The evaluator
checks the 1 MHz and 100 MHz differential gain observations from the sweep.

## Physical Requirements

Submit a readable GDSII file with a nonempty `input_common_centroid` top cell.
The file must be at most 10 MiB (10,485,760 bytes) and must contain the complete
hierarchy needed by the target cell.

The evaluator runs the pinned SG13G2 main and additional maximal DRC rules in
deep mode, with density and antenna checks disabled and no waivers. LVS uses the
current `lvs-upstream.json` profile and strict named-port matching against
`materials/circuit.cdl`; every declared port must stay on its own conductor
with the declared connectivity and device parameters. Port names are matched
case-insensitively.

The functional outline is the recursive bounding box of polygons on these
SG13G2 datatype-0 layers, including child cells and the complete routing stack:

`1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 19, 24, 26, 28, 29, 30, 31, 32, 33, 35, 36, 40, 44, 46, 49, 50, 51, 52, 53, 55, 58, 66, 67, 90, 101, 111, 125, 126, 128, 129, 133, 134, 139, 152`.

The maximum width is 45 µm and the maximum height is
40 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

After the physical and geometry gates pass, Magic extracts distributed wire
resistance and layout capacitance from the submitted GDS. Device merging and
resistor-network simplification are disabled. The compact-device extraction
boundary represents MOS bodies at ideal model rails; the explicit tap is checked
by physical LVS but is not emitted as an extracted tap element. Well/substrate
sheet resistance, tap resistance as an extracted quantity, body coupling, and
noise are outside the declared scope. The finite source tap is used only in source calibration.

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
| `differential_gain` | `response` | V/V | maximize / ratio | 0 … +∞ | — |
| `differential_gain_high` | `response` | V/V | maximize / ratio | 0 … +∞ | — |
| `tail_voltage` | `bias` | V | target / target | −∞ … +∞ | 1.2 |
| `common_drain` | `bias` | V | target / target | 0 … 1.2 | 1.2 |
| `drain_balance` | `bias` | V | target / target | −∞ … +∞ | 1.2 |
| `supply_power` | `supply` | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **1236.14 um2**. 13 expanded device instances; sum of device/contact envelopes 778.4891 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **3**; it is independent of
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
the supplied testbench. The evaluator generates `parameters.spice` from the
per-job values in `/protocol/task.json` and supplies the model paths and settings
through the runtime resource bundle. For the submitted layout, the evaluator
supplies the candidate-derived extracted netlist. If the harness declares
`process-feedback.v1`, the optional command is
`python -I /protocol/process_check.py`; the final evaluation remains independent.

Write the result to `/workspace/output/final.gds`, then run
`python -I /protocol/submit.py` and wait for the submission receipt. Solver
netlists, waveforms, and measurements are not accepted as substitutes for the
independent evaluator inputs.
