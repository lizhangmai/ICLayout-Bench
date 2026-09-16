> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Unity-Feedback Regulator with Internal Output Storage

## Overview

A five-transistor NMOS-input error amplifier drives a PMOS pass array;
an on-chip diode-connected NMOS biases the tail mirror. The maintained circuit
retains all seven source MOS groups (29 physical fingers), the output bleeder,
reference-series resistor, Miller path and internal output capacitor. Unity
feedback senses output directly; there is no feedback divider. This adds
physical output storage, a reference impedance, explicit return ratio and
zero-state startup to the existing externally loaded regulator coverage.

The original 2 pF Miller compensation is deliberately retuned to five physical
36.515 um square units, nominally 10.0293 pF. Thirteen 50.635 um square MIM
units retain the approximately 50 pF internal COUT. Four physical high-poly
segments implement the approximately 100 kohm bleeder and one implements
approximately 10 kohm reference resistance. MOS dimensions and multiplicities
are unchanged; explicit substrate/well taps are added. The 20 uA bias source
and 0.9 V reference are external. The raw zero-volt loop measurement source
becomes an external zero-volt link between distinct output and sense ports;
it is not a manufactured voltage-source device or an ideal common-mode servo.

The contract covers typical models at 27 C, 1.2/1.3 V supplies, a 0.9 V
external reference, 0.1–1 mA load regulation, specified current-load steps,
downward supply-headroom sweeps and resistive-load startup. It is not capless:
all output storage remains inside the DUT. Qualification does not imply
arbitrary startup/load conditions, PVT or a precision voltage reference.

## Files

- [Problem](problem.md): complete interface and qualification contract.
- [Configuration](case.toml): frozen inputs, measurements, score and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical devices.
- [Main testbench](materials/testbench.spice): bias, return ratio and current-load steps.
- [Startup deck](materials/startup.spice): separate zero-state resistive-load analysis.
- [DC sweeps](materials/sweeps.spice): separate line/load and regulation-floor analysis.
- [Reference](reference/ldo_009_fer_5t_pass.gds): independently constructed physical witness.

The problem and five material files are solver inputs. Collection license and
notices accompany distributions separately; generators, upstream DSL, original
proprietary-process decks and maintainer waveforms are not solver inputs.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
area is 462428 um²; the unified score is
100. Absolute area anchors are 500000/2000000 um²,
with coefficient 8. These fixed budgets include all physical devices,
contacts and routing; they are not ratios to a changing witness. The reference
is a feasibility witness, not an area optimum.

The grade combines physical internal output capacitance, startup, regulation and return-ratio requirements across the declared operating conditions.

Source simulation uses the maintained physical circuit with finite tap models;
post-layout uses candidate GDS-derived RC. Ranges below cover every condition
in the corresponding main, startup or sweep job; the problem specifies the
exact windows, supply accounting and acceptance bounds.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.90712498–0.92280421 | 0.90692163–0.92309997 |
| `bias_v` | V | 0.38675793–0.38675793 | 0.38718865–0.38718883 |
| `quiescent_a` | A | 7.3029499e-05–7.3352527e-05 | 7.3003987e-05–7.3330396e-05 |
| `power_w` | W | 0.00020795224–0.00074507825 | 0.00020793012–0.00074504489 |
| `dc_gain_db` | dB | 45.45435–53.67274 | 43.65761–53.53236 |
| `unity_hz` | Hz | 3238258–5728183 | 3063653–5472153 |
| `phase_margin_deg` | deg | 49.457–76.5545 | 48.1891–74.7216 |
| `minimum_v` | V | 0.8620178–0.8979894 | 0.8394636–0.8940477 |
| `maximum_v` | V | 0.933738–0.9533911 | 0.9374569–0.9790293 |
| `recovery_load_v` | V | 0.002161652–0.01893865 | 0.001723351–0.01913797 |
| `recovery_release_v` | V | 0.007124978–0.02280421 | 0.006921627–0.02309997 |
| `mean_power_w` | W | 0.0002680455–0.001070795 | 0.0002680227–0.001070757 |
| `startup_error_v` | V | 0.002141717–0.02267805 | 0.001706354–0.02296928 |
| `startup_peak_v` | V | 0.90309–0.9893929 | 0.902639–1.003684 |
| `startup_minimum_v` | V | 6.799612e-09–7.365177e-08 | 1.801741e-07–1.977834e-06 |
| `regulation_floor_v` | V | 1.029643–1.184926 | 1.085568–1.185902 |
| `headroom_v` | V | 0.129643–0.284926 | 0.185568–0.285902 |
| `line_span_v` | V | 0.0020169–0.0083393 | 0.0012052–0.0086994 |
| `load_span_v` | V | 0.0122965–0.018626 | 0.01267–0.0202016 |

An independent terminal-role graph audit matches all 52 functional devices
and 13 nets after collapsing only interconnect resistors and applying the
extractor's ideal-tap boundary. Native LVS separately checks device dimensions
and physical contacts. Source and candidate retain every internal passive.
This does not qualify a distributed substrate model.

Independent saved-waveform recomputation checks 352 observations across all
64 simulation jobs in source/reference/numerical variants, including full DC
sweep endpoints, sustained startup/recovery errors and trapezoidal mean power.
Each AC sweep has one unity crossing over the declared frequency interval.
The approximately 1.186 V light-load regulation floor is set by the complete
loop's headroom, despite the smaller load; it is not a pass-device resistance
estimate. Internal COUT remains approximately 50 pF throughout qualification.

Halving main/startup maximum steps to 0.5/1 ns and separately tightening
reltol/abstol/vntol tenfold, raising rshunt to 1e13 ohm, doubling AC density
and halving both DC sweep increments preserve all bounds. The largest changes
in the tightened run are listed below. Ideal constant-current loading from
zero supply is outside qualification; the runnable failure probe below keeps
that distinction explicit: an ideal current sink draws output below the allowed
minimum before supply is available. This out-of-range model excursion is a
contract failure, not a calibrated prediction of physical negative voltage.
No arbitrary sequencing or brownout claim is made.

- `phase_margin_deg`: maximum absolute tight-run change 0.0002 (the metric’s unit above).
- `unity_hz`: maximum absolute tight-run change 72 (the metric’s unit above).
- `regulation_floor_v`: maximum absolute tight-run change 2e-06 (the metric’s unit above).
- `load_span_v`: maximum absolute tight-run change 1.3e-06 (the metric’s unit above).
- `line_span_v`: maximum absolute tight-run change 7.3e-06 (the metric’s unit above).
- `startup_peak_v`: maximum absolute tight-run change 2.14e-05 (the metric’s unit above).
- `recovery_load_v`: maximum absolute tight-run change 1.4e-07 (the metric’s unit above).

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

From the repository root, use the [shared tools](../../../../../docs/tools.md#manual-tools).
These commands generate the reader's own prepared resources, reports and RC;
use fresh output paths and reuse verified resources where available.

```bash
python -m layout_eval.preview prepare \
  --case ldo_009_fer_5t_pass --image iclayout-bench-tools:local \
  --output build/runs/ldo_009_fer_5t_pass-prepared
python -m layout_eval.preview run \
  --prepared build/runs/ldo_009_fer_5t_pass-prepared --output build/runs/ldo_009_fer_5t_pass-reference
python -m pytest tests/integration/test_public_references.py \
  -k ldo_009_fer_5t_pass
```

After the preview run, reproduce source and numerical calibration with its
frozen inputs, models and RC. These commands create new reports under
`build/runs/`; no maintainer output is required. Acceptance bounds stay fixed.

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

case = Path('build/runs/ldo_009_fer_5t_pass-prepared/case/case.toml')
reference = Path('build/runs/ldo_009_fer_5t_pass-reference/reference')
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
    for role in ('performance', 'startup', 'sweeps'):
        deck = inputs['input:' + role].content.decode()
        if variant == 'half-step':
            deck = deck.replace('tran 1n 18u 0 1n', 'tran 0.5n 18u 0 0.5n')
            deck = deck.replace('tran 2n 30u 0 2n', 'tran 1n 30u 0 1n')
        if variant == 'tight':
            deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-14 vntol=1e-8',
                                'rshunt=1e13 reltol=1e-6 abstol=1e-15 vntol=1e-9')
            deck = deck.replace('ac dec 150', 'ac dec 300')
            deck = deck.replace('dc VDD 1.3 0.8 -0.001', 'dc VDD 1.3 0.8 -0.0005')
            deck = deck.replace('dc ILOAD 0.0001 0.001 0.00001',
                                'dc ILOAD 0.0001 0.001 0.000005')
        inputs['input:' + role] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('ldo_009_fer_5t_pass-' + variant),
    )
    assert result['outcome'] == 'passed', result

# Failure probe: impose an ideal constant current from zero supply instead
# of a resistive startup load. This intentionally violates the load boundary.
plan = copy.deepcopy(base)
plan['mode'] = 'characterization'
plan.pop('scoring')
plan['jobs'] = [j for j in plan['jobs'] if j['id'].startswith('startup')]
plan['metrics'] = [m for m in plan['metrics'] if m['id'].startswith('startup')]
for job in plan['jobs']:
    job['inputs']['dut'] = 'input:simulation'
for metric in plan['metrics']:
    for key in ('dimension', 'zero_lower', 'zero_upper'):
        metric.pop(key, None)
inputs = task.evaluation_inputs()
inputs['input:simulation'] = rc
deck = inputs['input:startup'].content.decode().replace(
    'RLOAD vout 0 {load_ohm}', 'ILOAD vout 0 {0.9/load_ohm}')
inputs['input:startup'] = Asset(deck.encode(), 'spice')
result = run_evaluation(
    parse_evaluation(json.dumps(plan).encode(), file_format='json'),
    inputs, load_toolchain(case),
    Path('build/runs/ldo_009_fer_5t_pass-constant-current-startup'),
)
assert result['outcome'] == 'failed'
assert result['metrics']['startup_minimum_v']['status'] == 'failed'
PYCODE
```

## Source and License

Derived from [analog-db ldo_009_fer_5t_pass at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_009_fer_5t_pass),
with normalized PolyForm Noncommercial terms and the snapshot's Token Zhang /
Arcadia-1 ferrosim MIT attribution retained in [LICENSE](../../LICENSE) and
[NOTICE](../../NOTICE); the original ferrosim notice was not independently
retrieved. The independently authored measurement decks are MIT.
