> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Six-Transistor SRAM Bitcell

## Overview

Nominal, predictive **qualified** layout task with a distributed passing witness.
The [problem](problem.md) defines the complete circuit, stimuli, limits and score.
Coefficient **6** covers a dynamic storage cell with write, hold and nondestructive read behavior.
The distributed reference preserves the original transistor and routing geometry.

## Files

| File | Purpose |
| --- | --- |
| [problem.md](problem.md) | Solver objective, interface, physical and electrical requirements, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative LVS and pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Stimuli, loads, transient analysis, and measurements |
| [Collection LICENSE](../../LICENSE), [NOTICE](../../NOTICE) | Collection distribution terms; excluded from solver inputs |
| [reference/cell_6t.gds](reference/cell_6t.gds) | Passing feasibility witness, excluded from standard solver inputs |

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The schematic depicts the authoritative netlist used by both simulation paths.

## Reference Results

FreePDK45 resources come from the pinned community installation, with the
explicit Magic model, marker and length-unit adaptations described in the tools guide.
Parasitics use the community technology's estimated coefficients.
See [resource preparation](../../../../../docs/tools.md) and the process manifest
for source pins, scope and reproducible preparation.

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **90.027704**, with electrical quality
**E = 0.75905151** and area quality **Q = 1.0677783**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1.367325 um2**.

Area reference: **1.46 um2**. 6 expanded device instances; sum of device/contact envelopes 0.6670 um2, per-side envelope allowance 0.12 um, 50% routing allowance and outer margin 0.24 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `read0` | V | 0.7858571 | 0.590123 | functional |
| `repeat0` | V | 0.7858571 | 0.590123 | functional |
| `read1` | V | 0.7858571 | 0.5925148 | functional |
| `repeat1` | V | 0.7858571 | 0.5925148 | functional |
| `supply` | W | 5.942012e-06 | 7.838401e-06 | 0.75806434 |
| `read_delay` | s | 1.317565e-11 | 1.728662e-11 … 1.733547e-11 | 0.76003996 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **6** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case freepdk45.OpenRAM.cell_6t --image iclayout-bench-tools:local \
  --output build/runs/cell_6t-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/cell_6t-prepared \
  --output build/runs/cell_6t-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'cell_6t'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Source: [cell_6t at the pinned publication](https://github.com/ferdous313/OpenRAM/tree/420a33e731d7d80bf9c7cd54ffbeec3603259847).
The upstream location is recorded in `case.toml` as `origin.url`.
The [collection license](../../LICENSE) and [notices](../../NOTICE) accompany
the maintained inputs and derived reference.
PDK models and rule/extraction resources retain their separate notices in the
reviewed support bundles; no Calibre SVRF deck is distributed by these profiles.
