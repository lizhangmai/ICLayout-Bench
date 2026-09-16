> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Resistor-Pullup NMOS Shunt Trim

## Overview

A W=2 um / L=0.5 um NMOS shunts the output of an approximately 200 kohm
physical pullup. Eight W=1 um / L=17.465 um high-poly segments replace the source
ideal resistor; MOS dimensions and all connections are retained, with an
explicit substrate contact. The independent reference retains the full resistor
area and body connection.

Qualification covers nonlinear trim range, sampled monotonic control,
finite-bias shunt conductance and loaded recovery across 1.1/1.3 V,
27/85 C and 500 kohm/1 Mohm loads. Output varies substantially with load and
temperature; this is an unbuffered control node, not precision conversion or
an ideal programmable resistor.

## Files

- [Problem](problem.md): complete solver contract and scope.
- [Configuration](case.toml): input digests, requirements, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching physical devices.
- [Testbench](materials/testbench.spice): control sweep, conductance and step recovery.
- [Reference](reference/trm_001_vcr.gds): independently constructed physical witness.

Only the problem and three materials enter solver inputs. Collection licenses
and notices accompany distributions separately; no source generator or original
layout is needed.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC and every electrical bound. Functional
area is 7608.7043 um²; the unified score is
100. Absolute area anchors are 8000/32000 um²,
with coefficient 4. These fixed budgets include all physical devices,
contacts and routing; they are not ratios to a changing witness. The reference
is a feasibility witness, not an area optimum.

The grade reflects a compact physical high-resistance network with nonlinear control, multiple operating conditions and recovery requirements.

Source simulation uses the maintained physical circuit with finite tap models;
post-layout uses candidate GDS-derived RC. Ranges below cover every condition
in the corresponding main, startup or sweep job; the problem specifies the
exact windows, supply accounting and acceptance bounds.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.048928095–0.063328792 | 0.049153295–0.063619726 |
| `power_w` | W | 5.8002812e-06–9.2495072e-06 | 5.7979386e-06–9.2453209e-06 |
| `high_v` | V | 0.7064219–1.041178 | 0.7063899–1.041143 |
| `low_v` | V | 0.007459411–0.0127078 | 0.007680443–0.01300553 |
| `knee_code_v` | V | 0.3227419–0.3628944 | 0.3227983–0.3629608 |
| `maximum_slope` | V/V | -0.023065316–-0.014507299 | -0.023056621–-0.014500865 |
| `span_v` | V | 0.6957099–1.0323365 | 0.69542711–1.0320393 |
| `conductance_04_s` | S | 9.702293e-05–0.0001196524 | 9.653373e-05–0.0001189998 |
| `conductance_06_s` | S | 0.0003544861–0.0004249599 | 0.0003493221–0.0004176012 |
| `conductance_ratio` | 1 | 2.9810317–4.3571978 | 2.9535966–4.3036201 |
| `recovery_down_v` | V | 2.748335e-10–2.949312e-09 | 1.60939e-09–4.571529e-09 |
| `recovery_up_v` | V | 2.708194e-09–4.499059e-08 | 1.24619e-10–3.844061e-08 |
| `mean_power_w` | W | 4.566792e-06–8.015902e-06 | 4.565953e-06–8.012931e-06 |
| `step_span_v` | V | 0.29636584–0.63795004 | 0.29632681–0.63783733 |

An independent terminal-role graph audit matches all 9 functional devices
and 11 nets after collapsing only interconnect resistors and applying the
extractor's ideal-tap boundary. Native LVS separately checks device dimensions
and physical contacts. Source and candidate retain every internal passive.
This does not qualify a distributed substrate model.

Independent saved-waveform recomputation checks 416 observations across all
32 source/reference/numerical jobs. Adjacent-point secants independently
confirm decreasing output across every full control sweep; conductance is
recomputed from raw supply current after removing the external load current.
The finite-bias conductance ratio and substantial load/temperature dependence
are measured properties, not a claim of ideal resistance programming.

Halving the maximum step to 1 ns and separately tightening reltol/abstol/vntol
tenfold, raising rshunt to 1e13 ohm and halving the control increment to 1 mV
preserve every bound. The largest changes in the tightened run are below.
The independently integrated recovery means agree within 0.1 uV of ngspice's
windowed measurements, far below the 100 uV acceptance limit.

- `span_v`: maximum absolute tight-run change 2.095e-06 (the metric’s unit above).
- `knee_code_v`: maximum absolute tight-run change 4.4e-06 (the metric’s unit above).
- `maximum_slope`: maximum absolute tight-run change 6.364987e-07 (the metric’s unit above).
- `conductance_ratio`: maximum absolute tight-run change 6.887902e-06 (the metric’s unit above).
- `recovery_up_v`: maximum absolute tight-run change 3.62484e-08 (the metric’s unit above).

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

From the repository root use the [shared tools](../../../../../docs/tools.md#manual-tools).
Commands create the reader's own resources and reports; use fresh output paths.

```bash
python -m layout_eval.preview prepare \
  --case trm_001_vcr --image iclayout-bench-tools:local \
  --output build/runs/trm_001_vcr-prepared
python -m layout_eval.preview run \
  --prepared build/runs/trm_001_vcr-prepared --output build/runs/trm_001_vcr-reference
python -m pytest tests/integration/test_public_references.py \
  -k trm_001_vcr
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

case = Path('build/runs/trm_001_vcr-prepared/case/case.toml')
reference = Path('build/runs/trm_001_vcr-reference/reference')
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
    for role in ('performance',):
        deck = inputs['input:' + role].content.decode()
        if variant == 'half-step':
            deck = deck.replace('tran 2n 18u 0 2n', 'tran 1n 18u 0 1n')
        if variant == 'tight':
            deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-14 vntol=1e-8',
                                'rshunt=1e13 reltol=1e-6 abstol=1e-15 vntol=1e-9')
            deck = deck.replace('dc VCODE 0.2 0.8 0.002', 'dc VCODE 0.2 0.8 0.001')
        inputs['input:' + role] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('trm_001_vcr-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db trm_001_vcr at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/trm_001_vcr),
with PolyForm Noncommercial normalized-material terms and the recorded Apache
component attribution retained in [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE);
the independently authored measurement deck is MIT.
