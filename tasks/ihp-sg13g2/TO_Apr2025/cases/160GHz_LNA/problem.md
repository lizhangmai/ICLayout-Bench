# Four-Stage SiGe HBT Voltage Amplifier Layout Task

## Objective

Create a clean SG13G2 layout for the maintained four-stage direct-coupled
common-emitter voltage amplifier in `LNA160_FOUR_STAGE`. Preserve the circuit
connectivity, HBT multiplicities, passive dimensions and five external ports.
The submitted top cell must be `LNA160_FOUR_STAGE` and must pass the physical
checks and nominal post-layout measurements below.

## Inputs and Interface

In addition to this problem, the runtime task supplies the following declared
inputs:

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist and drawn device geometry |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative simulator export |
| [materials/testbench.spice](materials/testbench.spice) | Nominal operating-point and AC testbench |
| [materials/pex_scope.json](materials/pex_scope.json) | Candidate-extraction and substrate-boundary contract |
| `materials/LICENSE` | License notice for the delivered case materials |

The circuit is a four-stage direct-coupled common-emitter amplifier. Four
`npn13G2` devices (`Nx=1`) form the gain chain. Each collector has an `rppd`
load to `VDD`, each emitter has an `rsil` resistor to `VSS`, and the three
interstage collector nodes have `rppd` clamps to `VBIAS`. The emitter
resistors are 4 µm wide with lengths 20.00, 20.01, 20.02 and 20.03 µm in
stage order. An explicit `ptap1` connects the substrate body to `VSS`.

The ordered top-level interface is:

| Port | Function |
|---|---|
| `IN` | Voltage input to the first HBT base |
| `OUT` | Voltage output from the fourth collector and 50 fF load node |
| `VDD` | Common collector-load supply, 1.2 V |
| `VSS` | Common return and substrate-tap reference |
| `VBIAS` | Interstage clamp-bias supply, 0.76 V |

LVS and simulation use this order exactly. The netlists specify
four 0.07 × 0.9 µm drawn `npn13G2` devices, four 2 × 20 µm `rppd` collector
loads, four stage-specific `rsil` emitter resistors, three 1 × 4 µm `rppd`
interstage clamps, and a substrate tap with `A=4 µm²`, `P=8 µm` and finite
simulator equivalent `R=81.6666667 Ω`.

## Operating Conditions

| Parameter | Setting |
|---|---|
| Models and temperature | `hbt_typ`, `res_typ`; 27 °C |
| Supplies and DC bias | `VDD=1.2 V`, `VSS=0 V`, `VIN=0.8 V`, `VBIAS=0.76 V` |
| AC stimulus | 1 V at `VIN` for small-signal gain normalization |
| Output load | 50 fF from `OUT` to `VSS` |
| AC sweep | 1 MHz–1 GHz, 40 points per decade; gain measured at 100 MHz |
| Solver options | `rshunt=1e12` Ω, `reltol=1e-6`, `vntol=1e-8` V, `abstol=1e-12` A |

The AC stimulus is a small-signal normalization, not a large-signal input.
The deck reports the input bias, output bias, `VDD` current, `VBIAS` current
and voltage gain; only the metrics in the table below are acceptance
criteria.

## Physical Requirements

The candidate GDS must be readable, non-empty and no larger than 10 MiB. It
must pass the pinned SG13G2 main and additional maximal DRC scopes in deep
mode without waivers; density and antenna checks are outside this declared scope. It must
also pass strict named-port LVS against `materials/circuit.cdl`, including
the five ports, HBT multiplicities, passive geometry and explicit substrate
tap. Artifact, DRC, LVS and geometry gates all precede candidate extraction.

The GDS must include the complete target hierarchy. Port names are matched
case-insensitively; each declared port must remain on its own conductor with
the declared connectivity.

The functional outline is the recursive bounding box of polygons on these
SG13G2 datatype-0 layers, including child cells and the complete routing stack:

`1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 19, 24, 26, 28, 29, 30, 31, 32, 33, 35, 36, 40, 44, 46, 49, 50, 51, 52, 53, 55, 58, 66, 67, 90, 101, 111, 125, 126, 128, 129, 133, 134, 139, 152`.

The maximum width is 160 µm and the maximum height is
90 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

Candidate post-layout extraction combines candidate-derived HBT geometry and
`Nx` with distributed interconnect resistance and capacitance. Strict LVS
retains the finite `ptap1` card and the drawn HBT geometry. In the simulator
export, the ordinary `npn13G2` model supplies its effective device dimensions
while `Nx=1` and all terminal connections are preserved; the drawn LVS
dimensions are not silently used as behavioral dimensions. The candidate path
reconciles the approved SG13G2 substrate body boundary to `VSS` with tap
extraction disabled. The finite source tap remains in calibration. Details
are in [materials/pex_scope.json](materials/pex_scope.json).

## Electrical Requirements and Scoring

The evaluator runs the three declared metrics at the nominal operating point.
Gain is the voltage ratio `V(OUT)/V(IN)` in dB at 100 MHz, output bias is the
DC voltage at `OUT`, and supply current is the current supplied by `VDD`.
Every required observation must be present, finite and within its interval. A failed,
missing or erroring physical or simulation job fails the case; no incomplete
evaluation can establish success.

| Metric | Measurement | Unit | Acceptance |
|---|---|---|---|
| `gain_db` | Voltage gain at 100 MHz | dB | 10–60 |
| `output_bias` | DC voltage at `OUT` | V | 0.20–1.10 |
| `supply_current` | Current supplied by `VDD` | µA | 10–3000 |

The input bias and `VBIAS` current are diagnostics, without acceptance limits.

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
| `gain_db` | `response` | 0 | 80 | dB |
| `output_bias` | `bias` | 0 | 1.2 | V |
| `supply_current` | `supply` | 0 | 5000 | µA |

For a fully accepted candidate, area utility is
`Q = clip((14,400 − area) / (14,400 − 13,000), 0, 1)`,
with area in µm². The fixed full-score area target is
13,000 µm²; the zero-area-utility boundary is 14,400 µm².
Area earns no points until all electrical requirements pass.

The task coefficient is `3`. A batch averages all scheduled independent
attempts per task, then computes `sum(coefficient * task_mean) / sum(coefficient)`.
Coefficients are fixed integers; adding tasks does not change existing ones.

## Tools and Submission

Discover the supplied task, resources, harness and constraints from
`/protocol/task.json`, `/protocol/resources.json` and
`/protocol/harness.json`. Use the tool and PDK resources selected by the
runtime environment. If the harness declares `process-feedback.v1`, request
an optional frozen process check with `python -I /protocol/process_check.py`;
the final evaluation remains independent.

Write the answer to `/workspace/output/final.gds` as a GDS file with top cell
`LNA160_FOUR_STAGE` and wait for the submission receipt:

```bash
python -I /protocol/submit.py
```

The evaluator uses the submitted snapshot for all physical checks, extraction
and simulations.
