> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

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

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 421629.05 um² and
score is 100. Absolute area anchors are
450000/1800000 um², calibrated against complete independent
placement, routing, physical passives and separate well/substrate contacts.
They are fixed absolute budgets, not ratios to a changing witness. Coefficient
8 reflects coupled multistage compensation, loaded loop response and recovery.
This reference is a feasibility witness, not an area optimum.

Ranges below cover all 5/10/20 pF conditions. Source simulation uses the
maintained rounded/fingered circuit and finite tap models; Post-layout uses
the submitted GDS-derived RC. Power includes the on-chip bias network and
excludes external bias-generator overhead. It does not credit bias-sink energy
as recovered power. See the problem for every measurement window and bound.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.50020624 | 0.49838005 |
| `bias_v` | V | 0.51960454 | 0.51781963 |
| `power_w` | W | 0.00029095025 | 0.00029399612 |
| `dc_gain_db` | dB | 87.05805 | 85.20933 |
| `unity_hz` | Hz | 2332575–2459231 | 2214842–2305191 |
| `phase_margin_deg` | deg | 76.0765–80.58622 | 71.6659–77.3958 |
| `recovery_up_v` | V | 0.001051429–0.001052217 | 0.0008262498–0.000826251 |
| `recovery_down_v` | V | 0.0002062373 | 0.001619949 |
| `step_gain` | V/V | 1.004226 | 1.0122305 |
| `mean_power_w` | W | 0.0002890905–0.000289376 | 0.0002917132–0.0002920033 |
| `peak_v` | V | 0.7062702–0.7179188 | 0.7067788–0.7301588 |
| `trough_v` | V | 0.4987494–0.4994512 | 0.4971434–0.4978274 |

The RC audit retains all 450 expanded functional MOS/MIM/poly
devices. After collapsing only interconnect resistors and applying Magic's
ideal-tap boundary, an independent terminal-role graph comparison uniquely
maps 19 nets to the source; capacitor top/bottom plates and
input source-tied wells remain distinct. Native LVS separately checks device
dimensions and finite physical contacts. This does not establish a distributed
substrate model or fabrication signoff.

Saved-waveform recomputation checks 144 observations across source,
reference and numerical variants, including sustained recovery maxima and
trapezoidal mean power. Each AC sweep has exactly one unity crossing, with
continuous phase starting near zero. Phase margin and finite-step recovery are
separate observations; neither substitutes for the other.

The maintained deck explicitly uses `itl4=1000` for transient nonlinear
iterations. The default ceiling can abort the 20 pF source transient, including
with a smaller maximum step. Increasing this iteration ceiling retains device
models, accuracy tolerances and acceptance bounds. The numerical checks below
retain the same ceiling and test both time resolution and tighter accuracy.

Halving maximum transient step to 1 ns and separately tightening
reltol/abstol/vntol tenfold, raising rshunt to 1e13 ohm and doubling AC sampling
to 300 points/decade preserve every bound:

- half-step: maximum unity-frequency change 0 Hz, phase-margin change 0 degrees, peak/trough change 1.62e-05 V and sustained-recovery change 1e-10 V.
- tight: maximum unity-frequency change 50 Hz, phase-margin change 0.0003 degrees, peak/trough change 8.4e-06 V and sustained-recovery change 1.146e-07 V.

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
  --case amp_007_leung_dfcfc2 --image iclayout-bench-tools:local \
  --output build/runs/amp_007_leung_dfcfc2-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_007_leung_dfcfc2-prepared --output build/runs/amp_007_leung_dfcfc2-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_007_leung_dfcfc2
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

case = Path('build/runs/amp_007_leung_dfcfc2-prepared/case/case.toml')
reference = Path('build/runs/amp_007_leung_dfcfc2-reference/reference')
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
        inputs, load_toolchain(case), Path('build/runs') / ('amp_007_leung_dfcfc2-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_007_leung_dfcfc2 at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_007_leung_dfcfc2),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
