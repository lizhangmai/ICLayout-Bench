> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Mixed LV/HV VGS Reference

## Overview

The maintained circuit preserves the fixed-source two-transistor core: an LV
NMOS with gate/source tied to the output above a diode-connected HV NMOS.
It targets an approximately 0.36 V reference for picoampere loads, with
explicit substrate contacts and an independently constructed layout. The
[problem](problem.md) defines the finite supply, temperature and recovery scope.

## Files

- [Configuration](case.toml): frozen inputs, tool bindings and qualification.
- [Physical circuit](materials/circuit.cdl) and [simulator circuit](materials/circuit.spice): equivalent LV/HV devices and same-net tap boundary.
- [Testbench](materials/testbench.spice): DC sensitivity, zero-state ramp and signed load recovery.
- [Reference layout](reference/vref_001_vgs.gds): independent physical implementation.

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

Measured `layout-v2` score: **36.456796**, with electrical quality
**E = 0.96017404** and area quality **Q = 0.13842261**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1521.5 um2**.

Area reference: **210.61 um2**. 3 expanded device instances; sum of device/contact envelopes 121.7863 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `reference_v` | V | 0.35520483 … 0.36499095 | 0.35520484 … 0.36499062 | 0.99999971 |
| `supply_a` | A | 8.1886204e-12 … 1.9812328e-09 | 8.1886373e-12 … 1.9812299e-09 | 0.99999755 |
| `power_w` | W | 8.1886204e-12 … 2.9718492e-09 | 8.1886373e-12 … 2.9718449e-09 | 0.99999751 |
| `startup_error_v` | V | 3.147905e-10 … 2.04144e-07 | 3.194858e-09 … 4.860068e-07 | 0.74842234 |
| `load_error_v` | V | 1.864483e-05 … 0.003246418 | 1.864153e-05 … 0.003245838 | 1.0001457 |
| `release_error_v` | V | 3.174917e-10 … 2.036695e-07 | 3.190603e-09 … 4.859076e-07 | 0.74061499 |
| `injection_error_v` | V | 1.863711e-05 … 0.002965899 | 1.864091e-05 … 0.002966606 | 0.99976176 |
| `return_error_v` | V | 3.169571e-10 … 5.143982e-08 | 3.174125e-09 … 5.45183e-07 | 0.68046297 |
| `minimum_v` | V | 1.354617e-06 … 3.662084e-06 | 2.055271e-06 … 4.554411e-06 | 0.9999993 |
| `maximum_v` | V | 0.3552278 … 0.3671883 | 0.3552278 … 0.3671884 | 0.99993247 |
| `line_min_v` | V | 0.35520483 … 0.35555882 | 0.35520484 … 0.35555839 | 0.99999971 |
| `line_max_v` | V | 0.36357591 … 0.36499094 | 0.3635759 … 0.36499063 | 0.99999979 |
| `line_span_v` | V | 0.0082925317 … 0.009490708 | 0.0082925478 … 0.0094907129 | 0.99998674 |
| `temperature_min_v` | V | 0.35520483 … 0.36350028 | 0.35520484 … 0.36350026 | 0.99999996 |
| `temperature_max_v` | V | 0.35555882 … 0.36499095 | 0.35555839 … 0.36499062 | 0.99999971 |
| `temperature_span_v` | V | 0.00035399783 … 0.0014906684 | 0.00035354538 … 0.0014903581 | 0.99987467 |
| `output_resistance_ohm` | ohm | 18644508 … 3.2464994e+09 | 18644592 … 3.2465145e+09 | 0.99998203 |
| `loaded_reference_v` | V | 0.35231233 … 0.36467689 | 0.35231187 … 0.36467691 | 0.9999997 |

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
  --case ihp-sg13g2.analog-db.vref_001_vgs --image iclayout-bench-tools:local \
  --output build/runs/vref_001_vgs-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/vref_001_vgs-prepared \
  --output build/runs/vref_001_vgs-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'vref_001_vgs'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db VREF001 at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/raw/vref_001_vgs/ihp-sg13g2/_dut.spice), under the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE), including PolyForm Noncommercial and applicable component terms.

The upstream manifest identifies this worked example as `analog-circuit-design`
and labels the component Apache-2.0. Its four advertised analyses are provenance,
not imported qualification or PSRR evidence. The normalized source remains
subject to the collection's PolyForm Noncommercial terms and Required Notice;
the manifest label does not relicense the derivative as a whole.

| Fixed-snapshot file reviewed | SHA-256 |
| --- | --- |
| `raw/vref_001_vgs/ihp-sg13g2/_dut.spice` | `0f1570819e2437286917ef9370cb20b7266e3ca7449e861f30074a4caaad61a5` |
| `circuits/vref_001_vgs/circuit.yaml` | `de50462486c2f5e9f5c199de5b3f671366206d9d63b9069b091f648d4f8112af` |
| `LICENSE` | `160dfa809ed429d74457e192fd8b53505d053b7de0651e89d21c507ebe0aa3d3` |
| `NOTICE` | `e4644906a59d8dc2c378bfcecb375c9e513c6a2a38e8045be8f7e4e3e7c3a425` |

All paths in the audit table are relative to `analog-db/` in the pinned
snapshot. No external reference pointer was followed. Native testbench authoring
is identified separately as MIT; retain the collection LICENSE and NOTICE with
all circuit-material distributions.
