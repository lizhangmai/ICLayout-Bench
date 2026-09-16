> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Series-Nulling-Resistor Two-Stage OTA

## Overview

A PMOS-input two-stage amplifier with physical series nulling resistance in its
Miller compensation path. The maintained circuit retains all eight source MOS
groups' W/L/m (27 individual MOS), externalizes the 100 nA bias sink through
`ibias`, and adds explicit substrate/well contacts. Two parallel 25.85 × 25.85 um
MIM units provide nominally 2.01294 pF. Four W=1 um, L=18 um `rhigh` segments
provide a nominal 102.64 kohm series chain at 27 C with the declared model.
The circuit uses physical devices for the source's ideal 2 pF / 100 kohm path.

Qualification covers 1.2 V, 27 C, typical models, 5/10/20 pF external loads,
loop gain about 0.5 V unity-feedback bias, and 0.5↔0.7 V finite-step recovery.
The 20 pF condition has approximately 44.7 degrees phase margin and 70 mV
positive overshoot; this is not a monotonic-response or arbitrary-load claim.
The series compensation adds a physical device and interstage parasitic path
to the direct-MIM two-stage topology. Noise, distortion, PVT, mismatch,
startup from zero supply and fabrication signoff are outside this qualification.

## Files

- [Problem](problem.md): complete solver contract, limits and scoring.
- [Configuration](case.toml): frozen task, tool bindings and reference identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice):
  matching physical device definitions with their native reader syntax.
- [Testbench](materials/testbench.spice): bias, return ratio and step measurements.
- [Reference layout](reference/amp_024_smcnr.gds): independently constructed witness.

Only the problem and three materials files are solver inputs. Collection
licenses/notices accompany distributions separately from solver materialization.
No upstream layout, generator, DSL, tuning history or scoreboard is required.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC extraction and all electrical bounds.
Its functional bounding-box area is 36886.7985000 um², with a score of 100. Absolute
area anchors are 38000/152000 um²: the target accommodates the independently
constructed 27-MOS witness, two MIM units, four poly segments, taps and complete
routing. They remain fixed when a witness changes. Coefficient 7 reflects the
coupled compensation, stability and closed-loop response requirements.

The table reports ranges across 5/10/20 pF; identical values are shown once.
Power is VDD-supplied power, including the on-chip bias mirror but excluding
external bias-generator overhead. See the problem for every window and limit.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.4999089 | 0.4999116 |
| `bias_v` | V | 0.5897282 | 0.5896805 |
| `power_w` | W | 1.55793e-06 | 1.558008e-06 |
| `dc_gain_db` | dB | 69.28808 | 69.2781 |
| `unity_hz` | Hz | 123342.7–165259.3 | 122410.5–164094.7 |
| `phase_margin_deg` | deg | 45.1515–71.4584 | 44.7027–70.6319 |
| `recovery_up_v` | V | 6.292729e-05–6.619118e-05 | 6.637928e-05–7.018053e-05 |
| `recovery_down_v` | V | 9.112525e-05–9.129919e-05 | 8.836365e-05–8.857658e-05 |
| `step_gain` | V/V | 1.00077 | 1.000774 |
| `mean_power_w` | W | 1.532992e-06–1.533232e-06 | 1.533066e-06–1.533308e-06 |
| `peak_v` | V | 0.7012933–0.769071 | 0.7021363–0.7699192 |
| `trough_v` | V | 0.4816025–0.4997009 | 0.4808844–0.4994896 |

Post-layout unity frequencies are 164.095/148.157/122.411 kHz and phase margins
70.632/58.142/44.703 degrees in load order. Recovery is maximum absolute
tracking error over sustained windows approximately 30 us after each edge,
not the first crossing of a tolerance band. The peak/trough bounds separately
limit the intervening excursion.

The candidate RC graph retains all 27 MOS, two physical MIM units and four
physical resistor segments. Removing only parasitic capacitors, collapsing
interconnect resistors and applying the declared ideal-tap boundary yields
the source device graph with distinct supply and return. Native LVS additionally
checks physical taps and device dimensions. Magic idealizes well/substrate
ties; source simulation retains finite tap models. Distributed substrate
resistance/noise is unqualified. The `analog-res-models` resource profile adds
the already pinned R3_CMC OSDI resistor model to MOS/MIM support; it changes no
runner, scorer, extraction rule or existing case profile.

At all three loads, halving maximum transient step from 50 to 25 ns changes
peak/trough by at most 26 uV and the recovery-window error by less than 0.04 uV.
A separate check tightens reltol/abstol/vntol tenfold, raises the numerical
shunt from 1e12 to 1e13 ohm, and doubles AC sampling to 300 points/decade.
It changes unity frequency by less than 0.02%, phase margin by less than
0.002 degrees, DC output by less than 3 uV and recovery error by less than
4 uV. Every declared bound remains satisfied. These checks establish this
measurement scope, not universal numerical accuracy.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Run from the repository root with the [shared tool setup](../../../../../docs/tools.md#manual-tools).
Reuse verified bundles or prepare them in new destinations. The new combined
model profile is required for physical high-poly resistance:

```bash
python -m layout_eval.preview prepare \
  --case amp_024_smcnr --image iclayout-bench-tools:local \
  --output build/runs/smcnr-prepared
python -m layout_eval.preview run \
  --prepared build/runs/smcnr-prepared --output build/runs/smcnr-reference
```

Preview preparation assembles all declared profiles, including the combined
resistor model support. These commands create
the reader's own reports, extraction and waveforms, rather than retrieving a
maintainer run directory. Use fresh output paths. Reference/empty-layout regression:

```bash
python -m pytest tests/integration/test_public_references.py \
  -k amp_024_smcnr
```

After the preview reference run, the following reproduces source calibration
and the two numerical checks using its frozen inputs, prepared models and
candidate RC. It does not alter the scored case. Each characterization retains
all three loads and acceptance bounds.

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

case = Path('build/runs/smcnr-prepared/case/case.toml')
reference = Path('build/runs/smcnr-reference/reference')
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
        deck = deck.replace('tran 50n 180u 0 50n', 'tran 25n 180u 0 25n')
    if variant == 'tight':
        deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-14 vntol=1e-8',
                            'rshunt=1e13 reltol=1e-6 abstol=1e-15 vntol=1e-9')
        deck = deck.replace('ac dec 150', 'ac dec 300')
    inputs['input:performance'] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('smcnr-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_024_smcnr at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_024_smcnr),
with PolyForm Noncommercial normalized-material terms and the attributed
CODA-Team AnalogGym BSD-3-Clause component terms retained in the collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE); the independently authored
measurement deck is MIT.
