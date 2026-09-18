> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Quadrature Voltage-Controlled Oscillator

## Overview

**Qualified, with a passing reference layout.** A four-stage differential ring oscillator with a common current-control network and two differential output buffers. The reference is an independently routed feasibility witness with separate source/body contacts and a short control-input wire. It deliberately establishes feasibility rather than a compact-layout optimum.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/vco.gds](reference/vco.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

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

Measured `layout-v2` score: **16.319596**, with electrical quality
**E = 1.0285582** and area quality **Q = 0.025893452**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **35031.25 um2**.

Area reference: **907.08 um2**. 47 expanded device instances; sum of device/contact envelopes 540.0800 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `low_control_frequency` | Hz | 97631840 | 17532880 | 0.65189343 |
| `high_control_frequency` | Hz | 2.459757e+08 | 50127620 | 0.60502402 |
| `tuning` | 1 | 2.51942 | 2.859063 | 1.13481 |
| `quadrature90` | 1 | 0.2499969 … 0.2500067 | 0.2604675 … 0.2605027 | 0.98961302 |
| `quadrature180` | 1 | 0.4999975 … 0.5000085 | 0.5000284 … 0.5043307 | 0.9956964 |
| `quadrature270` | 1 | 0.7500025 … 0.7500184 | 0.7613728 … 0.762118 | 0.98802953 |
| `low` | V | -0.0107174 … -0.004189262 | 0.005874613 … 0.01540607 | functional |
| `high` | V | 3.309453 … 3.317764 | 3.283485 … 3.295631 | functional |
| `supply` | W | 0.001899201 … 0.002622109 | 0.001563096 … 0.002113931 | 1.2150252 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 8 reflects the coupled feedback, tuning, speed and quadrature requirements.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.tt_tnt_gf_vco.vco --image iclayout-bench-tools:local \
  --output build/runs/vco-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/vco-prepared \
  --output build/runs/vco-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'vco'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/smunaut/tt_tnt_gf_vco/tree/897b3ec12ed693161fb56f4205d1b19dc5e56c1a/xschem/vco.sch); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
