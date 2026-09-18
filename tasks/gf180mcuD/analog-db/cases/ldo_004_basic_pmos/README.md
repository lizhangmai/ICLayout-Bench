> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Externally Biased 1.8 V PMOS Regulator Core

## Overview

This maintained GF180MCU D regulator core contains a four-transistor error
amplifier, a PMOS pass device of 100 parallel 10/0.3 um units and two physical
100-square high-resistance poly feedback resistors. It exposes five ports:
`vdd vout vref ibias vss`. The upstream MOS sizes and feedback ratio are retained;
the ideal reference and tail sink become external testbench sources, the ideal
divider becomes process resistors, and the zero-volt loop probe becomes a wire.
The reference layout is independently constructed.

The maintained operating point uses an external 0.9 V reference for approximately
1.8 V output, rather than the upstream 0.65 V reference. This gives positive
error-amplifier tail headroom with the retained 200 uA sink; tail voltage is an
explicit requirement. Qualification covers TT, 27 C, three supplies (2.2, 2.7,
3.3 V), three loads (0.1, 1, 5 mA), an ideal external 1 uF output capacitor,
load-step recovery, supply rejection, output impedance peaking and dropout.
It does not qualify a self-biased three-port LDO, startup, full loop phase margin,
PVT, mismatch, noise, EM, thermal behavior or fabrication signoff.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and 13 simulation jobs |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative physical circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | DC, supply-rejection and output-impedance analyses |
| [materials/transient.spice](materials/transient.spice) | Distinct load-step transient analysis |
| [materials/dropout.spice](materials/dropout.spice) | Distinct low-supply DC sweep and crossing measurement |
| [reference/ldo_004_basic_pmos.gds](reference/ldo_004_basic_pmos.gds) | Ready-to-use physical witness, excluded from solver inputs |

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

Measured `layout-v2` score: **26.669807**, with electrical quality
**E = 0.73888364** and area quality **Q = 0.096263955**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **78921.752 um2**.

Area reference: **7597.32 um2**. 106 expanded device instances; sum of device/contact envelopes 4876.0000 um2, per-side envelope allowance 1 um, 50% routing allowance and outer margin 2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 1.7997982 … 1.8060988 | 1.8007112 … 1.8062375 | 0.99967758 |
| `tail_v` | V | 0.086371187 … 0.092771005 | 0.084233607 … 0.090594193 | 0.99933962 |
| `quiescent_a` | A | 0.00020887493 … 0.00020908752 | 0.00020887555 … 0.00020908095 | 0.99999505 |
| `power_w` | W | 0.000679592 … 0.01718954 | 0.00067958366 … 0.01718951 | 0.9999998 |
| `psrr_db` | dB | 61.37198 … 104.8581 | 53.5666 … 100.5262 | 0.29472705 |
| `peaking_db` | dB | 0 | 0 … 4.0718907 | 0.62575664 |
| `peak_error_v` | V | 0.005909084 … 0.006098814 | 0.006042282 … 0.006237456 | 0.97777623 |
| `high_settled_error_v` | V | 7.380036e-05 … 0.0002924197 | 0.0007112089 … 0.001356717 | 0.067177947 |
| `low_settled_error_v` | V | 0.005909084 … 0.006098814 | 0.006042282 … 0.006237456 | 0.97777623 |
| `tail_min_v` | V | 0.08637119 … 0.09112281 | 0.08418127 … 0.08894713 | 0.99933683 |
| `dropout_v` | V | 0.049365 | 0.135254 | 0.36498466 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The coefficient is 7 for closed-loop regulation combining amplifier, pass-array
and passive feedback behavior over multiple regimes.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case gf180mcuD.analog-db.ldo_004_basic_pmos --image iclayout-bench-tools:local \
  --output build/runs/ldo_004_basic_pmos-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/ldo_004_basic_pmos-prepared \
  --output build/runs/ldo_004_basic_pmos-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'ldo_004_basic_pmos'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [MacAnalog analog-db ldo_004_basic_pmos](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_004_basic_pmos), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
