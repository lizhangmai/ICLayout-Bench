> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Differential Polarity-Commutating Switch

## Overview

Eight MOS devices form four transmission paths that connect a differential input directly or with reversed polarity. The two complementary clock nets are independent layout ports. Fixed IHP W/L/m are retained; explicit substrate/well taps are included in both maintained circuit representations.

VDD = 1.5 V; VSS = 0 V; input common mode = 0.75 V; differential input = -0.2 or +0.2 V. Each output has an external 10 kohm resistor to common mode and 1 pF to ground. DC checks both clock states (vctl = 0 or 1.5 V), giving four conditions. Transient clocks are complementary 0/1.5 V pulses, delay 1 us, rise/fall 2 ns, high width 5 us and period 10 us; output/max step is 0.1 ns with Gear order 2, stop time 12 us. A second transient sets both inputs to 0.75 V to separate clock feedthrough/injection from signal reversal. The finite clock slopes deliberately permit overlap; non-overlap operation is not claimed.  Ron includes the declared terminal loading and common mode. Injection is net terminal charge integrated under driven equal inputs, not stored charge on a disconnected sampler. Noise, chopping an amplifier, RF/EM, mismatch and other clock rates are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical circuit |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/sw_002_chopper_diff.gds](reference/sw_002_chopper_diff.gds) | Independently constructed witness, excluded from solver inputs |

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The authoritative netlist, simulation decks and evaluation requirements are unchanged.

## Reference Results

Reference results use the pinned IHP SG13G2 ciel release described in
[resource preparation](../../../../../docs/tools.md#ihp-physical-check-profiles).

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **25.801631**, with electrical quality
**E = 0.33012168** and area quality **Q = 0.20166023**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **2279.4777 um2**.

Area reference: **459.68 um2**. 10 expanded device instances; sum of device/contact envelopes 278.7760 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `ron_p` | ohm | 812.8557 … 1388.0725 | 868.76251 … 1428.376 | 0.92345204 |
| `ron_n` | ohm | 812.8557 … 1388.0725 | 868.7477 … 1424.1957 | 0.92747597 |
| `transfer` | V/V | 0.90146839 | 0.89721643 … 0.89798143 | 0.99576604 |
| `common_error_v` | V | 0.0023356672 | 0.0021881282 … 0.0022202732 | 1.0519495 |
| `straight_gain` | V/V | 0.9014684 | 0.8972164 … 0.8972177 | 0.995766 |
| `crossed_gain` | V/V | -0.9014684 | -0.8979814 … -0.8979807 | 0.99652442 |
| `common_glitch_v` | V | 1.35409e-05 | 0.000676535 | 0.021461474 |
| `differential_glitch_v` | V | 3.219647e-15 | 0.00108759 | 0.0009186195 |
| `input_charge_c` | C | 3.422271e-18 | 1.123403e-15 | 0.0030472306 |
| `clock_power_w` | W | 2.250818e-09 | 8.067328e-09 | 0.27909351 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Capability coefficient: **5** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.sw_002_chopper_diff --image iclayout-bench-tools:local \
  --output build/runs/sw_002_chopper_diff-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/sw_002_chopper_diff-prepared \
  --output build/runs/sw_002_chopper_diff-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'sw_002_chopper_diff'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db sw_002_chopper_diff](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sw_002_chopper_diff), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
