> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Series-Nulling-Resistor Two-Stage OTA

## Overview

A PMOS-input two-stage amplifier with physical series nulling resistance in its
Miller compensation path. The maintained circuit retains all eight source MOS
groups' W/L/m (27 individual MOS), externalizes the 100 nA bias sink through
`ibias`, and adds explicit substrate/well contacts. Two parallel 25.85 × 25.85 um
MIM units provide nominally 2.01294 pF. Four W=1 um, L=18 um `rhigh` segments
provide a nominal 102.64 kohm series chain at 27 C with the declared model.
The circuit uses physical devices for the source's ideal 2 pF / 100 kohm path.

Qualification covers 1.2 V, 27 C, typical models, 5/10/20 pF external loads,
loop gain about 0.5 V unity-feedback bias, and 0.5↔0.7 V finite-step recovery.
The 20 pF condition has approximately 44.7 degrees phase margin and 70 mV
positive overshoot; this is not a monotonic-response or arbitrary-load claim.
The series compensation adds a physical device and interstage parasitic path
to the direct-MIM two-stage topology. Noise, distortion, PVT, mismatch,
startup from zero supply and fabrication signoff are outside this qualification.

## Files

- [Problem](problem.md): complete solver contract, limits and scoring.
- [Configuration](case.toml): frozen task, tool bindings and reference identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice):
  matching physical device definitions with their native reader syntax.
- [Testbench](materials/testbench.spice): bias, return ratio and step measurements.
- [Reference layout](reference/amp_024_smcnr.gds): independently constructed witness.

Only the problem and three materials files are solver inputs. Collection
licenses/notices accompany distributions separately from solver materialization.
No upstream layout, generator, DSL, tuning history or scoreboard is required.

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

Measured `layout-v2` score: **39.854811**, with electrical quality
**E = 0.99817898** and area quality **Q = 0.15913037**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **36886.7985 um2**.

Area reference: **5869.81 um2**. 35 expanded device instances; sum of device/contact envelopes 3813.4378 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.49990888 | 0.49991164 | 0.9999977 |
| `bias_v` | V | 0.58972819 | 0.58968053 | 0.99996029 |
| `power_w` | W | 1.55793e-06 | 1.5580081e-06 | 0.99994986 |
| `dc_gain_db` | dB | 69.28808 | 69.2781 | 0.99885167 |
| `unity_hz` | Hz | 123342.7 … 165259.3 | 122410.5 … 164094.7 | 0.99209841 |
| `phase_margin_deg` | deg | 45.1515 … 71.4584 | 44.7027 … 70.6319 | 0.99542932 |
| `recovery_up_v` | V | 6.292729e-05 … 6.619118e-05 | 6.637927e-05 … 7.01806e-05 | 0.94395355 |
| `recovery_down_v` | V | 9.112525e-05 … 9.129919e-05 | 8.836366e-05 … 8.85765e-05 | 1.0303951 |
| `step_gain` | V/V | 1.00077 | 1.000774 | 0.999996 |
| `mean_power_w` | W | 1.532992e-06 … 1.533232e-06 | 1.533066e-06 … 1.533308e-06 | 0.99995043 |
| `peak_v` | V | 0.7012933 … 0.769071 | 0.7021363 … 0.7699192 | 0.99882455 |
| `trough_v` | V | 0.4816025 … 0.4997009 | 0.4808844 … 0.4994896 | 0.99940194 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 7 reflects the
coupled compensation, stability and closed-loop response requirements.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_024_smcnr --image iclayout-bench-tools:local \
  --output build/runs/amp_024_smcnr-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_024_smcnr-prepared \
  --output build/runs/amp_024_smcnr-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_024_smcnr'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_024_smcnr at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_024_smcnr),
with PolyForm Noncommercial normalized-material terms and the attributed
CODA-Team AnalogGym BSD-3-Clause component terms retained in the collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE); the independently authored
measurement deck is MIT.
