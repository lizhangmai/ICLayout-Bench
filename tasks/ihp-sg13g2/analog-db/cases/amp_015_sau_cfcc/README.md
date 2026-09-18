> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Input-Driven Active-Feedforward OTA

## Overview

Lay out `amp_015_sau_cfcc` with its complete transistor signal and bias paths.
The PMOS-input folded stage produces `voutn`, controlling the mirror at
`net050` and the auxiliary PMOS at `net049`. The `net050 → net043 → net049`
path and direct input-driven PMOS feedforward jointly drive the output
PMOS/NMOS at `net050/net049`. Preserve the original `net063–vout` compensation
and both explicitly added physical capacitor arrays.

Qualification covers 1.2 V, typical IHP LV models at 27 C, both 0.5/0.7 V
DC input points and 5/10/15 pF external loads. Positive and negative 200 mV
steps must sustain 2 mV tracking in the declared windows. See the
[problem](problem.md) for the complete contract.

MOS dimensions are rounded to the 10 nm physical grid. Parallel regrouping
within each original group preserves its rounded total W and L, with at most
10 um single-finger width; individual width/multiplicity and diffusion perimeter
change. Distributed 2 × 2 um body contacts have at most 20 um pitch.
All internal capacitors use `cap_cmim`:

- `c0`: `net063` (top) to `vout` (bottom), 1 parallel 51.3 × 51.3 um MIM units.
- `clocal`: `net050` (top) to `vout` (bottom), 4 parallel 51.64 × 51.64 um MIM units.
- `cout`: `vout` (top) to `vss` (bottom), 12 parallel 51.64 × 51.64 um MIM units.

The raw 10.0474 uA sink is calibrated to 1.255925 uA. The original
3.94789 pF `net063–vout` compensation remains. Approximately 16 pF is added
at `net050–vout` and another 48 pF at `vout–vss`. These are physical
compensation/output-storage devices, included in the netlist, area and
extracted simulation. This maintained circuit is explicitly not capless.
No ideal servo, diagnostic clamp or hidden damping element is part of this DUT.


## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): inputs, physical checks, metrics, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical device graphs.
- [Testbench](materials/testbench.spice): bias, bilateral loop and sustained recovery.
- [Reference layout](reference/amp_015_sau_cfcc.gds): independent physical witness.

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

Measured `layout-v2` score: **45.619118**, with electrical quality
**E = 0.98085989** and area quality **Q = 0.21217137**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **397760.7744 um2**.

Area reference: **84393.45 um2**. 364 expanded device instances; sum of device/contact envelopes 55883.1016 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.50172759 … 0.70175575 | 0.50188431 … 0.70191273 | 0.9998692 |
| `output_error_v` | V | 0.0017275931 … 0.0017557499 | 0.0018843095 … 0.0019127322 | 0.91687498 |
| `bias_v` | V | 0.72715328 … 0.7271535 | 0.72705444 … 0.72705469 | 0.99991764 |
| `power_w` | W | 2.2842247e-05 … 2.2924397e-05 | 2.2917964e-05 … 2.2999347e-05 | 0.99669617 |
| `dc_gain_db` | dB | 93.74538 … 95.57222 | 93.34345 … 95.34078 | 0.95478041 |
| `unity_hz` | Hz | 201599.6 … 203659.9 | 200691.6 … 202861.6 | 0.99549602 |
| `phase_margin_deg` | deg | 97.39206 … 97.82809 | 96.74 … 97.21597 | 0.99634188 |
| `final_unity_hz` | Hz | 201599.6 … 203659.9 | 200691.6 … 202861.6 | 0.99549602 |
| `final_phase_margin_deg` | deg | 97.39206 … 97.82809 | 96.74 … 97.21597 | 0.99634188 |
| `minimum_return_distance` | 1 | 0.66594196 … 0.69266267 | 0.58595981 … 0.62269892 | 0.92594123 |
| `return_phase_excursion_deg` | deg | 89.445706 … 89.502623 | 89.435218 … 89.498314 | 1.0000481 |
| `hf_gain_db` | dB | -71.20634 … -69.26125 | -77.36762 … -69.27791 | 0.98003593 |
| `recovery_up_v` | V | 0.001755749 … 0.001755751 | 0.001912731 … 0.001912738 | 0.91796839 |
| `recovery_down_v` | V | 0.001738622 … 0.001738971 | 0.001895625 … 0.001896033 | 0.9172065 |
| `step_gain` | V/V | 1.0001405 … 1.000141 | 1.000142 | 0.9999985 |
| `mean_power_w` | W | 2.329226e-05 … 2.337913e-05 | 2.337032e-05 … 2.345742e-05 | 0.99665987 |
| `peak_v` | V | 0.7017558 … 0.704205 | 0.7022219 … 0.7060984 | 0.99838827 |
| `trough_v` | V | 0.5017276 | 0.5018843 | 0.99986943 |

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
  --case ihp-sg13g2.analog-db.amp_015_sau_cfcc --image iclayout-bench-tools:local \
  --output build/runs/amp_015_sau_cfcc-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_015_sau_cfcc-prepared \
  --output build/runs/amp_015_sau_cfcc-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_015_sau_cfcc'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [the fixed source snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_015_sau_cfcc).
IHP raw DUT SHA-256: `4a36b71803bfc2a6fb18296c8a24815887837a3f68285bd76c0e18a2417553af`.
Selected raw DUT, manifest, analyses and collection licensing files were checked
against the fixed Git tree. Normalized circuit derivatives and the independent
witness retain PolyForm Noncommercial, Required Notice and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE). The separately authored native measurement deck
is MIT. Component labels do not relicense normalized materials or the witness.
