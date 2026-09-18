> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Auxiliary Source-Driven Output-Control OTA

## Overview

Lay out `amp_012_peng_tcfc` with its complete transistor signal and bias paths.
The PMOS-input folded stage produces `voutp`, driving the output PMOS and
`net043` branch. The large PMOS path through `net049` feeds `net10`, while
`net043` controls its NMOS pulldown. `net10` drives the output NMOS. Preserve
both original compensation branches and the added local output-control MIM.
Unlike a direct `net050/net049` output stage, this circuit includes the
source-driven auxiliary PMOS and a separate `net10` control node.

Qualification covers 1.2 V, typical IHP LV models at 27 C, both 0.5/0.7 V
DC input points and 5/10/15 pF external loads. Positive and negative 200 mV
steps must sustain 2 mV tracking in the declared windows. See the
[problem](problem.md) for the complete contract.

MOS dimensions are rounded to the 10 nm physical grid. Parallel regrouping
within each original group preserves its rounded total W and L, with at most
10 um single-finger width; individual width/multiplicity and diffusion perimeter
change. Distributed 2 × 2 um body contacts have at most 20 um pitch.
All internal capacitors use `cap_cmim`:

- `c0`: `voutp` (top) to `vout` (bottom), 1 parallel 35.325 × 35.325 um MIM units.
- `c1`: `net049` (top) to `vout` (bottom), 1 parallel 41.2 × 41.2 um MIM units.
- `clocal`: `net10` (top) to `vout` (bottom), 1 parallel 51.64 × 51.64 um MIM units.

The raw 1.29849 uA sink is calibrated to 0.16231125 uA. A real approximately
4 pF `net10–vout` MIM is added to suppress the internal output-control
oscillation. Both original 1.87196 pF `voutp–vout` and 2.54606 pF
`net049–vout` branches remain. There is no added output-to-ground capacitor.
No ideal servo, diagnostic clamp or hidden damping element is part of this DUT.


## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): inputs, physical checks, metrics, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical device graphs.
- [Testbench](materials/testbench.spice): bias, bilateral loop and sustained recovery.
- [Reference layout](reference/amp_012_peng_tcfc.gds): independent physical witness.

Only the problem and three materials files enter solver inputs. Source records,
configuration, reference and qualification answers remain outside those inputs.
Collection license and notice accompany distributions separately.

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

Measured `layout-v2` score: **31.340924**, with electrical quality
**E = 1.0358525** and area quality **Q = 0.094825618**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **155127.2784 um2**.

Area reference: **14710.04 um2**. 180 expanded device instances; sum of device/contact envelopes 9648.5648 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.50048525 … 0.70049288 | 0.50049232 … 0.70050006 | 0.99999402 |
| `output_error_v` | V | 0.00048525143 … 0.00049288168 | 0.00049231983 … 0.00050006313 | 0.98566757 |
| `bias_v` | V | 0.83101787 … 0.83101816 | 0.83099087 … 0.83099118 | 0.9999775 |
| `power_w` | W | 9.7245469e-06 … 9.7572849e-06 | 9.7273738e-06 … 9.7601184e-06 | 0.99970939 |
| `dc_gain_db` | dB | 101.3742 … 103.6586 | 101.4153 … 103.7541 | 1.004743 |
| `unity_hz` | Hz | 366723.5 … 398205.7 | 363648.1 … 396783.7 | 0.99119332 |
| `phase_margin_deg` | deg | 60.4251 … 64.5516 | 54.2949 … 59.4769 | 0.96706499 |
| `final_unity_hz` | Hz | 366723.5 … 398205.7 | 363648.1 … 396783.7 | 0.99119332 |
| `final_phase_margin_deg` | deg | 60.4251 … 64.5516 | 54.2949 … 59.4769 | 0.96706499 |
| `minimum_return_distance` | 1 | 0.46029521 … 0.6719657 | 0.43671386 … 0.62945953 | 0.95860473 |
| `return_phase_excursion_deg` | deg | 89.757913 … 89.787925 | 89.780352 … 89.808146 | 0.99974596 |
| `hf_gain_db` | dB | -60.53757 … -51.79715 | -74.43889 … -65.90893 | 4.9386187 |
| `recovery_up_v` | V | 0.0004928885 … 0.0004928907 | 0.0005000618 … 0.0005000638 | 0.98567987 |
| `recovery_down_v` | V | 0.0004853169 … 0.0004853358 | 0.0004923604 … 0.0004923887 | 0.98570519 |
| `step_gain` | V/V | 1.000038 | 1.000039 | 0.999999 |
| `mean_power_w` | W | 9.743154e-06 … 9.749601e-06 | 9.746252e-06 … 9.752659e-06 | 0.99967788 |
| `peak_v` | V | 0.7009345 … 0.7034029 | 0.7026497 … 0.703412 | 0.99857271 |
| `trough_v` | V | 0.4972896 … 0.4981424 | 0.4925557 … 0.4943265 | 0.99607058 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 8 reflects multistage
feedback, coupled physical compensation and loaded sustained recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_012_peng_tcfc --image iclayout-bench-tools:local \
  --output build/runs/amp_012_peng_tcfc-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_012_peng_tcfc-prepared \
  --output build/runs/amp_012_peng_tcfc-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_012_peng_tcfc'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [the fixed source snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_012_peng_tcfc).
IHP raw DUT SHA-256: `bf38368898ea174c0ed978bd73c731d88815e1607d4cbf915496d4cd6227d302`.
Selected raw DUT, manifest, analyses and collection licensing files were checked
against the fixed Git tree. Normalized circuit derivatives and the independent
witness retain PolyForm Noncommercial, Required Notice and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE). The separately authored native measurement deck
is MIT. Component labels do not relicense normalized materials or the witness.
