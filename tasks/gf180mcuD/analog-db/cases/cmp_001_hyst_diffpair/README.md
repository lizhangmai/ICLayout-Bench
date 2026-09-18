> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Resistive-Feedback Hysteretic Comparator

## Overview

A differential input stage, resistive positive feedback and three output inverters form a hysteretic comparator. Twelve MOS entries expand to 28 physical instances. The physical ppolyf_u_1k resistors are width 2 um: two 600 um feedback devices (300 squares) and one 12 um tail device (6 squares). MOS sizes and multiplicities are retained; ideal resistors become substrate-connected process devices.

VDD = 3.3 V, VSS = 0 V, VINN = 1.65 V. VINP stays at 1.45 V through 0.1 ms, ramps to 1.85 V at 1.1 ms, holds through 1.2 ms, ramps back to 1.45 V at 2.2 ms, then holds through 2.3 ms. Each ramp magnitude is 0.4 V/ms. Evaluate external loads of 1, 5 and 10 pF separately with a 0.2 us transient output step. The transient starts from its DC operating point. Thresholds include this finite ramp rate and output load. Offset is intentional and is not zero-centered about VINN. Metastability, fast decision delay, startup, noise, statistical offset, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/cmp_001_hyst_diffpair.gds](reference/cmp_001_hyst_diffpair.gds) | Independently constructed witness, excluded from solver inputs |

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

Measured `layout-v2` score: **37.302565**, with electrical quality
**E = 1.0045259** and area quality **Q = 0.1385212**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **60543.6549 um2**.

Area reference: **8386.58 um2**. 31 expanded device instances; sum of device/contact envelopes 5392.5600 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `rising_input` | V | 1.694373 … 1.694397 | 1.69392 … 1.693935 | 0.99985548 |
| `falling_input` | V | 1.681959 … 1.682001 | 1.680888 … 1.680902 | 0.99966284 |
| `hysteresis_v` | V | 0.012372 … 0.012438 | 0.013018 … 0.013047 | 0.9997955 |
| `mean_power_w` | W | 0.0005595666 … 0.0005599238 | 0.0005542408 … 0.0005544089 | 1.0093031 |
| `low_v` | V | 2.869148e-09 … 2.86915e-09 | 5.468602e-05 | functional |
| `high_v` | V | 3.3 | 3.298868 | functional |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 5 for regenerative feedback and a multi-stage output path.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.cmp_001_hyst_diffpair --image iclayout-bench-tools:local \
  --output build/runs/cmp_001_hyst_diffpair-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/cmp_001_hyst_diffpair-prepared \
  --output build/runs/cmp_001_hyst_diffpair-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'cmp_001_hyst_diffpair'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db cmp_001_hyst_diffpair](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmp_001_hyst_diffpair), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
