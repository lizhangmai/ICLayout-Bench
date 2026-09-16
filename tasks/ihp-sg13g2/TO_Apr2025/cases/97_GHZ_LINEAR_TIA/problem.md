# Linear SiGe HBT Transimpedance Amplifier Layout Task

## Objective

Create a clean SG13G2 layout for the maintained multi-stage linear
transimpedance amplifier in `FMD_QNC_01_LIN_TIA`. Preserve the circuit
connectivity, HBT multiplicities, passive dimensions and six external ports.
The submitted top cell must be `FMD_QNC_01_LIN_TIA` and must pass the physical
checks and nominal post-layout measurements below.

## Inputs and Interface

In addition to this problem, the runtime task supplies the following declared
inputs:

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist and device geometry |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative simulator export |
| [materials/testbench.spice](materials/testbench.spice) | Nominal operating-point, AC and DC-linearity testbench |

The circuit is a three-stage SiGe HBT transimpedance core with active
feedback. Q1 is the input common-emitter device (`Nx=5`), Q2 is the
intermediate emitter follower (`Nx=10`), Q3 is the output common-emitter
device (`Nx=10`), and Q4 is an active emitter-follower feedback device
(`Nx=5`) sensing `RFOUT`. `RFB` returns the Q4 feedback signal to the
Q2/Q3 interstage node. The remaining resistors provide collector loading,
emitter degeneration and input feedback; three `cap_cmim` devices decouple
the independent supply rails. An explicit `ptap1` connects the substrate
body to `VSS`.

The ordered top-level interface is:

| Port | Function |
|---|---|
| `RFIN` | Current input and transimpedance sensing node |
| `RFOUT` | Voltage output and 50 fF load node |
| `VCC1` | First collector-load supply, 1.7 V |
| `VCC2` | Q2/Q4 collector supply, 2.1 V |
| `VCC3` | Q3 collector-load supply, 2.1 V |
| `VSS` | Common return and substrate-tap reference |

LVS and simulation use this order exactly. The netlists specify
the HBT multiplicities, resistor dimensions, 30 × 60 µm `cap_cmim` devices
with `m=2`, and a substrate tap with `A=4 µm²`, `P=8 µm` and finite
simulator equivalent `R=81.6666667 Ω`.

## Operating Conditions

| Parameter | Setting |
|---|---|
| Models and temperature | `hbt_typ`, `res_typ`, `cap_typ`; 26.85 °C |
| Supplies | `VCC1=1.7 V`, `VCC2=2.1 V`, `VCC3=2.1 V` |
| Input DC current | −5 µA, 0 A and +5 µA from `VSS` into `RFIN` |
| AC stimulus | 1 A at the zero-volt `VSENSE` source for normalization |
| Output load | 50 fF from `RFOUT` to `VSS` |
| AC sweep | 1 MHz–100 MHz, 40 points per decade |
| Linearity sweep | 21 DC points from −5 µA to +5 µA in 0.5 µA steps |
| Solver options | `rshunt=1e12` Ω, `reltol=1e-6`, `vntol=1e-8` V, `abstol=1e-12` A |

The AC stimulus is a small-signal normalization, not a large-signal 1 A
input. Transfer is normalized by the current measured at `VSENSE`, and
supply power is calculated from the three independent supply sources.

## Physical Requirements

The candidate GDS must be readable, non-empty and no larger than 32 MiB. It
must pass the pinned SG13G2 main and additional maximal DRC scopes in deep
mode without waivers; density and antenna checks are outside this declared scope. It must
also pass strict named-port LVS against `materials/circuit.cdl`, including
the six ports, device multiplicities, passive geometry and explicit substrate
tap. Artifact, DRC, strict LVS and geometry gates all precede candidate
extraction.

The GDS must include the complete target hierarchy. Port names are matched
case-insensitively; each declared port must remain on its own conductor with
the declared connectivity.

The functional outline is the recursive bounding box of polygons on these
SG13G2 datatype-0 layers, including child cells and the complete routing stack:

`1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 19, 24, 26, 28, 29, 30, 31, 32, 33, 35, 36, 40, 44, 46, 49, 50, 51, 52, 53, 55, 58, 66, 67, 90, 101, 111, 125, 126, 128, 129, 133, 134, 139, 152`.

The maximum width is 720 µm and the maximum height is
620 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

Candidate post-layout extraction combines candidate-derived HBT geometry and
`Nx` with distributed interconnect resistance and capacitance. Drawn emitter
geometry is checked against the candidate; effective ordinary `npn13G2`
dimensions use the simulator model defaults, with the extracted `Nx` retained. The standard
path disables tap extraction at the approved SG13G2 substrate boundary so
the compact-device body can be reconciled to `VSS`; strict LVS still checks
the finite `ptap1` card. Device terminals, multiplicities, resistor geometry,
MIM geometry and top-level connectivity remain candidate-derived. The
finite source tap is retained in pre-layout calibration, and the accepted
model boundary is limited to the nominal transfer, bias, power and linearity
measurements in this task. No other internal-node aliases are permitted; a simulator global ground
alias must not replace the explicit source substrate connection.

## Electrical Requirements and Scoring

The evaluator runs the electrical metrics at each of the three input-current
conditions. Transfer at 1 MHz is the real signed value of
`V(RFOUT)/I(VSENSE)`; transfer at 100 MHz is its magnitude. Linearity is the
maximum absolute deviation from the line joining the two endpoint DC outputs,
divided by the endpoint output span and expressed as a percentage. Every
required observation must be present, finite and within its interval. A failed,
missing or erroring physical or simulation job fails the case; no incomplete
evaluation can establish success.

| Metric | Measurement | Unit | Acceptance |
|---|---|---|---|
| `transimpedance_low` | Signed transfer at 1 MHz | Ω | 300–700 |
| `transimpedance_high` | Magnitude of transfer at 100 MHz | Ω | 300–700 |
| `linearity_error_pct` | Maximum endpoint-line error over the 21-point DC sweep | % | 0–2 |
| `input_bias` | DC voltage at `RFIN` | V | 0.55–1.05 |
| `output_bias` | DC voltage at `RFOUT` | V | 1.4–2.7 |
| `supply_power` | Sum of power from `VCC1`, `VCC2` and `VCC3` | mW | 1–20 |

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
| `transimpedance_low` | `response` | 0 | 1000 | Ω |
| `transimpedance_high` | `response` | 0 | 1000 | Ω |
| `linearity_error_pct` | `response` | 0 | 4 | % |
| `input_bias` | `bias` | 0.3 | 1.3 | V |
| `output_bias` | `bias` | 1.1 | 3 | V |
| `supply_power` | `supply` | 0.5 | 30 | mW |

For a fully accepted candidate, area utility is
`Q = clip((446,400 − area) / (446,400 − 420,000), 0, 1)`,
with area in µm². The fixed full-score area target is
420,000 µm²; the zero-area-utility boundary is 446,400 µm².
Area earns no points until all electrical requirements pass.

The task coefficient is `6`. A batch averages all scheduled independent
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
`FMD_QNC_01_LIN_TIA` and wait for the submission receipt:

```bash
python -I /protocol/submit.py
```

The evaluator uses the submitted snapshot for all physical checks, extraction
and simulations.
