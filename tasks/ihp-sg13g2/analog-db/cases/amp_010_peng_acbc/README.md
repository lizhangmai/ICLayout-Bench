> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Auxiliary-Branch Compensation OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS/diode/mirror stage
drives `net049`, followed by the NMOS output stage. The output PMOS also
receives feedforward drive from `net050`. C0 connects `net050` to output,
while C1 connects `net049` to `net1`. The auxiliary node has a bias-fed PMOS,
a diode-connected PMOS and an NMOS controlled by `net043`; this three-device
branch creates a distinct active compensation termination. It is neither a
second output-connected Miller capacitor nor the six-MOS current-buffer
branch of the other representative.

The maintained circuit retains all 27 source MOS groups as 237 physical
fingers, 6 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. All source multiplicities are retained.
The maintained 1.80825 uA sink is external through `net013`.
The external bias is deliberately calibrated to 0.1 times the source current; this is not an unchanged upstream operating point. Physical
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
- [Reference layout](reference/amp_010_peng_acbc.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 252948.45 um² and
score is 100. Absolute area anchors are
270000/1080000 um², calibrated against complete independent
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
| `output_v` | V | 0.49902625 | 0.49928499 |
| `bias_v` | V | 0.81169171 | 0.81150661 |
| `power_w` | W | 4.4557631e-05 | 4.4632728e-05 |
| `dc_gain_db` | dB | 90.95124 | 90.99614 |
| `unity_hz` | Hz | 240024.7–244699.6 | 237848–242598.5 |
| `phase_margin_deg` | deg | 87.03286–88.03197 | 86.41132–87.44605 |
| `recovery_up_v` | V | 0.0009865102–0.0009865104 | 0.0007260222 |
| `recovery_down_v` | V | 0.0009737532–0.0009737533 | 0.0007150123 |
| `step_gain` | V/V | 0.9999365 | 0.999945 |
| `mean_power_w` | W | 4.446528e-05–4.44657e-05 | 4.453962e-05–4.454004e-05 |
| `peak_v` | V | 0.6990135 | 0.699274 |
| `trough_v` | V | 0.4990262 | 0.499285 |

The RC audit retains all 243 expanded functional MOS/MIM/poly
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

Halving maximum transient step to 5 ns and separately tightening
reltol/abstol/vntol tenfold, raising rshunt to 1e13 ohm and doubling AC sampling
to 300 points/decade preserve every bound:

- half-step: maximum unity-frequency change 0 Hz, phase-margin change 0 degrees, peak/trough change 0 V and sustained-recovery change 4e-10 V.
- tight: maximum unity-frequency change 13 Hz, phase-margin change 0.00015 degrees, peak/trough change 0 V and sustained-recovery change 1.47e-08 V.

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
  --case amp_010_peng_acbc --image iclayout-bench-tools:local \
  --output build/runs/amp_010_peng_acbc-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_010_peng_acbc-prepared --output build/runs/amp_010_peng_acbc-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_010_peng_acbc
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

case = Path('build/runs/amp_010_peng_acbc-prepared/case/case.toml')
reference = Path('build/runs/amp_010_peng_acbc-reference/reference')
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
        deck = deck.replace('tran 10n 180u 0 10n', 'tran 5n 180u 0 5n')
    if variant == 'tight':
        deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-14 vntol=1e-8',
                            'rshunt=1e13 reltol=1e-6 abstol=1e-15 vntol=1e-9')
        deck = deck.replace('ac dec 150', 'ac dec 300')
    inputs['input:performance'] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('amp_010_peng_acbc-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_010_peng_acbc at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_010_peng_acbc),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
