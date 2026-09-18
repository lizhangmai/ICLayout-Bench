> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Resistor-Pullup NMOS Shunt Trim

## Overview

A W=2 um / L=0.5 um NMOS shunts the output of an approximately 200 kohm
physical pullup. Eight W=1 um / L=17.465 um high-poly segments replace the source
ideal resistor; MOS dimensions and all connections are retained, with an
explicit substrate contact. The independent reference retains the full resistor
area and body connection.

Qualification covers nonlinear trim range, sampled monotonic control,
finite-bias shunt conductance and loaded recovery across 1.1/1.3 V,
27/85 C and 500 kohm/1 Mohm loads. Output varies substantially with load and
temperature; this is an unbuffered control node, not precision conversion or
an ideal programmable resistor.

## Files

- [Problem](problem.md): complete solver contract and scope.
- [Configuration](case.toml): input digests, requirements, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical devices.
- [Testbench](materials/testbench.spice): control sweep, conductance and step recovery.
- [Reference](reference/trm_001_vcr.gds): independently constructed physical witness.

Only the problem and three materials enter solver inputs. Collection licenses
and notices accompany distributions separately; no source generator or original
layout is needed.

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The drawing depicts the authoritative netlist; evaluation requirements are
defined by the current case configuration.

## Reference Results

Reference results use the pinned IHP SG13G2 ciel release described in
[resource preparation](../../../../../docs/tools.md#ihp-physical-check-profiles).

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **28.89134629**, with electrical quality
**E = 0.99770028** and area quality **Q = 0.083663391**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **7608.70425 um2**.

Area reference: **636.57 um2**. 10 expanded device instances; sum of device/contact envelopes 391.7515 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.048928095 … 0.063328792 | 0.049153295 … 0.063619726 | 0.99976471 |
| `power_w` | W | 5.8002812e-06 … 9.2495072e-06 | 5.7979386e-06 … 9.2453209e-06 | 1.0003987 |
| `high_v` | V | 0.7064219 … 1.041178 | 0.7063899 … 1.041143 | 0.99996192 |
| `low_v` | V | 0.007459411 … 0.0127078 | 0.007680443 … 0.01300553 | 0.99977103 |
| `knee_code_v` | V | 0.3227419 … 0.3628944 | 0.3227983 … 0.3629608 | 0.999941 |
| `maximum_slope` | V/V | -0.023065316 … -0.014507299 | -0.023056621 … -0.014500865 | 0.99989427 |
| `span_v` | V | 0.6957099 … 1.0323365 | 0.69542711 … 1.0320393 | 0.99974361 |
| `conductance_04_s` | S | 9.702293e-05 … 0.0001196524 | 9.653373e-05 … 0.0001189998 | 0.99566818 |
| `conductance_06_s` | S | 0.0003544861 … 0.0004249599 | 0.0003493221 … 0.0004176012 | 0.98549606 |
| `conductance_ratio` | 1 | 2.9810317 … 4.3571978 | 2.9535966 … 4.3036201 | 0.98939806 |
| `recovery_down_v` | V | 2.748335e-10 … 2.949312e-09 | 1.60939e-09 … 4.571529e-09 | 0.99709168 |
| `recovery_up_v` | V | 2.708194e-09 … 4.499059e-08 | 1.24619e-10 … 3.844061e-08 | 0.97516861 |
| `mean_power_w` | W | 4.566792e-06 … 8.015902e-06 | 4.565953e-06 … 8.012931e-06 | 1.0001767 |
| `step_span_v` | V | 0.29636584 … 0.63795004 | 0.29632681 … 0.63783733 | 0.99988232 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

The sampled control slope must be nonpositive in every condition. Endpoint
voltages contribute continuous source-paired quality within the output rail
domain, using the 1.3 V supply scale; no narrow absolute endpoint target is
required. This evaluation uses ngspice 45 and the pinned native IHP resources.

Capability coefficient: **4** for the fixed circuit and its declared functional scope.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.trm_001_vcr --image iclayout-bench-tools:local \
  --output build/runs/trm_001_vcr-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/trm_001_vcr-prepared \
  --output build/runs/trm_001_vcr-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'trm_001_vcr'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db trm_001_vcr at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/trm_001_vcr),
with PolyForm Noncommercial normalized-material terms and the recorded Apache
component attribution retained in [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE);
the independently authored measurement deck is MIT.
