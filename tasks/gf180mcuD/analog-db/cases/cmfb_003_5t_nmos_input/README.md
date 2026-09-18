> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Segmented-Resistor NMOS Common-Mode Controller

## Overview

Seven MOS devices form an NMOS-input common-mode error amplifier and self-bias network. Each ideal 5 Mohm sense arm is implemented as twenty series GF180 ppolyf_u_1k segments, each 2 um wide and 500 um long: 5,000 squares per arm. The segmentation, substrate terminals and intermediate nodes are part of the maintained circuit. The independent witness uses compact rows connected by metal; it retains both complete resistance chains.

VDD = 3.3 V; VSS = 0 V; VREF = 1.65 V. The external first-order inverting plant has drive = 3.3 V - V(vcmfb), followed by 100 kohm and 100 nF to common mode. V(vinp/vinn) = plant output + disturbance +/- d, where d = 0, 0.1 and 0.2 V in separate conditions. Disturbance is 0 through 10 ms, +0.1 V at 10.01 ms through 30 ms, -0.1 V at 30.01 ms through 50 ms, and 0 at 50.01 ms through 70 ms. A 10 pF external capacitor loads vcmfb. Transient output/max step is 10 us. This plant is test apparatus, not an internal ideal servo or a claimed transistor amplifier. Recovery windows are 25–29 ms and 45–49 ms for the positive/negative disturbances; error is measured at the average sensed inputs against VREF. Controller power excludes the external plant. Qualification covers recovery with this specified external plant, not stability with arbitrary amplifiers. The long physical sense chains retain candidate-derived parasitics. Startup, mismatch, noise, PVT and a complete differential amplifier are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative physical circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/cmfb_003_5t_nmos_input.gds](reference/cmfb_003_5t_nmos_input.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **68.515449**, with electrical quality
**E = 1.0213409** and area quality **Q = 0.45962782**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **266260.995 um2**.

Area reference: **122380.96 um2**. 47 expanded device instances; sum of device/contact envelopes 80826.5000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 1.6521036 | 1.6519569 … 1.6519574 | 0.99995553 |
| `error_v` | V | 0.0021036363 … 0.0021036363 | 0.0019568744 … 0.0019574126 | 1.0746644 |
| `power_w` | W | 0.00016284625 | 0.00016202185 | 1.0050882 |
| `recovery_up_v` | V | 0.001780462 | 0.001634283 … 0.001634822 | 1.0890317 |
| `recovery_down_v` | V | 0.002431036 | 0.002284726 … 0.002285264 | 1.0637599 |
| `recovery_zero_v` | V | 0.002103118 | 0.001956879 … 0.001957417 | 1.0743973 |
| `peak_error_v` | V | 0.2011193 | 0.2009729 … 0.2009735 | 1.0007255 |
| `mean_power_w` | W | 0.0001628409 | 0.0001620166 | 1.0050878 |

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
  --case gf180mcuD.analog-db.cmfb_003_5t_nmos_input --image iclayout-bench-tools:local \
  --output build/runs/cmfb_003_5t_nmos_input-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/cmfb_003_5t_nmos_input-prepared \
  --output build/runs/cmfb_003_5t_nmos_input-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'cmfb_003_5t_nmos_input'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db cmfb_003_5t_nmos_input](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmfb_003_5t_nmos_input), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
