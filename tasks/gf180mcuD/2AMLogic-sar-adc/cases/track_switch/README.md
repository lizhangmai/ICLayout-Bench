> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Dummy-Compensated Track Switch

## Overview

**Qualified, with a passing reference layout.** A complementary transmission gate with two dummy MOS devices for charge compensation. The source default widths are specialized to 40, 80, 17.5 and 35 um, and its implicit ground is exposed as vss; these changes preserve the original default circuit. The independently constructed reference includes isolated body contacts and a complete physical implementation.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/adc_tgate_dum.gds](reference/adc_tgate_dum.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

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

Measured `layout-v2` score: **38.389392**, with electrical quality
**E = 0.77852807** and area quality **Q = 0.18929895**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **3710.85 um2**.

Area reference: **702.46 um2**. 4 expanded device instances; sum of device/contact envelopes 411.5400 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `high` | V | 2.5 | 2.5 | functional |
| `low` | V | 0.5 | 0.5 | functional |
| `hold` | V | 0.003106877 | 0.02900351 | 0.99221364 |
| `settling` | s | 4.361648e-10 | 7.140155e-10 | 0.61086235 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 4 covers the complementary switch, dummy compensation and loaded tracking/hold behavior.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.2AMLogic-sar-adc.track_switch --image iclayout-bench-tools:local \
  --output build/runs/track_switch-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/track_switch-prepared \
  --output build/runs/track_switch-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'track_switch'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/2AMLogic/gf180-sar-adc/tree/c32c8da53e52fbb7d75f6f628b8cc9f6f45a13fc/design/adc-top/adc_top.spice); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
