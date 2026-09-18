> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Output-Controlled Auxiliary Compensation OTA

## Overview

The folded PMOS input stage drives `net050`, which feeds the output PMOS
and a PMOS/diode/NMOS mirror path to `net049`. That node drives the output
NMOS and a separate auxiliary common-source NMOS at `net1`, with a biased
PMOS load. C0 spans `net050`–output and C1 spans `net049`–`net1`.
Unlike AMP007, the auxiliary stage senses the NMOS output control node;
AMP007 senses `net050` with a PMOS and terminates compensation at `net2`.
These different control nodes, active paths and capacitor endpoints establish
the topology distinction; the measurements below establish its finite scope.

All 26 source MOS groups remain. MOS dimensions are rounded to the 10 nm
PyCell grid; integer parallel regrouping reduces 1,413 rounded source fingers
to 675 physical fingers, preserving each group's rounded total W and L.
Individual finger W/m and diffusion perimeter change, with width <=10 um.
The 400-finger PMOS output device remains 400 fingers. Both internal capacitor
branches become complete MIM arrays: eight 48.935 um square C0 devices and
three 50.94 um square C1 devices, approximately 28.74/11.68 pF.
The raw 27.4754 uA sink is explicitly calibrated to an external 6.86885 uA
sink to support the declared headroom and tracking. Internal bias mirrors,
the separate source-tied input well and both compensation branches remain.
Distributed physical 2 x 2 um contacts at <=20 um pitch connect the wells and
substrate. No hidden output servo or internal numerical damping is introduced.

Qualification covers 1.2 V, typical LV models, 27 C, 5/10/20 pF loads,
0.5/0.7 V operating points, bilateral return ratio and finite 0.5↔0.7 V
tracking after approximately 3 us. See the [problem](problem.md) for the
complete interface, measurement definitions, bounds and physical requirements.

## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): declared inputs, checks, limits, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical device graphs.
- [Testbench](materials/testbench.spice): bias, bilateral loop and recovery measurements.
- [Reference layout](reference/amp_006_leung_dfcfc1.gds): independent physical witness.

Only the problem and three materials files enter solver inputs. Collection
licenses and notices accompany distributions separately. Source checkouts,
upstream generators, DSL, witness and qualification answers are excluded.

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

Measured `layout-v2` score: **33.046526**, with electrical quality
**E = 1.0041165** and area quality **Q = 0.10875958**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **762378.1052 um2**.

Area reference: **82915.92 um2**. 1164 expanded device instances; sum of device/contact envelopes 54901.4182 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.50281187 … 0.70297998 | 0.50371133 … 0.70393283 | 0.99920658 |
| `output_error_v` | V | 0.0028118651 … 0.0029799754 | 0.0037113258 … 0.0039328301 | 0.75770964 |
| `bias_v` | V | 0.66852399 … 0.66852442 | 0.6608879 … 0.66088822 | 0.99367674 |
| `power_w` | W | 0.00011971951 … 0.00012011829 | 0.00012235452 … 0.00012300756 | 0.9765115 |
| `dc_gain_db` | dB | 95.37677 … 98.19628 | 95.73468 … 98.37732 | 1.0210617 |
| `unity_hz` | Hz | 546056.4 … 574201.7 | 589380.8 … 637743.1 | 1.0793405 |
| `phase_margin_deg` | deg | 80.55115 … 81.93171 | 81.84918 … 83.56516 | 0.99081171 |
| `final_unity_hz` | Hz | 546056.4 … 574201.7 | 589380.8 … 637743.1 | 1.0793405 |
| `final_phase_margin_deg` | deg | 80.55115 … 81.93171 | 81.84918 … 83.56516 | 0.99081171 |
| `minimum_return_distance` | 1 | 0.8047943 … 0.84772962 | 0.73858463 … 0.75198343 | 0.9106222 |
| `return_phase_excursion_deg` | deg | 89.556499 … 89.622004 | 89.553024 … 89.616259 | 1.0000353 |
| `hf_gain_db` | dB | -50.95392 … -43.18098 | -71.62955 … -63.85617 | 8.940751 |
| `recovery_up_v` | V | 0.002978925 … 0.002978926 | 0.003932828 | 0.75751278 |
| `recovery_down_v` | V | 0.002831263 … 0.002837292 | 0.003730838 … 0.003735368 | 0.75894586 |
| `step_gain` | V/V | 1.00084 | 1.0011075 | 0.99973257 |
| `mean_power_w` | W | 0.0001198889 … 0.0001198912 | 0.0001226652 … 0.0001226677 | 0.97736568 |
| `peak_v` | V | 0.7029789 | 0.7039328 | 0.99920571 |
| `trough_v` | V | 0.5028109 | 0.5037113 | 0.99925023 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 8 reflects coupled multistage auxiliary compensation, loaded
bilateral response and sustained recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_006_leung_dfcfc1 --image iclayout-bench-tools:local \
  --output build/runs/amp_006_leung_dfcfc1-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_006_leung_dfcfc1-prepared \
  --output build/runs/amp_006_leung_dfcfc1-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_006_leung_dfcfc1'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [AMP006 at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_006_leung_dfcfc1).
The IHP raw DUT SHA-256 is
`74f446ca092d50f5ef367d1987db3985eafc5d8fd3587a0cc7eeb6f748b35131`.
Selected raw DUT, manifest, analyses and collection licensing files were
checked against the fixed Git tree. The normalized circuit derivatives and
independent witness retain PolyForm Noncommercial, the Required Notice and
recorded CODA-Team AnalogGym BSD-3-Clause component terms in collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). The separately authored
native measurement deck is MIT. Component manifest labels do not relicense
normalized materials or the independent witness MIT.
