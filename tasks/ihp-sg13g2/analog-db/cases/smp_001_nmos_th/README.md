> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Physical NMOS Sample-and-Hold: Headroom and Retention

## Overview

A single W=2 um / L=0.13 um NMOS samples onto one physical 18.2 × 18.2 um
MIM capacitor, nominally 499.772 fF. The maintained circuit retains the source
switch and all storage connectivity, adds an explicit substrate tap and removes
the raw VDD port because it has no electrical connection. The ordered interface
is `vin clk vout vss`; clock drive is external. No output buffer, dummy
compensation, complementary switch, ideal hold capacitor or hold-node servo is
added. The independently routed reference includes the actual MIM plates.

Qualification covers sampled levels 0.1/0.4/0.6/0.7 V at TT, 27/85 C,
1.2 V clock amplitude with 2 ns edges and 1 kohm source resistance. At each
point the input is driven to 0 or 1.2 V while the switch is off: sixteen
conditions. The contract measures sustained acquisition, turn-off pedestal,
isolated-input feedthrough, quiet 10 us hold drift, total stored-value error
and reacquisition. This adds physical storage and input/temperature-dependent
retention to the existing dummy-compensated track-switch case.

These sample points do not establish rail-to-rail operation or an exact maximum
input voltage. Higher inputs and longer holds expose substantial errors in the
published diagnostic recipe. This is model-based retention for a specified
sequence, not precision ADC resolution or measured-silicon leakage validation.
Noise, jitter, distortion, process corners, mismatch and arbitrary clock/source
conditions remain outside qualification. The MIM model's presence does not
validate capacitor dielectric leakage or distributed substrate noise.

## Files

- [Problem](problem.md): complete circuit, sequence, measurement and scoring contract.
- [Configuration](case.toml): frozen inputs, tool bindings and witness identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): equivalent physical-device definitions for the native readers.
- [Testbench](materials/testbench.spice): finite acquisition/hold/reacquisition with off-state input disturbances.
- [Reference layout](reference/smp_001_nmos_th.gds): independently constructed NMOS, MIM, tap and complete routing.

Only the problem and three materials files enter solver inputs. Collection
LICENSE and NOTICE remain with material distributions separately. Source
layouts, generators, DSL and upstream scoring are not runtime dependencies.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
bounding-box area is 1286.082 um²; score is 100. Fixed absolute area anchors
1400/5600 um² accommodate the physical capacitor, switch, tap and full routing.
Coefficient 5 reflects a complete compact loaded block operating through
acquisition, storage and reacquisition, independently of device count.

The table reports all sixteen conditions. All voltages are uncorrected; signed
point differences are diagnostic, while absolute errors and peak excursions
have the bounds specified in the problem. Clock energy counts positive
supplied energy for the finite high/low/high sequence, without recovery credit;
it excludes initial DC charging, signal-driver energy and physical clock-driver
overhead. There is no connected DUT VDD port or invented supply-power metric.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `track_error_v` | V | 2.690636e-09–0.001026075 | 2.713107e-09–0.00113599 |
| `pedestal_abs_v` | V | 0.0028763–0.00376907 | 0.0067678–0.00750121 |
| `feedthrough_peak_v` | V | 8.031927e-08–5.496746e-05 | 4.369318e-05–0.0004745488 |
| `hold_drift_v` | V | 1.2e-06–0.0115981 | 1.1e-06–0.0112294 |
| `hold_error_v` | V | 0.002883985–0.01517136 | 0.006769885–0.01896994 |
| `reacquire_error_v` | V | 1.176898e-09–4.669633e-06 | 1.200642e-09–5.395874e-06 |
| `clock_energy_j` | J | 1.86907e-15–2.57894e-15 | 7.18973e-15–7.90125e-15 |
| `target` | V | 0.1–0.7 | 0.1–0.7 |
| `track_v` | V | 0.1–0.7 | 0.1–0.7 |
| `held_v` | V | 0.09623093–0.6971237 | 0.09249879–0.6932302 |
| `before_input_v` | V | 0.09623096–0.6971235 | 0.09249884–0.6932301 |
| `after_input_v` | V | 0.09622947–0.6971235 | 0.09245509–0.6934418 |
| `hold_start_v` | V | 0.09601923–0.6971229 | 0.09228863–0.6934415 |
| `hold_end_v` | V | 0.09163936–0.697116 | 0.08809035–0.693436 |
| `reacquired_v` | V | 0.1–0.7 | 0.1–0.7 |
| `pedestal_v` | V | -0.00376907–-0.0028763 | -0.00750121–-0.0067678 |
| `feedthrough_v` | V | -5.63e-05–5.86e-06 | -0.0003508–0.00047174 |
| `drift_v` | V | -0.0115981–0.00116347 | -0.0112294–0.00123567 |

Post-layout acquisition error is at most about 1.14 mV in the accepted window,
with the largest error near the 0.7 V input point at 27 C. Turn-off pedestal
is about −6.77 to −7.50 mV, compared with approximately −3 to −3.77 mV before
extraction. Off-state input feedthrough reaches about 0.475 mV. Clock routing
and intrinsic switch charge therefore matter even with a roughly 500 fF
physical storage capacitor.

Quiet 10 us drift reaches about 11.23 mV at 85 C with the input driven low;
total held error reaches about 18.97 mV. Reacquisition error remains below
5.4 uV. These bounds describe a simple uncompensated sampler, not a precision
hold buffer. The signed drift depends strongly on off-state input and
temperature; an unchanged input or a nominal track waveform alone would miss
that behavior.

The independent source/RC graph audit recovers four functional nets, one MOS
and one physical MIM after collapsing parasitic resistors and applying the
explicit ideal-tap boundary, preserving MIM plate orientation. Native LVS checks
the tap and dimensions. Source simulation uses the finite tap model; Magic
idealizes the tap connection and supplies actual junction geometry and routing
RC. The import uses half-grid subdivision and a writable isolated Magic
database; the submitted GDS remains immutable. No native diagnostic is ignored.

At all sixteen conditions, halving maximum time step from 2 to 1 ns changes
acquisition error by less than 61 uV, pedestal by less than 2 uV, quiet drift
by less than 0.2 uV and clock energy by less than 0.03%. Tightening numerical
tolerances tenfold, reducing `gmin` from 1e-15 to 1e-16 and increasing
`rshunt` from 1e15 to 1e16 ohm changes pedestal by less than 23 uV, drift by
less than 0.8 uV and clock energy by less than 0.05%. All bounds still pass.
The shunt is a numerical aid, not the physical load producing the reported
drift. Independent integration and sampling of source/reference waveforms
checks all 18 observations in all sixteen conditions.

The reproduction below also probes 0.8/0.95 V inputs and a 100 us quiet hold
at 0.7 V, with the off-state input driven to 0 V. These are deliberately outside
the qualified scope. The same candidate RC gives:

| Out-of-scope observation | 27 C (mV) | 85 C (mV) |
| --- | --- | --- |
| Acquisition error over 80–190 ns, 0.8 V sample | 54.79 | 27.19 |
| Acquisition error over 80–190 ns, 0.95 V sample | 187.19 | 151.00 |
| Quiet 100 us drift, 0.7 V sample | 8.11 | 106.83 |

The acquisition contract fails at the high inputs, and the high-temperature
long hold fails retention. Reports expose the failed bounds instead of treating
successful SPICE execution as qualification. Neither source labels nor device
count establish a useful sampling range.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Run from the repository root with the [shared tool setup](../../../../../docs/tools.md#manual-tools).
The existing `analog-res-models` profile supplies MOS/MIM and explicit tap
models. Existing IHP physical and RC tools suffice; no image rebuild or
framework extension is needed.

```bash
python -m layout_eval.preview prepare \
  --case smp_001_nmos_th --image iclayout-bench-tools:local \
  --output build/runs/nmos-hold-prepared
python -m layout_eval.preview run \
  --prepared build/runs/nmos-hold-prepared --output build/runs/nmos-hold-reference
python -m pytest tests/integration/test_public_references.py \
  -k smp_001_nmos_th
```

These commands create the reader's resources, candidate RC, reports and
waveforms; choose fresh output paths. After the preview, the recipe below
runs source calibration, both numerical checks and the two out-of-scope probes.
The first three variants retain all sixteen conditions. The probes select
four high-input or two long-hold controls. All retain the original acceptance
bounds so the failed scope extensions remain visible.

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

case = Path('build/runs/nmos-hold-prepared/case/case.toml')
reference = Path('build/runs/nmos-hold-reference/reference')
task = load_task(case)
report = json.loads((reference / 'report.json').read_text())
assert report['task_success']
rc = Asset((reference / report['jobs']['parasitics']['outputs']['netlist']['path']).read_bytes(), 'spice')
base = tomllib.loads(case.read_text())['task']['evaluation']
for variant in ('source', 'half-step', 'tight', 'headroom', 'long-hold'):
    plan = copy.deepcopy(base)
    plan['mode'] = 'characterization'
    plan.pop('scoring')
    plan['jobs'] = [j for j in plan['jobs'] if j['stage'] == 'simulate']
    if variant == 'headroom':
        plan['jobs'] = [plan['jobs'][i] for i in (0, 2, 8, 10)]
        for job, level in zip(plan['jobs'], (0.8, 0.95, 0.8, 0.95)):
            job['parameters']['values']['sample_v'] = level
    if variant == 'long-hold':
        plan['jobs'] = [plan['jobs'][i] for i in (6, 14)]
    selected = {j['id'] for j in plan['jobs']}
    for job in plan['jobs']:
        job['inputs']['dut'] = 'input:simulation'
    plan['metrics'] = [m for m in plan['metrics'] if m['category'] == 'performance']
    for metric in plan['metrics']:
        for key in ('dimension', 'zero_lower', 'zero_upper'):
            metric.pop(key, None)
        metric['observations'] = [o for o in metric['observations'] if o.split(':')[0] in selected]
    inputs = task.evaluation_inputs()
    if variant != 'source':
        inputs['input:simulation'] = rc
    deck = inputs['input:performance'].content.decode()
    if variant == 'half-step':
        deck = deck.replace('tran 2n 11.7u 0 2n', 'tran 1n 11.7u 0 1n')
    if variant == 'tight':
        deck = deck.replace('gmin=1e-15 rshunt=1e15 reltol=1e-6 abstol=1e-15 vntol=1e-9',
                            'gmin=1e-16 rshunt=1e16 reltol=1e-7 abstol=1e-16 vntol=1e-10')
    if variant == 'long-hold':
        deck = deck.replace('11.', '101.').replace('at=11u', 'at=101u').replace('to=11u', 'to=101u')
    inputs['input:performance'] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('nmos-hold-' + variant),
    )
    expected = 'failed' if variant in ('headroom', 'long-hold') else 'passed'
    assert result['outcome'] == expected, result
    assert all(job['status'] == 'passed' for job in result['jobs'].values()), result
PYCODE
```

## Source and License

Derived from [analog-db smp_001_nmos_th at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/smp_001_nmos_th).
The fixed manifest identifies the sampler as a SpiceXplorer worked example,
records `analog-circuit-design` provenance and an Apache-2.0 component label.
Normalized derivatives and the independent witness retain PolyForm
Noncommercial terms and the database Required Notice. Collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) preserve the applicable
terms; the normalized circuit is not relicensed under framework MIT.
The independently authored measurement deck is MIT.
