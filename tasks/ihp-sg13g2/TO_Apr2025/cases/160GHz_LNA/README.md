# Four-Stage SiGe HBT Voltage Amplifier

## Overview

This case contains a qualified four-stage direct-coupled SiGe HBT voltage
amplifier. Four `npn13G2` common-emitter stages use collector loads,
emitter degeneration and three interstage `VBIAS` clamps. The case-owned
interface is `IN OUT VDD VSS VBIAS`. The four emitter `rsil` lengths are
20.00/20.01/20.02/20.03 um, giving repeated emitter contacts distinct
candidate-derived device identities for the cross-extractor mapping.

Qualification covers nominal 100 MHz voltage
gain, output bias and `VDD` supply current at the declared bias point. The
candidate extraction boundary and substrate calibration are recorded in the
[problem](problem.md#physical-requirements) and the calibration below.

## Files

| File | Purpose |
|---|---|
| [problem.md](problem.md) | Solver-facing layout, physical and electrical contract |
| [case.toml](case.toml) | Frozen task inputs, constraints, toolchain and evaluation plan |
| [materials/circuit.cdl](materials/circuit.cdl) | Strict LVS netlist with drawn HBT geometry |
| [materials/circuit.spice](materials/circuit.spice) | Ready-to-use pre-layout simulator netlist |
| [materials/testbench.spice](materials/testbench.spice) | Shared nominal operating-point and AC testbench |
| [Collection LICENSE](../../LICENSE) | Collection distribution terms; excluded from solver inputs |
| [reference/LNA160_FOUR_STAGE.gds](reference/LNA160_FOUR_STAGE.gds) | Qualified reference layout, top cell `LNA160_FOUR_STAGE` |

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

Measured `layout-v2` score: **31.992850**, with electrical quality
**E = 0.97560345** and area quality **Q = 0.10491378**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **12642 um2**.

Area reference: **1326.32 um2**. 16 expanded device instances; sum of device/contact envelopes 836.9640 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `gain_db` | dB | 40.85778 | 40.83956 | 0.99790454 |
| `output_bias` | V | 1.00304 | 0.932008 | 0.9441147 |
| `supply_current` | A | 0.00053701 | 0.000544849 | 0.98561253 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

### Calibration limits

For the finite-body source control, all HBT bulk terminals use SUBSTRATE
and the source tap retains 81.6666667 ohm. For the ideal-body control, replace
SUBSTRATE by VSS and remove the tap. Both runs use the same nominal deck,
models and measurements. Compare the five terminal metrics using the absolute
tolerances below. A VBIAS sweep checks the bias window and saturation boundary;
internal source/native stage nodes are diagnostic only. These controls do not
change the scored candidate circuit or acceptance limits.

The following maintainer regression limits are read by the reproduction tests;
they do not add solver requirements.

| Comparison | Unit | Maximum difference |
| --- | --- | --- |
| `vin_bias` | V | 1e-09 |
| `out_bias` | V | 0.001 |
| `i_vdd` | A | 1e-05 |
| `i_vbias` | V | 1e-05 |
| `gain_db` | dB | 40.85778 | 40.83956 | 0.99790454 |


Coefficient 5 reflects four cascaded HBT stages with independent bias clamps
and interstage parasitics under the nominal gain and bias contract.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case TO_Apr2025.160GHz_LNA --image iclayout-bench-tools:local \
  --output build/runs/160GHz_LNA-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/160GHz_LNA-prepared \
  --output build/runs/160GHz_LNA-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k '160GHz_LNA'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

The model-boundary calibration tolerances above are exercised by `tests/integration/test_lna160_postlayout.py`.

## Source and License

Adapted from the [`160GHz_LNA` circuit](https://github.com/IHP-GmbH/TO_Apr2025/blob/63e203a0eccfb6028a1a0a8364553e4e979b55b3/160GHz_LNA/design_data/qucs-s/160GHz_LNA(MAIN).sch).

Case materials: [Apache-2.0](../../LICENSE). PDK, model and tool licenses
apply to their respective materials.
