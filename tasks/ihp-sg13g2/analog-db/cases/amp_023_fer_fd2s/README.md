> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Fully Differential Two-Stage OTA with Common-Mode Feedback

## Overview

A folded first stage drives two common-source output stages with physical
series R/C compensation and transistor common-mode feedback. All 28 source
MOS groups retain their W/L/m and connections, expanded into 50 physical MOS.
The original internal ideal sources become explicit `ibias` and `vcmr` ports:
a 20 uA source supplies IBIAS from VDD, and VCMR receives the output common-mode
reference. Mirrors and the common-mode controller remain inside the circuit.

Each compensation path uses a nominal 1.52 kohm high-poly resistor and two
parallel 25.85 × 25.85 um MIM units totaling 2.01294 pF. Each output-sensing
arm uses eight nominal 25.66 kohm poly segments in series, in parallel with
one 9.95 × 9.95 um MIM capacitor (150.096 fF). These implement all original
1.5 kohm / 2 pF compensation and 200 kohm / 150 fF sensing branches; no
functional passive is removed. Explicit well/substrate contacts complete the
physical circuit.

Qualification covers 1.2 V, 27 C, typical models, 0.5 V input common mode and
1/5/10 pF per output. Each load has positive and negative differential steps
paired with positive and negative common-mode current disturbances. External
feedback fixes input common mode and closes only the differential signal loop;
the actual transistor controller regulates output common mode. The measurements
include differential return ratio, common-mode reference transfer and peaking,
sustained recovery after both types of steps, cross-coupled errors, and recovery
from equal output-current kicks. Common-mode transfer is a closed-loop response,
not an internal common-mode loop phase-margin measurement.

Noise, distortion, PVT, mismatch, rail-to-rail operation, startup from zero
supply, arbitrary loads and fabrication signoff are outside this qualification.
The increased common-mode peaking after extraction is a material limitation.

## Files

- [Problem](problem.md): complete solver contract, measurement windows and scoring.
- [Configuration](case.toml): frozen inputs, tool bindings and reference identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice):
  equivalent physical device definitions for the two native readers.
- [Testbench](materials/testbench.spice): bias, differential/common-mode AC and transient measurements.
- [Reference layout](reference/amp_023_fer_fd2s.gds): independently constructed physical witness.

Only the problem and three materials files enter solver inputs. Collection
LICENSE and NOTICE accompany distributions separately. Source layouts,
generators, DSL and upstream scoring are not runtime dependencies.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC extraction and all electrical bounds.
Its functional bounding-box area is 89741.183 um² and its score is 100.
Fixed area anchors are 95000/380000 um², accommodating 50 MOS, six MIM units,
18 resistor segments, taps and complete routing. Coefficient 9 reflects coupled
differential and common-mode compensation and recovery. These absolute anchors
do not track a changing reference layout.

The table reports all six conditions; identical values appear once. Power is
VDD-supplied power, including the external 20 uA drawn from VDD and on-chip
mirrors. External feedback, reference and disturbance-source energy and bias
generator overhead are excluded. Mean power averages the finite 0–8 us test
sequence, not a complete 20 us pulse period. VDD supplies positive power
throughout the measured sequence.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_cm_v` | V | 0.7536909 | 0.7540654 |
| `output_dm_v` | V | -1.606493e-13 | 0.0001377083 |
| `bias_v` | V | 0.3867579 | 0.3963358 |
| `power_w` | W | 0.0005720081 | 0.0005655747 |
| `dm_gain_db` | dB | 61.6623 | 61.86768 |
| `unity_hz` | Hz | 2.070397e+07–2.460567e+07 | 2.043506e+07–2.527824e+07 |
| `phase_margin_deg` | deg | 72.8372–101.6995 | 71.1612–101.8228 |
| `cm_gain_vv` | V/V | 1.064286 | 1.060767 |
| `cm_peak_vv` | V/V | 1.083292–1.125353 | 1.487001–1.657028 |
| `dm_up_error_v` | V | 8.268386e-05 | 5.685723e-05–0.0002183719 |
| `dm_down_error_v` | V | 2.311484e-13–7.364109e-13 | 0.0001377083 |
| `cm_up_error_v` | V | 0.008070969 | 0.008104677–0.008105633 |
| `cm_down_error_v` | V | 0.003946135–0.004627371 | 0.004340494–0.005177776 |
| `cm_kick_error_v` | V | 0.003690862–0.003690863 | 0.0040654 |
| `cm_kick_peak_v` | V | 0.02614724–0.04855971 | 0.03333466–0.06652191 |
| `dm_peak_v` | V | 0.1000001–0.1020541 | 0.09991323–0.1030632 |
| `mean_power_w` | W | 0.0005715061–0.0005715175 | 0.0005650759–0.0005651148 |
| `dm_cm_error_v` | V | 8.399948e-05 | 5.365265e-05–0.000217755 |
| `cm_dm_error_v` | V | 0.003690737 | 0.004064673–0.004065426 |
| `dm_high_v` | V | -0.09991732–0.09991732 | -0.09978163–0.1000569 |
| `cm_high_v` | V | 0.808071 | 0.8081047–0.8081056 |

Post-layout differential unity frequencies are 25.278/23.296/20.435 MHz and
phase margins 101.823/85.188/71.161 degrees in load order. Common-mode
closed-loop peaking increases from at most 1.126 V/V before extraction to
1.658 V/V afterward. Differential step error remains below 0.219 mV; the
raised common-mode reference has about 8.11 mV sustained error. Error metrics
bound entire declared recovery windows, rather than a first tolerance crossing.
The problem specifies the separate disturbance peak and cross-coupling bounds.

The extracted circuit preserves 50 MOS, six physical MIM units and 18 physical
poly resistors. Collapsing only parasitic resistors, removing parasitic
capacitors and applying the declared ideal-tap boundary recovers the source
38-net device graph. Native LVS also checks taps and dimensions. Magic idealizes
well/substrate ties while source simulation retains finite tap models;
distributed substrate resistance/noise is unqualified. Extraction uses the
existing half-grid import option and writable Magic import database to retain
geometry on the process grid; the submitted GDS remains immutable and native
DRC/LVS inspect that GDS. No diagnostics are waived or ignored.

At all six conditions, halving maximum transient step from 1 to 0.5 ns changes
excursion peaks by less than 0.13 mV and sustained-window errors by less than
9 uV. Tightening reltol/abstol/vntol tenfold, increasing the numerical shunt
from 1e12 to 1e13 ohm and doubling both AC sweep densities changes unity
frequency by less than 0.003%, differential phase margin by less than 0.001
degrees and common-mode peaking by less than 0.00011 V/V. All limits still pass.
The supplied recipe reproduces these scope-specific checks using candidate RC.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Run from the repository root with the [shared tool setup](../../../../../docs/tools.md#manual-tools).
The existing `analog-res-models` profile provides the pinned MOS/MIM and R3_CMC
models. No image rebuild or new framework/PDK mechanism is needed.

```bash
python -m layout_eval.preview prepare \
  --case amp_023_fer_fd2s --image iclayout-bench-tools:local \
  --output build/runs/fd2s-prepared
python -m layout_eval.preview run \
  --prepared build/runs/fd2s-prepared --output build/runs/fd2s-reference
python -m pytest tests/integration/test_public_references.py \
  -k amp_023_fer_fd2s
```

These commands create the reader's own prepared resources, reference report,
extraction and waveforms; use fresh output paths. After the preview run, the
following performs source calibration and both numerical checks at all six
conditions with the same acceptance bounds, without changing the scored case.

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

case = Path('build/runs/fd2s-prepared/case/case.toml')
reference = Path('build/runs/fd2s-reference/reference')
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
        deck = deck.replace('tran 1n 8u 0 1n', 'tran 0.5n 8u 0 0.5n')
    if variant == 'tight':
        deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-13 vntol=1e-8',
                            'rshunt=1e13 reltol=1e-6 abstol=1e-14 vntol=1e-9')
        deck = deck.replace('ac dec 150', 'ac dec 300')
        deck = deck.replace('ac dec 100', 'ac dec 200')
    inputs['input:performance'] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('fd2s-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db amp_023_fer_fd2s at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_023_fer_fd2s).
Normalized materials and their derivative witness retain PolyForm Noncommercial
terms; the fixed snapshot records Token Zhang / Arcadia-1 ferrosim and MIT
component attribution. This is not independent verification of the original
ferrosim repository or its original copyright notice. The collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE) retain those terms and the
database Required Notice. The independently authored measurement deck is MIT.
