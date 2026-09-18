> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Two-Input NAND

## Overview

Nominal, predictive **qualified** layout task with a distributed passing witness.
The [problem](problem.md) defines the complete circuit, stimuli, limits and score.
Coefficient **1** covers a compact loaded series/parallel logic cell.
The reference adds explicit well/substrate taps and extends rails to them, extends the outer poly ends by 10 nm, encloses poly contacts by at least 5 nm, and centers rail labels inside metal. Transistor W/L and topology are unchanged.

## Files

| File | Purpose |
| --- | --- |
| [problem.md](problem.md) | Solver objective, interface, physical and electrical requirements, and scoring |
| [case.toml](case.toml) | Single case configuration, input digests, toolchain, constraints, and evaluation plan |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative LVS and pre-layout simulator netlist |
| [materials/schematic.svg](materials/schematic.svg) | Analog Canvas transistor schematic for result browsing; presentation asset, excluded from solver inputs |
| [materials/testbench.spice](materials/testbench.spice) | Stimuli, loads, transient analysis, and measurements |
| [Collection LICENSE](../../LICENSE), [NOTICE](../../NOTICE) | Collection distribution terms; excluded from solver inputs |
| [reference/NAND2_X1.gds](reference/NAND2_X1.gds) | Passing feasibility witness, excluded from standard solver inputs |

The schematic preserves the authoritative netlist’s ordered ports, device models,
W/L values and D/G/S/B connections. It was exported with Analog Canvas at commit
`cbc18ee76ef91d88dd3e2dea9b47dd6d759f2d8f` and checked by SPICE round-trip
and its ERC/visual diagnostics. Its SVG metadata binds the source netlist digest.
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

Measured `layout-v2` score: **83.235024**, with electrical quality
**E = 0.69280692** and area quality **Q = 1**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1.6789 um2**.

Area reference: **1.6789 um2**. Complete functional bounding rectangle of the declared standard-cell reference GDS: 1.03 by 1.63 um = 1.6789 um2. Reference SHA-256: d077499ea242e1c8506c7a992ce713d46ea513c52b80073a2b7ae6d6515f2d3f. This footprint includes the maintained explicit taps and routing.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `state_0` | V | 0.9999975 | 0.9999975 | functional |
| `state_1` | V | 0.9999739 | 0.9999733 | functional |
| `state_2` | V | 0.0001741408 | 0.0008770521 | functional |
| `state_3` | V | 0.9998214 | 0.9998028 | functional |
| `state_4` | V | 0.999999 | 0.9999989 | functional |
| `state_5` | V | 0.9999582 | 0.9999578 | functional |
| `state_6` | V | 0.0001756712 | 0.0009153661 | functional |
| `state_7` | V | 0.9999739 | 0.9999731 | functional |
| `state_8` | V | 0.9999406 | 0.9999397 | functional |
| `supply` | W | 3.425277e-06 | 4.878972e-06 | 0.70204898 |
| `propagation_delay` | s | 9.335134e-12 … 1.515943e-11 | 1.333601e-11 … 2.138194e-11 | 0.6897296 |
| `output_transition` | s | 9.668356e-12 … 1.658675e-11 | 1.42665e-11 … 2.429691e-11 | 0.67769642 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **1** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case freepdk45.nangate45-pdk.NAND2_X1 --image iclayout-bench-tools:local \
  --output build/runs/NAND2_X1-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/NAND2_X1-prepared \
  --output build/runs/NAND2_X1-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'NAND2_X1'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Source: [NAND2_X1 at the pinned publication](https://foss-eda-tools.googlesource.com/third_party/freepdk45/+/356e90646f5ef26ea09b1ed8ce4796871403a0c7).
The upstream location is recorded in `case.toml` as `origin.url`.
The [collection license](../../LICENSE) and [notices](../../NOTICE) accompany
the maintained inputs and derived reference.
PDK models and rule/extraction resources retain their separate notices in the
reviewed support bundles; no Calibre SVRF deck is distributed by these profiles.
