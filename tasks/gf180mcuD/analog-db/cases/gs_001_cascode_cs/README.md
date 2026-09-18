> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Self-Biased Cascode Common-Source Gain Stage

## Overview

Nine MOS devices form a cascode common-source stage with PMOS and NMOS bias ladders. An external 20 uA sink biases the PMOS ladder. Total widths, lengths and multiplicities follow the fixed GF180 binding. Physical body contacts and an independently constructed reference complete the circuit.

VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V; external 20 uA sink from ibias to VSS; external 1 pF output load. A 1 TH external inductor connects output to input for the DC trip-point solve. A 1 F external coupling capacitor injects a unit AC input through acin while isolating the DC fixture. This measures open-loop small-signal gain at each self-biased trip point; it does not prescribe a fixed DC input voltage. Transient settling, fixed-input bias robustness, noise, mismatch, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/gs_001_cascode_cs.gds](reference/gs_001_cascode_cs.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **24.369619**, with electrical quality
**E = 0.99452407** and area quality **Q = 0.059714825**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **6604.725 um2**.

Area reference: **394.4 um2**. 9 expanded device instances; sum of device/contact envelopes 220.6500 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.7190888 … 0.71915119 | 0.71939484 … 0.71946532 | 0.99990482 |
| `bias_v` | V | 0.47188213 … 1.0718821 | 0.47084465 … 1.070845 | 0.99968571 |
| `power_w` | W | 0.00015931166 … 0.00019988954 | 0.00015921349 … 0.00019980649 | 1.0004157 |
| `gain_db` | dB | 33.3961 … 33.66256 | 33.36374 … 33.63149 | 0.99627217 |
| `bandwidth_hz` | Hz | 521841.2 … 538586.7 | 506604.5 … 522917.8 | 0.97080204 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 4 for a complete compact cascode stage with bias ladders and a load.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.gs_001_cascode_cs --image iclayout-bench-tools:local \
  --output build/runs/gs_001_cascode_cs-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/gs_001_cascode_cs-prepared \
  --output build/runs/gs_001_cascode_cs-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'gs_001_cascode_cs'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db gs_001_cascode_cs](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/gs_001_cascode_cs), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
