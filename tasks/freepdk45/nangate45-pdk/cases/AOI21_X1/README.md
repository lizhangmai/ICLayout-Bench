> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# AND-OR-Invert Gate

## Overview

Nominal, predictive **qualified** layout task with a distributed passing witness.
The [problem](problem.md) defines the complete circuit, stimuli, limits and score.
Coefficient **2** covers a compact loaded compound logic cell.
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
| [reference/AOI21_X1.gds](reference/AOI21_X1.gds) | Passing feasibility witness, excluded from standard solver inputs |

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

Measured `layout-v2` score: **86.636432**, with electrical quality
**E = 0.75058714** and area quality **Q = 1**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **2.0049 um2**.

Area reference: **2.0049 um2**. Complete functional bounding rectangle of the declared standard-cell reference GDS: 1.23 by 1.63 um = 2.0049 um2. Reference SHA-256: 1ebcc6f4d7a8f5c50846b5cdfd60f3039fb96caf455b89f2d7f30568c5a2af94. This footprint includes the maintained explicit taps and routing.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `state_0` | V | 0.999952 | 0.999951 | functional |
| `state_1` | V | 0.9998967 | 0.9999129 | functional |
| `state_2` | V | 0.0001918556 | 0.0006888252 | functional |
| `state_3` | V | 0.9994024 | 0.9981266 | functional |
| `state_4` | V | 0.0004865273 | 0.001137968 | functional |
| `state_5` | V | 1.239731e-06 | 1.24088e-06 | functional |
| `state_6` | V | 8.142936e-05 | 0.0001404172 | functional |
| `state_7` | V | -3.673975e-05 | -2.10431e-05 | functional |
| `state_8` | V | 0.9998379 | 0.9995095 | functional |
| `state_9` | V | 0.0004804343 | 0.001053172 | functional |
| `state_10` | V | 0.0003069374 | 0.0003234055 | functional |
| `state_11` | V | 1.216504e-06 | 1.240873e-06 | functional |
| `state_12` | V | 7.794863e-05 | 0.0001138873 | functional |
| `state_13` | V | 0.99935 | 0.997539 | functional |
| `state_14` | V | 0.0001950317 | 0.0007189033 | functional |
| `state_15` | V | 0.9998362 | 0.9989273 | functional |
| `state_16` | V | 0.9997699 | 0.9997589 | functional |
| `supply` | W | 4.305193e-06 | 5.653086e-06 | 0.76156514 |
| `propagation_delay` | s | 1.163873e-11 … 1.992426e-11 | 1.497704e-11 … 2.606879e-11 | 0.75595166 |
| `output_transition` | s | 1.274633e-11 … 2.079778e-11 | 1.760714e-11 … 2.728552e-11 | 0.72392961 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **2** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case freepdk45.nangate45-pdk.AOI21_X1 --image iclayout-bench-tools:local \
  --output build/runs/AOI21_X1-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/AOI21_X1-prepared \
  --output build/runs/AOI21_X1-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'AOI21_X1'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Source: [AOI21_X1 at the pinned publication](https://foss-eda-tools.googlesource.com/third_party/freepdk45/+/356e90646f5ef26ea09b1ed8ce4796871403a0c7).
The upstream location is recorded in `case.toml` as `origin.url`.
The [collection license](../../LICENSE) and [notices](../../NOTICE) accompany
the maintained inputs and derived reference.
PDK models and rule/extraction resources retain their separate notices in the
reviewed support bundles; no Calibre SVRF deck is distributed by these profiles.
