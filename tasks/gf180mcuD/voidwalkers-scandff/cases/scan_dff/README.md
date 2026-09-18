> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Scan D Flip-Flop with Active-Low Reset

## Overview

**Qualified, with a passing reference layout.** A transmission-gate scan multiplexer and resettable D flip-flop. The reference retains the upstream geometry and uses the authoritative source top-cell name. Its contract checks data selection, stored high/low values, asynchronous reset and clock-to-output timing.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/gf180mcu_voidwalkers_sc_sdffrnq_4.gds](reference/gf180mcu_voidwalkers_sc_sdffrnq_4.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

Standard materialization contains only the five declared input files. It excludes this README, the case configuration, references, upstream checkouts and generation history. Physical/model resources are supplied separately as verified support bundles.

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The schematic depicts the authoritative netlist; the current layout requirements
and evaluation settings are declared in the task.

## Reference Results

GF180 resources come from the pinned ciel prebuilt distribution, including its
current KLayout rules, nominal models and variant-D Magic extraction.
The reference uses a 0.001 um GDS database unit; dummy COMP fill is included
where required by the rule deck.
See [resource preparation](../../../../../docs/tools.md) and the process manifest
for source pins, scope and reproducible preparation.

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **93.414342**, with electrical quality
**E = 0.87262393** and area quality **Q = 1**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **175.5775 um2**.

Area reference: **175.5775 um2**. Complete functional bounding rectangle of the declared standard-cell reference GDS: 27.65 by 6.35 um = 175.577 um2. Reference SHA-256: ffd6654d5505bf6340acbb3061ad81fab36951badda45b3bd3a8448be0fa00ab. This footprint includes the maintained explicit taps and routing.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `low` | V | 6.604153e-09 … 5.576545e-08 | 1.049328e-08 … 3.660766e-08 | functional |
| `high` | V | 3.3 | 3.3 | functional |
| `supply` | W | 4.187209e-05 | 4.996386e-05 | 0.83804754 |
| `propagation_delay` | s | 4.179378e-10 … 5.49924e-10 | 4.87768e-10 … 6.369726e-10 | 0.85683727 |
| `output_transition` | s | 2.787695e-10 … 3.358882e-10 | 2.89316e-10 … 3.481107e-10 | 0.96354678 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 5 covers the dynamic storage circuit and its scan/reset paths.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.voidwalkers-scandff.scan_dff --image iclayout-bench-tools:local \
  --output build/runs/scan_dff-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/scan_dff-prepared \
  --output build/runs/scan_dff-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'scan_dff'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/radityankn/voidwalkers-scandff-gf180mcu/tree/b136150cdcfd55a9568fe14a825c214c3af5dde4/designs/cells/gf180mcu_voidwalkers_sc_sdffrnq_4/sch/gf180mcu_voidwalkers_sc_sdffrnq_4.sch); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
