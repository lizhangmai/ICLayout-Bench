> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Dual-Capacitor Three-Stage OTA

## Overview

The folded PMOS-input stage drives `net050`; a PMOS stage at `net043`
and its NMOS mirror drive `net049`, which controls the NMOS output device.
A parallel feedforward path drives the output PMOS directly from `net050`.
Two capacitive paths connect `net050` to output and `net049` to output.
These couple two internal gain nodes to the load, unlike the maintained
two-stage OTA's single Miller path.

The maintained circuit retains all 24 source MOS groups as 236 physical
fingers, 3 MIM units and 0 high-poly segments. MOS W/L are rounded to the nearest 0.01 um process grid. All source multiplicities are retained.
The source's 7.52942 uA sink is external through `net013`. Physical
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
- [Reference layout](reference/amp_008_leung_nmcf.gds): independently constructed witness.

Only the problem and three materials files enter solver inputs; collection
licenses/notices accompany distributions separately. No upstream generator,
layout, DSL, tuning history or scoreboard is needed.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 194584.21 um² and
score is 100. Absolute area anchors are
200000/800000 um², calibrated against complete independent
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
| `output_v` | V | 0.49907771 | 0.49981547 |
| `bias_v` | V | 0.72175232 | 0.72096044 |
| `power_w` | W | 0.00019054529 | 0.00019177013 |
| `dc_gain_db` | dB | 83.75325 | 88.3934 |
| `unity_hz` | Hz | 2793689–3046550 | 2744138–2989930 |
| `phase_margin_deg` | deg | 56.8138–66.4509 | 51.6184–62.1753 |
| `recovery_up_v` | V | 0.0003963888–0.0003963889 | 0.0005150447 |
| `recovery_down_v` | V | 0.0009222942–0.0009222943 | 0.0001845324 |
| `step_gain` | V/V | 1.0026295 | 1.0034975 |
| `mean_power_w` | W | 0.0001865652–0.0001865916 | 0.0001876508–0.0001876788 |
| `peak_v` | V | 0.700899–0.7059239 | 0.7057017–0.7157009 |
| `trough_v` | V | 0.4882809–0.495909 | 0.4806747–0.4939142 |

The RC audit retains all 239 expanded functional MOS/MIM/poly
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

- half-step: maximum unity-frequency change 0 Hz, phase-margin change 0 degrees, peak/trough change 3.22e-05 V and sustained-recovery change 1e-10 V.
- tight: maximum unity-frequency change 58 Hz, phase-margin change 0.0006 degrees, peak/trough change 1.6e-05 V and sustained-recovery change 1.74e-08 V.

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
  --case amp_008_leung_nmcf --image iclayout-bench-tools:local \
  --output build/runs/amp_008_leung_nmcf-prepared
python -m layout_eval.preview run \
  --prepared build/runs/amp_008_leung_nmcf-prepared --output build/runs/amp_008_leung_nmcf-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_008_leung_nmcf
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

case = Path('build/runs/amp_008_leung_nmcf-prepared/case/case.toml')
reference = Path('build/runs/amp_008_leung_nmcf-reference/reference')
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
        inputs, load_toolchain(case), Path('build/runs') / ('amp_008_leung_nmcf-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_008_leung_nmcf at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_008_leung_nmcf),
with PolyForm Noncommercial normalized-material terms and recorded CODA-Team
AnalogGym BSD-3-Clause component terms in the collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE); the independently authored measurement deck is MIT.
