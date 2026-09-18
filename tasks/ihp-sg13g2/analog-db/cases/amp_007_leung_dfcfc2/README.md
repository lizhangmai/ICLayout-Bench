> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Auxiliary-Stage Miller Compensation OTA

## Overview

The folded PMOS-input stage drives `net050`; the PMOS/diode/mirror path
drives `net049` and then the NMOS output stage. Direct feedforward drives
the output PMOS from `net050`. A separate PMOS common-source branch has
gate `net050`, drain `net2` and an NMOS bias sink. C1 connects `net050` to
output; C2 connects `net050` to `net2`, across the auxiliary stage. This
compensation branch is distinct from output-to-current-buffer injection and
from the `net049`-controlled auxiliary termination in the other cases.

The maintained circuit retains all 26 source MOS groups as 440 physical
fingers, 10 MIM units and 0 high-poly segments. All MOS dimensions/multiplicities are retained exactly.
The maintained 20 uA sink is external through `net1`.
The source bias-current value is retained. Physical
substrate and separate N-well contacts retain the input PMOS bodies at their
common source `net31`, electrically separate from the VDD well. No internal
ideal bias source or output servo is introduced. Capacitor values are rounded
to physical geometry; every branch remains internal to the DUT.

Qualification covers 1.2 V, 27 C, 5/10/20 pF loads, return ratio around
0.5 V unity feedback and 0.5↔0.7 V step recovery. See the
[problem](problem.md) for all bounds and limitations.

## Files

- [Problem](problem.md): complete solver contract.
- [Configuration](case.toml): inputs, limits, score, backend bindings and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching device graphs.
- [Testbench](materials/testbench.spice): source/RC measurement deck.
- [Reference layout](reference/amp_007_leung_dfcfc2.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

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

Measured `layout-v2` score: **33.771965**, with electrical quality
**E = 0.91137579** and area quality **Q = 0.12514548**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **421629.048 um2**.

Area reference: **52764.97 um2**. 453 expanded device instances; sum of device/contact envelopes 34876.8788 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.50020624 | 0.49838005 | 0.99848049 |
| `bias_v` | V | 0.51960454 | 0.51781963 | 0.99851479 |
| `power_w` | W | 0.00029095025 | 0.00029399612 | 0.98963975 |
| `dc_gain_db` | dB | 87.05805 | 85.20933 | 0.80828403 |
| `unity_hz` | Hz | 2332575 … 2459231 | 2214842 … 2305191 | 0.93736253 |
| `phase_margin_deg` | deg | 76.0765 … 80.58622 | 71.6659 … 77.3958 | 0.97608272 |
| `recovery_up_v` | V | 0.001051429 … 0.001052217 | 0.0008262498 … 0.0008262511 | 1.2722022 |
| `recovery_down_v` | V | 0.0002062373 | 0.001619949 | 0.12784936 |
| `step_gain` | V/V | 1.004226 | 1.0122305 | 0.99205906 |
| `mean_power_w` | W | 0.0002890905 … 0.000289376 | 0.0002917132 … 0.0002920033 | 0.9910025 |
| `peak_v` | V | 0.7062702 … 0.7179188 | 0.7067788 … 0.7301588 | 0.98990299 |
| `trough_v` | V | 0.4987494 … 0.4994512 | 0.4971434 … 0.4978274 | 0.99864866 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient
8 reflects coupled multistage compensation, loaded loop response and recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.amp_007_leung_dfcfc2 --image iclayout-bench-tools:local \
  --output build/runs/amp_007_leung_dfcfc2-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/amp_007_leung_dfcfc2-prepared \
  --output build/runs/amp_007_leung_dfcfc2-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'amp_007_leung_dfcfc2'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db amp_007_leung_dfcfc2 at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_007_leung_dfcfc2),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
