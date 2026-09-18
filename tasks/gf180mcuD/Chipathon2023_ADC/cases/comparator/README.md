> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Dynamic Comparator

## Overview

**Qualified, with a passing reference layout.** A clocked differential comparator with an input stage and a regenerative output stage, using the 15 MOS devices in the maintained source. The independently routed reference preserves all dimensions and connections. Both signs of the differential input are required.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/comp_20240331.gds](reference/comp_20240331.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

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

Measured `layout-v2` score: **18.941704**, with electrical quality
**E = 0.43126816** and area quality **Q = 0.083193753**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **3623.95 um2**.

Area reference: **301.49 um2**. 15 expanded device instances; sum of device/contact envelopes 164.1600 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `decision` | V | 3.299999 | 3.3 | functional |
| `delay` | s | 1.228056e-09 | 2.208843e-09 … 2.810156e-09 | 0.43700634 |
| `supply` | W | 9.475911e-05 | 0.0001891104 … 0.0002226455 | 0.42560533 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 6 covers the interacting dynamic input and regenerative stages.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.Chipathon2023_ADC.comparator --image iclayout-bench-tools:local \
  --output build/runs/comparator-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/comparator-prepared \
  --output build/runs/comparator-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'comparator'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/ishi-kai/Chipathon2023_ADC/tree/3dce439b2125a9d628e43be40c65cf8fce5d795c/gitefu/comp_20240331/comp_20240331.sch); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
