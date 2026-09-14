# Two-Stage SiGe HBT Transimpedance Amplifier Layout Task

## Objective

Create a clean SG13G2 layout for the maintained two-stage transimpedance
amplifier in `FMD_QNC_03a_TIA_1`. Preserve the circuit connectivity, HBT
multiplicities, passive dimensions and five external ports. The submitted top
cell must be `FMD_QNC_03a_TIA_1` and must pass the physical checks and nominal
post-layout measurements below.

## Inputs and Interface

In addition to this problem, the runtime task supplies the following declared
inputs:

| Input | Purpose |
|---|---|
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative LVS netlist and device geometry |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative simulator export |
| [materials/testbench.spice](materials/testbench.spice) | Nominal operating-point and AC testbench |
| `materials/LICENSE` | License notice for the delivered case materials |

The circuit is a two-stage SiGe HBT transimpedance core. Q1 is the first
common-emitter stage (`Nx=5`) and drives Q2, the second common-emitter stage
(`Nx=4`). `RC1` and `RC2` are independent collector loads, `RRF` provides
first-stage resistive feedback from `DN1` to `INPUT`, and `C1` and `C2`
decouple the two supply rails. The explicit `ptap1` has both terminals on
`VEE`, so it is a same-net substrate tie.

The ordered top-level interface is:

| Port | Function |
|---|---|
| `INPUT` | Current input and transimpedance sensing node |
| `OUTPUT` | Voltage output and 50 fF load node |
| `VCC2V` | Q1 collector-load supply, 2 V |
| `VCC2V1` | Q2 collector-load supply, 2 V |
| `VEE` | Common return and substrate reference |

LVS and simulation use this order exactly. The netlists specify
`npn13G2` devices with `Nx=5` and `Nx=4`, `rppd` resistors with dimensions
15 × 4 µm, 11.5 × 2 µm and 29 × 6.3 µm, two 30 × 30 µm `cap_cmim`
devices with `m=1`, and the tap geometry `A=3.6504 µm²`, `P=18.72 µm`.

## Operating Conditions

| Parameter | Setting |
|---|---|
| Models and temperature | `hbt_typ`, `res_typ`, `cap_typ`; 26.85 °C |
| Supplies | `VCC2V=2 V`, `VCC2V1=2 V`, `VEE=0 V` |
| Input DC current | −100 µA, 0 A and +100 µA from the return into `INPUT` |
| AC stimulus | 1 A at the zero-volt `VSENSE` source for normalization |
| Output load | 50 fF from `OUTPUT` to the simulator return |
| External loads | No external resistive input or output load |
| AC sweep | 1 MHz–100 MHz, 40 points per decade |
| Solver options | `rshunt=1e12` Ω, `reltol=1e-6`, `vntol=1e-8` V, `abstol=1e-12` A |

The AC stimulus is a small-signal normalization, not a large-signal 1 A
input. The shunt anchors DC-floating capacitive islands while retaining their
AC coupling. Transfer is normalized by the current measured at `VSENSE`, and
supply power is calculated from the two independent supply sources.

## Physical Requirements

The candidate GDS must be readable, non-empty and no larger than 32 MiB. It
must pass the pinned SG13G2 main and additional maximal DRC scopes in deep
mode without waivers; density and antenna checks are outside this declared scope. It must
also pass strict named-port LVS against `materials/circuit.cdl`, including
the five ports, device multiplicities, passive geometry and the same-net
substrate tap. Artifact, DRC, LVS and geometry gates all precede candidate
extraction.

The GDS must include the complete target hierarchy. Port names are matched
case-insensitively; each declared port must remain on its own conductor with
the declared connectivity.

The functional outline is the recursive bounding box of polygons on these
SG13G2 datatype-0 layers, including child cells and the complete routing stack:

`1, 3, 5, 6, 7, 8, 10, 11, 13, 14, 19, 24, 26, 28, 29, 30, 31, 32, 33, 35, 36, 40, 44, 46, 49, 50, 51, 52, 53, 55, 58, 66, 67, 90, 101, 111, 125, 126, 128, 129, 133, 134, 139, 152`.

The maximum width is 720 µm and the maximum height is
860 µm, measured along the submitted X and Y axes.
Functional area is width multiplied by height. Text, annotation and filler
layers are excluded. The area score below uses this same functional footprint.

Candidate post-layout extraction combines candidate-derived HBT geometry and
`Nx` with distributed interconnect resistance and capacitance. Drawn emitter
geometry is checked against the candidate; effective ordinary `npn13G2`
dimensions use the simulator model defaults, with the extracted `Nx` retained. It preserves
device terminals, resistor and MIM geometry, top-level connectivity and the
same-net substrate boundary. The simulator export represents the tap with
its finite PDK equivalent `R=43.80789 Ω`; because both tap terminals are
`VEE`, this element has no DC voltage drop. The `rshunt` conditioning and
substrate boundary are numerical model choices and do not add an external
port or change the maintained circuit.

## Electrical Requirements and Scoring

The evaluator runs all five metrics at each of the three input-current
conditions. Transfer at 1 MHz is the real signed value of
`V(OUTPUT)/I(VSENSE)`; transfer at 100 MHz is its magnitude. Every required
observation must be present, finite and within its interval. A failed, missing or
erroring physical or simulation job fails the case; no incomplete evaluation
can establish success.

| Metric | Measurement | Unit | Acceptance |
|---|---|---|---|
| `transimpedance_low` | Signed transfer at 1 MHz | Ω | 150–350 |
| `transimpedance_high` | Magnitude of transfer at 100 MHz | Ω | 150–350 |
| `input_bias` | DC voltage at `INPUT` | V | 0.85–1.05 |
| `output_bias` | DC voltage at `OUTPUT` | V | 0.9–1.7 |
| `supply_power` | Sum of power from `VCC2V` and `VCC2V1` | mW | 30–80 |

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
| `transimpedance_low` | `response` | 0 | 700 | Ω |
| `transimpedance_high` | `response` | 0 | 700 | Ω |
| `input_bias` | `bias` | 0.75 | 1.15 | V |
| `output_bias` | `bias` | 0.7 | 1.9 | V |
| `supply_power` | `supply` | 15 | 120 | mW |

For a fully accepted candidate, area utility is
`Q = clip((619,200 − area) / (619,200 − 590,000), 0, 1)`,
with area in µm². The fixed full-score area target is
590,000 µm²; the zero-area-utility boundary is 619,200 µm².
Area earns no points until all electrical requirements pass.

The task coefficient is `2`. A batch averages all scheduled independent
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
`FMD_QNC_03a_TIA_1` and wait for the submission receipt:

```bash
python -I /protocol/submit.py
```

The evaluator uses the submitted snapshot for all physical checks, extraction
and simulations.
