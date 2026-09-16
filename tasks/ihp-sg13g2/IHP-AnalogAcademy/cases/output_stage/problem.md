# CMOS OTA Output Stage Layout Task

## Objective

Create an IHP SG13G2 layout for the `output_stage` output stage of a two-stage
CMOS operational transconductance amplifier. Preserve the device topology,
dimensions, compensation capacitor, explicit well and substrate connections,
and five-port interface in the authoritative materials. The submitted GDS must
pass the physical checks, fit the functional outline, and meet the nominal
output-response limits after candidate-derived RC extraction.

## Inputs and Interface

In addition to this problem, the solver receives the following declared
materials. The structured constraints
and evaluation plan are also available at runtime through `/protocol/task.json`.

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist for `output_stage` |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Bias, load, AC sweep, and public measurement expressions |

Use one external label on each distinct conductor. Internal nodes must not be
declared as external ports.

| Port | Function | Nominal connection |
|---|---|---|
| `vdd` | PMOS supply and n-well reference | 1.2 V supply |
| `iout` | Bias replica/control node | 20 µA current sink to ground |
| `vout` | Single-ended output | 100 kΩ and 500 fF loads to ground |
| `vss` | NMOS supply and substrate reference | Ground |
| `dn4` | NMOS gate and compensation-capacitor node | 0.33 V DC with 1 V AC |

The extraction port order is `vdd iout vout vss dn4`.

The circuit contains the PMOS output current source `MM5`, diode-connected bias
replica `MM9`, long-channel NMOS pull-down `MM6`, MIM compensation capacitor
`CC2`, and explicit tap devices `RR4` and `RR5`.

## Operating Conditions

The pre-layout and candidate-derived simulations use the supplied deck and the
same nominal model and parameter values.

| Parameter | Setting |
|---|---|
| Process corner | `mos_tt`, `cap_typ`, `res_typ` |
| Temperature | 27 °C |
| Supply | `VDD = 1.2 V`, `VSS = 0 V` |
| Bias | 20 µA current sink at `iout` |
| Input stimulus | `dn4 = 0.33 V` DC with 1 V AC small signal |
| Output load | 100 kΩ resistor and 500 fF capacitor to ground |
| AC sweep | 40 points/decade from 1 Hz through 1 GHz |
| Numerical conditioning | `rshunt = 1e12`: 1 TΩ from every analog node to ground, identical pre-layout and post-layout |

Supply power is `-V(vdd) × I(VDD)` at the DC operating point.

## Physical Requirements

Submit a readable GDSII file with a nonempty `output_stage` top cell. The file
must be at most 10 MiB (10,485,760 bytes) and must contain the complete
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

The maximum width is 55 µm and the maximum height is
45 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

After the physical and geometry gates pass, Magic extracts distributed wire
resistance and layout capacitance from the submitted GDS. Device merging and
resistor-network simplification are disabled. The compact-device extraction
boundary represents MOS bodies at ideal model rails; explicit taps remain in the
physical LVS netlist but are not emitted as extracted tap elements. Substrate
sheet and tap resistance as extracted quantities, body coupling, and noise are
outside the declared scope. The finite source taps are used only in source calibration.

## Electrical Requirements and Scoring

All declared measurements must be finite and satisfy their limits.

| Metric | Measurement | Unit | Acceptance |
|---|---|---|---|
| Output gain at 1 MHz | Magnitude of `-V(vout) / V(dn4)` at 1 MHz | V/V | ≥8 |
| Output gain at 100 MHz | Magnitude of the same transfer at 100 MHz | V/V | ≥0.7 |
| Output bias | `V(vout)` at the DC operating point | V | 0.60–0.70 |
| Supply power | `-V(vdd) × I(VDD)` at the DC operating point | µW | 0–60 |

The evaluator runs artifact validation, DRC, strict LVS, geometry,
candidate-derived RC extraction, and post-layout simulation in dependency order.
A failed or errored prerequisite blocks dependent jobs; a completed violation,
missing or non-finite measurement, model error, or timeout cannot establish
success.

The single task score uses `layout-v1`:

```text
S = G * (60 * E + 20 * H + 20 * H * Q)
```

`G` requires valid artifact, DRC, strict LVS, hard geometry, candidate PEX and
complete simulation measurements. A completed physical rejection scores 0;
an evaluator error that prevents grading leaves the score pending (`null`).
`H` is 1 only when every electrical requirement passes. `E` is the mean of the
applicable `response`, `bias` and `supply` dimensions: take the worst observation
of each metric, then the worst metric in each dimension. Successful candidates
score 80–100; physically valid candidates with an electrical violation score
below 60. There are no separate points for check jobs or individual cycles.

An observation earns attainment 1 throughout its inclusive acceptance range.
Outside that range it declines linearly to the corresponding zero boundary in
the table below, and remains 0 beyond it. A zero boundary equal to its acceptance
boundary declares an immediate drop to 0 outside that side. A dash means that
side has no bound. These are explicit grading anchors, not additional acceptance
limits or alternate stimulus conditions.

| Metric ID | Dimension | Lower-Side Zero | Upper-Side Zero | Unit |
|---|---|---:|---:|---|
| `output_gain` | `response` | 0 | — | V/V |
| `output_gain_high` | `response` | 0 | — | V/V |
| `output_bias` | `bias` | 0.5 | 0.8 | V |
| `supply_power` | `supply` | 0 | 100 | µW |

For a fully accepted candidate, area utility is
`Q = clip((2,475 − area) / (2,475 − 1,750), 0, 1)`,
with area in µm². The fixed full-score area target is
1,750 µm²; the zero-area-utility boundary is 2,475 µm².
Area earns no points until all electrical requirements pass.

The task coefficient is `4`. A batch averages all scheduled independent
attempts per task, then computes `sum(coefficient * task_mean) / sum(coefficient)`.
Coefficients are fixed integers; adding tasks does not change existing ones.

## Tools and Submission

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
