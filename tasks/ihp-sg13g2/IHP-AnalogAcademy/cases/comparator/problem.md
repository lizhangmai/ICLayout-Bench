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
| `worst_delay` | `response` | s | minimize / ratio | 0 … +∞ | — |
| `decision_margin` | `response` | V | functional check | 1.0 … +∞ | — |
| `supply_power` | `supply` | W | minimize / ratio | 0 … +∞ | 1e-12 |

Area reference: **502.96 um2**. 24 expanded device instances; sum of device/contact envelopes 306.3377 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

The capability coefficient remains **6**; it is independent of
the reference-relative task score.

## Tools and Submission

Solve budget: **3 hours**.

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
