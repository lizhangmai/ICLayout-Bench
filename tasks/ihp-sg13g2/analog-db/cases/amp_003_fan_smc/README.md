> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Single-Capacitor Three-Stage Feedforward OTA

## Overview

The folded PMOS-input stage drives `net050`; the PMOS stage at `net043`
and its NMOS mirror drive `net049`, which controls the NMOS output device.
An active feedforward path drives the output PMOS directly from `net050`.
A single physical capacitor branch connects `net050` to output. This is the
single-capacitor representative: there is no second `net049` capacitor or
series nulling resistor. The large retained mirror multiplicities and coupled
three-stage/feedforward paths require their own loaded recovery calibration.

The maintained circuit retains all 24 source MOS groups as 412 physical
fingers, 2 MIM units and 0 high-poly segments. All MOS dimensions/multiplicities are retained exactly.
The maintained 3 uA sink is external through `net013`.
The source value was 60 uA; the maintained 3 uA bias is a deliberate headroom calibration, not an unchanged upstream operating point. Physical
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
- [Reference layout](reference/amp_003_fan_smc.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 307375.73 um² and
score is 100. Absolute area anchors are
320000/1280000 um², calibrated against complete independent
placement, routing, physical passives and separate well/substrate contacts.
They are fixed absolute budgets, not ratios to a changing witness. Coefficient
7 reflects coupled multistage compensation, loaded loop response and recovery.
This reference is a feasibility witness, not an area optimum.

Ranges below cover all 5/10/20 pF conditions. Source simulation uses the
maintained rounded/fingered circuit and finite tap models; Post-layout uses
the submitted GDS-derived RC. Power includes the on-chip bias network and
excludes external bias-generator overhead. It does not credit bias-sink energy
as recovered power. See the problem for every measurement window and bound.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.49935918 | 0.49996489 |
| `bias_v` | V | 0.82080801 | 0.81960251 |
| `power_w` | W | 5.4973186e-05 | 5.575258e-05 |
| `dc_gain_db` | dB | 95.33123 | 95.35406 |
| `unity_hz` | Hz | 1369789–1383658 | 1416461–1485272 |
| `phase_margin_deg` | deg | 85.30559–86.9872 | 76.4297–79.2516 |
| `recovery_up_v` | V | 0.0009181133–0.000918114 | 0.0001642943–0.0002066184 |
| `recovery_down_v` | V | 0.0006408193–0.0006408194 | 3.511185e-05–0.000726515 |
| `step_gain` | V/V | 0.9986135 | 0.999353–0.999354 |
| `mean_power_w` | W | 5.414429e-05–5.427551e-05 | 5.486363e-05–5.502446e-05 |
| `peak_v` | V | 0.6990819 | 0.6998357–0.7328612 |
| `trough_v` | V | 0.4993592 | 0.489406–0.4999641 |

The RC audit retains all 414 expanded functional MOS/MIM/poly
devices. After collapsing only interconnect resistors and applying Magic's
ideal-tap boundary, an independent terminal-role graph comparison uniquely
maps 18 nets to the source; capacitor top/bottom plates and
input source-tied wells remain distinct. Native LVS separately checks device
dimensions and finite physical contacts. This does not establish a distributed
substrate model or fabrication signoff.

Saved-waveform recomputation checks 144 observations across source,
reference and numerical variants, including sustained recovery maxima and
trapezoidal mean power. Each AC sweep has exactly one unity crossing, with
continuous phase starting near zero. Phase margin and finite-step recovery are
separate observations; neither substitutes for the other.

Halving maximum transient step to 1 ns and separately tightening
reltol/abstol/vntol tenfold, raising rshunt to 1e13 ohm and doubling AC sampling
to 300 points/decade preserve every bound:

- half-step: maximum unity-frequency change 0 Hz, phase-margin change 0 degrees, peak/trough change 3.28e-05 V and sustained-recovery change 3.111e-07 V.
- tight: maximum unity-frequency change 122 Hz, phase-margin change 0.0002 degrees, peak/trough change 1.85e-05 V and sustained-recovery change 1.2498e-06 V.

Qualification is limited to the declared loads, bias, signal levels and
measurement windows. It is not a noise, distortion, PVT, mismatch, startup,
rail-to-rail or arbitrary-load stability claim.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Use the [shared tools](../../../../../docs/tools.md#manual-tools) from the
repository root. The following commands generate the reader's own reports;
use fresh output directories and reuse verified resources where available.

```bash
python -m layout_eval.preview prepare \
  --case amp_003_fan_smc --image iclayout-bench-tools:local \
  --output build/runs/amp_003_fan_smc-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_003_fan_smc-prepared --output build/runs/amp_003_fan_smc-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_003_fan_smc
```

After the preview run, reproduce source calibration and numerical checks with
its frozen inputs, models and candidate RC. These commands create new local
reports under `build/runs/`; no maintainer run directory is needed. Keep the
acceptance bounds unchanged.

```bash
uv run --locked python - <<'PYCODE'
import copy
import json
import tomllib
from pathlib import Path
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.files import Asset

case = Path('build/runs/amp_003_fan_smc-prepared/case/case.toml')
reference = Path('build/runs/amp_003_fan_smc-reference/reference')
task = load_task(case)
report = json.loads((reference / 'report.json').read_text())
assert report['task_success']
rc = Asset((reference / report['jobs']['parasitics']['outputs']['netlist']['path']).read_bytes(), 'spice')
base = tomllib.loads(case.read_text())['task']['evaluation']
for variant in ('source', 'half-step', 'tight'):
    plan = copy.deepcopy(base)
    plan['mode'] = 'characterization'
    plan.pop('scoring')
    plan['jobs'] = [j for j in plan['jobs'] if j['stage'] == 'simulate']
    for job in plan['jobs']:
        job['inputs']['dut'] = 'input:simulation'
    plan['metrics'] = [m for m in plan['metrics'] if m['category'] == 'performance']
    for metric in plan['metrics']:
        for key in ('dimension', 'zero_lower', 'zero_upper'):
            metric.pop(key, None)
    inputs = task.evaluation_inputs()
    if variant != 'source':
        inputs['input:simulation'] = rc
    deck = inputs['input:performance'].content.decode()
    if variant == 'half-step':
        deck = deck.replace('tran 2n 18u 0 2n', 'tran 1n 18u 0 1n')
    if variant == 'tight':
        deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-14 vntol=1e-8',
                            'rshunt=1e13 reltol=1e-6 abstol=1e-15 vntol=1e-9')
        deck = deck.replace('ac dec 150', 'ac dec 300')
    inputs['input:performance'] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('amp_003_fan_smc-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_003_fan_smc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_003_fan_smc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
