> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# MIM Switched-Capacitor Common-Mode Sampler

## Overview

Sixteen minimum-size MOS (W/L = 0.15/0.13 um) implement eight transmission paths. Four internal MIM capacitors retain the original connections: two separate vbias-to-vcm capacitors and two floating control-to-sense capacitors. Each is a 25.85 by 25.85 um cap_cmim, nominally about 1.00647 pF. Explicit physical substrate and well taps are included. The output samples common-mode displacement; this is a switched-capacitor sensing network with driven inputs, not a complete closed-loop amplifier or a loop-stability qualification.

Typical IHP low-voltage MOS, typical resistor and capacitor models at 27 C; VDD = 1.5 V and VSS = 0 V. Each node has the declared 1e12 ohm numerical shunt. Transient integration uses Gear order 2 with a 1 ns output and maximum step. Physical taps have finite source-model resistance; Magic treats well/substrate ties ideally. Distributed silicon substrate resistance, statistical mismatch, PVT, noise and RF/EM are outside scope.

Vcm = 0.75 V; Vbias = 0.6 V. Each condition starts with input common mode 0.75 V. It changes linearly over 40–40.1 us to common_v, then holds through 100 us. Inputs are common mode +/- diff_v. The five (common_v, diff_v) pairs in volts are (0.65,0), (0.65,0.1), (0.75,0.1), (0.85,0), (0.85,0.1). Phi starts high, falls after 1 us, and alternates with its complementary independent clock; rise/fall times are 2 ns, low width 5 us and period 10 us. Phi high precharges the floating capacitors; phi low couples them to the sensed inputs and output. Finite complementary slopes permit overlap. An external 1 pF loads vcmfb; stop time is 100 us. The target after repeated transfers is 0.6 V + common_v - 0.75 V.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver contract and scoring |
| [case.toml](case.toml) | Frozen inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical netlist |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurements |
| [reference/cmfb_004_output_switched_cap.gds](reference/cmfb_004_output_switched_cap.gds) | Independent witness, excluded from solver inputs |

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

Measured `layout-v2` score: **18.804646**, with electrical quality
**E = 0.13831794** and area quality **Q = 0.25565356**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **20589.5824 um2**.

Area reference: **5263.8 um2**. 22 expanded device instances; sum of device/contact envelopes 3414.7414 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.5001887 … 0.6998088 | 0.5025711 … 0.697334 | 0.99835285 |
| `sample_error_v` | V | 2.520536e-06 … 0.0001925041 | 4.491021e-05 … 0.002666033 | 0.072080585 |
| `hold_drift_v` | V | 9.400405e-05 … 0.0001883919 | 0.0002111733 … 0.0002683448 | 0.35305009 |
| `clock_power_w` | W | 3.654853e-10 … 3.768236e-10 | 2.173587e-08 … 2.207999e-08 | 0.01661591 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 5 reflects periodic charge transfer, independent clock routing and interacting floating capacitors.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.cmfb_004_output_switched_cap --image iclayout-bench-tools:local \
  --output build/runs/cmfb_004_output_switched_cap-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/cmfb_004_output_switched_cap-prepared \
  --output build/runs/cmfb_004_output_switched_cap-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'cmfb_004_output_switched_cap'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db `cmfb_004_output_switched_cap` at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmfb_004_output_switched_cap), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE); independently authored testbench under MIT.
