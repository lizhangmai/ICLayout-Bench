> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Five-Transistor OTA Core with Bias Mirror

## Overview

This maintained IHP SG13G2 OTA uses an NMOS differential pair, PMOS mirror load,
NMOS tail device and diode-connected NMOS bias reference. The five-transistor
core therefore has six MOS instances in its complete interface. The fixed
upstream IHP dimensions are retained; explicit well/substrate taps and a fresh
physical layout complete the maintained circuit. The native CDL and simulator
netlists describe the same device connectivity and geometry.

The qualification scope is nominal AC/DC at 1.5 V, 20 uA reference current,
0.8 V input common mode and 10 pF external output load, TT, 27 C. Matching means
fixed electrical dimensions here; no statistical mismatch or physical centroid
constraint is claimed. Noise, distortion, transient settling, PVT and EM are
outside the declared scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing requirements and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC/simulation plan and frozen limits |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative native LVS circuit with taps |
| [materials/circuit.spice](materials/circuit.spice) | Same circuit as ngspice model calls, for source calibration |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout AC/DC testbench |
| [reference/amp_001_5t.gds](reference/amp_001_5t.gds) | Independently constructed witness; not a solver input |

## Reference Results

The reference passes artifact, main/extra DRC without waivers, strict named-port
LVS, geometry, candidate-derived distributed RC extraction and all six nominal
electrical requirements through the published case plan. Its functional
bounding-box area is 3675.0499 um2. This demonstrates feasibility at the declared
conditions, not optimum area or a model score.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| Low-frequency gain | dB | 33.11524 | 33.10943 |
| Unity-gain bandwidth | Hz | 1,211,382 | 1,206,185 |
| Phase margin | deg | 83.80139 | 83.71266 |
| Output bias | V | 0.79870636 | 0.798673565 |
| Bias voltage | V | 0.41466120 | 0.41529479 |
| Supply power, including reference branch | W | 0.00005928993 | 0.00005925994 |

The acceptance bands target a 30 dB, 1 MHz amplifier with at least 60 degrees
phase margin and a 65 uW supply budget. They are supported by the same-condition
source/post-layout measurements above, not inherited from upstream datasheet
claims. Bias bands surround the intended 0.8 V operating point and nominal
reference mirror bias. See the problem for the full bands and zero boundaries.
The reference fits within the 100 by 40 um nominal routing budget.
The absolute area target is that routing budget (4000 um2); area utility
falls to zero at 8000 um2. These fixed budgets are independent of a submitted
candidate or a reference-area ratio. The coefficient is 4 for a complete compact
amplifier with bias and load matching.

Physical LVS includes explicit well/substrate tap devices. Magic retains its
candidate-derived external RC network but does not emit the separate tap compact
models used by the source. This is a nominal model boundary, not a substrate
noise or statistical matching model.
A source-only control with ideal rail-connected bodies changes bandwidth by
8 Hz and phase margin by 0.00021 degrees at these conditions; the reproduction
below includes that control. This does not qualify substrate noise behavior.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

From the repository root, follow the shared [tool setup](../../../../../docs/tools.md)
and run the no-model preview:

```bash
python -m layout_eval.preview quickstart --case amp_001_5t \
  --output build/runs/analog-db-ota-preview
```

Add `--skip-build` when the maintained tools image already exists. This command
creates the prepared case/resources and the reference report under the selected
output directory. Use a fresh output directory for each run.

To reproduce source calibration with that prepared toolchain and the same
published testbench:

```bash
uv run --locked python - <<'PY'
import json
from pathlib import Path
from benchmarking.evaluation import parse_evaluation
from layout_eval.evaluate import run_evaluation
from benchmarking.tasks import load_task
from layout_eval.toolchains import load_toolchain
from benchmarking.files import Asset

config = Path('build/runs/analog-db-ota-preview/prepared/case/case.toml')
task = load_task(config)
plan = task.evaluation.description()
plan['mode'] = 'characterization'
plan.pop('scoring', None)
plan['jobs'] = [j for j in plan['jobs'] if j['stage'] == 'simulate']
for job in plan['jobs']:
    job['inputs']['dut'] = 'input:simulation'
    job.pop('requires', None)
plan['metrics'] = [m for m in plan['metrics'] if m['category'] == 'performance']
for metric in plan['metrics']:
    for key in ('dimension', 'zero_lower', 'zero_upper'):
        metric.pop(key, None)
report = run_evaluation(parse_evaluation(json.dumps(plan).encode(), file_format='json'),
                        task.evaluation_inputs(), load_toolchain(config),
                        Path('build/runs/analog-db-ota-source'), task_sha256=task.digest)
assert report['outcome'] == 'passed', report

# Isolate the finite-tap compact-model boundary, without changing MOS sizes.
inputs = task.evaluation_inputs()
lines = []
for line in inputs['input:simulation'].content.decode().splitlines():
    if line.startswith('XR'):
        continue
    if line.startswith('XM'):
        fields = line.split()
        fields[4] = 'vdd' if 'pmos' in fields[5] else 'vss'
        line = ' '.join(fields)
    lines.append(line)
inputs['input:simulation'] = Asset(('\n'.join(lines) + '\n').encode(), 'spice')
control = run_evaluation(parse_evaluation(json.dumps(plan).encode(), file_format='json'),
                         inputs, load_toolchain(config),
                         Path('build/runs/analog-db-ota-ideal-body'), task_sha256=task.digest)
assert control['outcome'] == 'passed', control
PY
```

This creates reports under `build/runs/analog-db-ota-source/` and
`build/runs/analog-db-ota-ideal-body/`; both are characterization,
not scored layout results. The same catalog-driven witness/empty-candidate
regressions used by other public cases apply:

```bash
python -m pytest tests/integration/test_public_references.py -k amp_001_5t
```

Generated preparation/run directories are local outputs, not redistribution
packages. Retain the collection LICENSE and NOTICE when distributing case materials.

## Source and License

Derived from [MacAnalog analog-db amp_001_5t](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_001_5t), with the applicable [collection license](../../LICENSE) and [notices](../../NOTICE).
