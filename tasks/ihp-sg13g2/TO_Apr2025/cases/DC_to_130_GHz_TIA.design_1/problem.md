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
| `transimpedance_low` | `response` | ohm | maximize / ratio | 0 … +∞ | — |
| `transimpedance_high` | `response` | ohm | maximize / ratio | 0 … +∞ | — |
| `input_bias` | `bias` | V | target / target | 0 … 2.0 | 2.0 |
| `output_bias` | `bias` | V | target / target | 0 … 2.0 | 2.0 |
| `supply_power` | `supply` | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **3852.28 um2**. 8 expanded device instances; sum of device/contact envelopes 2487.4228 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **4**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

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
