> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Shared-Nulling-Resistor Three-Stage OTA

## Overview

The folded PMOS-input stage drives `net050`; the PMOS stage at `net043`
and its NMOS mirror drive `net049`, which controls the NMOS output device.
The output PMOS gate connects to the bias mirror, not to `net050`.
Two capacitors connect `net050` and `net049` to a common `net044` node;
a physical high-poly resistor connects that junction to output. The shared
resistance and bias-controlled output PMOS distinguish this circuit from
both the dual-capacitor feedforward OTA and the two-stage series-R/C OTA.

The maintained circuit retains all 24 source MOS groups as 272 physical
fingers, 3 MIM units and 1 high-poly segments. All MOS dimensions/multiplicities are retained exactly.
The source's 3 uA sink is external through `net013`. Physical
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
- [Reference layout](reference/amp_009_leung_nmcnr.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 617432.43 um² and
score is 100. Absolute area anchors are
650000/2600000 um², calibrated against complete independent
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
| `output_v` | V | 0.49966042 | 0.50017676 |
| `bias_v` | V | 0.73769917 | 0.73722016 |
| `power_w` | W | 7.5986653e-05 | 7.6261598e-05 |
| `dc_gain_db` | dB | 91.90065 | 92.57493 |
| `unity_hz` | Hz | 1236878–1433315 | 1306310–1620232 |
| `phase_margin_deg` | deg | 82.00337–90.51311 | 66.998–84.14817 |
| `recovery_up_v` | V | 0.0008626829 | 0.001596237 |
| `recovery_down_v` | V | 0.000339583 | 0.0001767645–0.0001768096 |
| `step_gain` | V/V | 1.0060115 | 1.007097 |
| `mean_power_w` | W | 7.483076e-05–7.484843e-05 | 7.507405e-05–7.510323e-05 |
| `peak_v` | V | 0.7008627–0.7099745 | 0.7015962–0.7886517 |
| `trough_v` | V | 0.4965633–0.4993272 | 0.4869953–0.4993051 |

The RC audit retains all 276 expanded functional MOS/MIM/poly
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

Halving maximum transient step to 1 ns and separately tightening
reltol/abstol/vntol tenfold, raising rshunt to 1e13 ohm and doubling AC sampling
to 300 points/decade preserve every bound:

- half-step: maximum unity-frequency change 0 Hz, phase-margin change 0 degrees, peak/trough change 1.46e-05 V and sustained-recovery change 4e-10 V.
- tight: maximum unity-frequency change 65 Hz, phase-margin change 0.00098 degrees, peak/trough change 8.11e-05 V and sustained-recovery change 1.395e-07 V.

Qualification is limited to the declared loads, bias, signal levels and
measurement windows. It is not a noise, distortion, PVT, mismatch, startup,
rail-to-rail or arbitrary-load stability claim.

At 20 pF, the extracted positive peak is about 0.789 V despite a phase
margin near 67 degrees. The declared peak bound permits this measured overshoot;
monotonic recovery is not claimed.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Use the [shared tools](../../../../../docs/tools.md#manual-tools) from the
repository root. The following commands generate the reader's own reports;
use fresh output directories and reuse verified resources where available.

```bash
python -m layout_eval.preview prepare \
  --case amp_009_leung_nmcnr --image iclayout-bench-tools:local \
  --output build/runs/amp_009_leung_nmcnr-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_009_leung_nmcnr-prepared --output build/runs/amp_009_leung_nmcnr-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_009_leung_nmcnr
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

case = Path('build/runs/amp_009_leung_nmcnr-prepared/case/case.toml')
reference = Path('build/runs/amp_009_leung_nmcnr-reference/reference')
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
        inputs, load_toolchain(case), Path('build/runs') / ('amp_009_leung_nmcnr-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_009_leung_nmcnr at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_009_leung_nmcnr),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
