> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Current-Buffer and Active-Feedforward OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS common-source stage
drives `net013`, then a PMOS stage and NMOS mirror at `net043` drive the
output NMOS. An active feedforward path drives the output PMOS directly
from `net050`. One capacitor connects output to `net063`, the source side
of the first-stage NMOS cascode; the second connects `net050` to `net013`.
The current-buffer compensation terminal and the additional active path
are real connection differences from the dual-capacitor and shared-resistor
representatives. This case is not counted from a changed circuit name or size.

The maintained circuit retains all 24 source MOS groups as 89 physical
fingers, 4 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. The original W=18/20/30 um devices use 2×9/2×10/3×10 um parallel fingers; the resulting short-width model behavior is calibrated independently.
The source's 14.3293 uA sink is external through `net1`. Physical
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
- [Reference layout](reference/amp_002_alfio_raffc.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 154727.08 um² and
score is 100. Absolute area anchors are
160000/640000 um², calibrated against complete independent
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
| `output_v` | V | 0.49954682 | 0.50059203 |
| `bias_v` | V | 0.23269814 | 0.23217762 |
| `power_w` | W | 0.0004119832 | 0.00041444626 |
| `dc_gain_db` | dB | 93.72582 | 82.33763 |
| `unity_hz` | Hz | 1884332–1910778 | 1881988–1916285 |
| `phase_margin_deg` | deg | 73.7404–79.3754 | 74.3891–80.16008 |
| `recovery_up_v` | V | 0.0004710615–0.0004710616 | 0.001479954 |
| `recovery_down_v` | V | 0.0004531763 | 0.0005920302 |
| `step_gain` | V/V | 0.9999105 | 1.00444 |
| `mean_power_w` | W | 0.0004069606–0.0004069685 | 0.0004094146–0.000409421 |
| `peak_v` | V | 0.6995289 | 0.70148 |
| `trough_v` | V | 0.4994566–0.4995032 | 0.5005453–0.500567 |

The RC audit retains all 93 expanded functional MOS/MIM/poly
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

- half-step: maximum unity-frequency change 0 Hz, phase-margin change 0 degrees, peak/trough change 0 V and sustained-recovery change 0 V.
- tight: maximum unity-frequency change 44 Hz, phase-margin change 0.0003 degrees, peak/trough change 2e-07 V and sustained-recovery change 2.6e-07 V.

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
  --case amp_002_alfio_raffc --image iclayout-bench-tools:local \
  --output build/runs/amp_002_alfio_raffc-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_002_alfio_raffc-prepared --output build/runs/amp_002_alfio_raffc-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_002_alfio_raffc
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

case = Path('build/runs/amp_002_alfio_raffc-prepared/case/case.toml')
reference = Path('build/runs/amp_002_alfio_raffc-reference/reference')
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
        inputs, load_toolchain(case), Path('build/runs') / ('amp_002_alfio_raffc-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_002_alfio_raffc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_002_alfio_raffc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
