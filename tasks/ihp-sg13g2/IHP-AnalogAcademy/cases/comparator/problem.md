# Dynamic Comparator Layout Task

## Objective

Create an IHP SG13G2 layout for the `DIFF_COMPARATOR` dynamic differential
comparator. Preserve the topology, device parameters, explicit well and
substrate connections, and eight-port interface in the authoritative materials.
The submitted GDS must pass the physical checks, fit the functional outline, and
meet the clocked decision requirements after candidate-derived RC extraction.

## Inputs and Interface

In addition to this problem, the solver receives the following declared
materials. The structured constraints
and evaluation plan are also available at runtime through `/protocol/task.json`.

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist for `DIFF_COMPARATOR` |
| [materials/circuit.spice](materials/circuit.spice) | Pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Clock stimulus and public measurement expressions |
| `materials/LICENSE` | Shared collection license, delivered with the circuit |

Use one distinct external conductor for each ordered port. Internal nodes must
not be exposed as ports.

| Port | Function |
|---|---|
| `vdd` | Positive supply |
| `gnd` | Ground and substrate reference |
| `V+`, `V-` | Differential input pair |
| `clk` | Dynamic latch clock |
| `out-`, `out+` | Complementary decision outputs |
| `vbias` | Bias input |

The extraction port order is `vdd gnd V+ V- clk out- out+ vbias`.

## Operating Conditions

The supplied deck evaluates the pre-layout and candidate-derived netlists with
the same model and stimulus definitions.

| Parameter | Setting |
|---|---|
| Process corner | `mos_tt`, `res_typ` |
| Temperature | 27 °C |
| Supply | `VDD = 1.2 V` |
| Input reference and bias | `V- = vbias = 0.6 V` |
| Differential input | `V+ − V- = −5, −3, +3, +5 mV`, tested separately |
| Clock | 100 MHz, 1.2 V swing, 500 ps rise and fall, 5 ns high time |
| Output load | 50 fF on each output |
| Transient analysis | 100 ns duration, 10 ps maximum time step |
| Measurements | Skip the first two cycles and evaluate the next eight cycles |

The testbench excludes power consumed by the external clock, input, and bias
drivers from the reported supply-power measurement.

## Physical Requirements

Submit a readable GDSII file with a nonempty `DIFF_COMPARATOR` top cell. The file
must be at most 10 MiB (10,485,760 bytes) and must contain the complete hierarchy
needed by the target cell.

The evaluator runs the pinned SG13G2 main and additional maximal DRC rules in
deep mode, with density and antenna checks disabled and no waivers. LVS uses the
current `lvs-upstream.json` profile and strict named-port matching against
`materials/circuit.cdl`; port names are matched case-insensitively, while every
declared port must remain on its own conductor with the declared connectivity.

The functional outline is the recursive bounding box of polygons on these
SG13G2 datatype-0 layers, including child cells and the complete routing stack:

`1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 19, 24, 26, 28, 29, 30, 31, 32, 33, 35, 36, 40, 44, 46, 49, 50, 51, 52, 53, 55, 58, 66, 67, 90, 101, 111, 125, 126, 128, 129, 133, 134, 139, 152`.

The maximum width is 45 µm and the maximum height is
45 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

After the physical and geometry gates pass, Magic extracts distributed wire
resistance and layout capacitance from the submitted GDS. Device merging and
resistor-network simplification are disabled. The compact-device extraction
boundary represents MOS bodies at ideal model rails; explicit taps remain part
of physical LVS but are not emitted as extracted tap elements. Substrate sheet
and tap resistance as extracted quantities, body coupling, and noise are outside
the declared scope. The source and post-layout runs use the same nominal
stimuli and models; a finite-source-tap versus ideal-body calibration bounds this
extraction choice.

## Electrical Requirements and Scoring

Every observation below must be finite and satisfy its limit at every one of the
four differential-input settings.

| Metric | Measurement | Unit | Acceptance |
|---|---|---|---|
| Decision delay | From each falling clock edge at 50% level until the correct-polarity output difference reaches 1 V | ns | 0–3 |
| Decision margin | Minimum correct-polarity output difference from 3 to 4 ns after each falling edge | V | ≥1 |
| Average supply power | Average `-V(vdd) × I(VDD)` from 20 to 100 ns | µW | 0–80 |

For positive `V+ − V-`, use `out+ − out-`; for negative `V+ − V-`, use
`out- − out+`. The evaluator checks 32 delay observations, 32 margin
observations, and four power observations independently. A failed or errored
physical prerequisite blocks all dependent extraction and simulation jobs, and
missing or non-finite measurements cannot pass.

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
| `worst_delay` | `response` | 0 | 4 | ns |
| `decision_margin` | `response` | 0 | — | V |
| `supply_power` | `supply` | 0 | 120 | µW |

For a fully accepted candidate, area utility is
`Q = clip((2,025 − area) / (2,025 − 1,700), 0, 1)`,
with area in µm². The fixed full-score area target is
1,700 µm²; the zero-area-utility boundary is 2,025 µm².
Area earns no points until all electrical requirements pass.

The task coefficient is `3`. A batch averages all scheduled independent
attempts per task, then computes `sum(coefficient * task_mean) / sum(coefficient)`.
Coefficients are fixed integers; adding tasks does not change existing ones.

## Tools and Submission

The runtime environment and support resources are declared in
`/protocol/resources.json` and `/protocol/harness.json`; the working directory is
`/workspace`. KLayout performs artifact, DRC, LVS, and geometry checks; Magic
performs RC extraction; ngspice runs the supplied deck with the reviewed SG13G2
models. The evaluator provides the tool and PDK resources named by the case
toolchain.

For pre-layout simulation, use `materials/circuit.spice` as `dut.spice`
beside the supplied testbench and use the per-job values exposed in
`/protocol/task.json`. For the submitted layout, the evaluator supplies the
netlist produced by candidate-derived RC extraction. If the harness declares
`process-feedback.v1`, the optional command is
`python -I /protocol/process_check.py`; the final evaluation remains independent.

Write the result to `/workspace/output/final.gds`, then run
`python -I /protocol/submit.py` and wait for the submission receipt. Solver
netlists, waveforms, and measurements are not accepted as substitutes for the
independent evaluator inputs.
