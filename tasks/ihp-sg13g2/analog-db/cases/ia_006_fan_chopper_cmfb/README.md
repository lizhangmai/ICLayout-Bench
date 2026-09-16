> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Clocked Capacitive Instrumentation Amplifier with Transistor CMFB

## Overview

This complete differential instrumentation amplifier combines input, feedback
and interstage/output chopping with capacitive signal transfer, a two-stage
core and transistor common-mode feedback. All six complementary clock signals
run during qualification. The controller senses both outputs through physical
resistors and drives the split output-current-source gates; no ideal external
common-mode or differential-feedback servo closes the loop.

The maintained circuit retains all 46 source MOS groups as 61 physical fingers.
Parallel fingers preserve the core's total W*m/L; paired core groups use ABBA
placement to control deterministic interconnect asymmetry. Three controller
groups have explicit 10 nm grid rounding: XM1_CMFB W/L=0.33/0.26 um,
XM3_CMFB W/L=0.88/0.26 um, and XM7_CMFB W=0.29 um. The authoritative netlist
fixes every finger dimension. Four core bias voltages and the common-mode
reference become external ports. Two additional high-impedance summing-node
monitor ports are observed without an external source, servo or load; they also
anchor symmetric branches for strict native named-port LVS.

Thirteen physical MIM units implement every internal capacitor. Each input
arm totals 16.008384 pF and each feedback arm 0.80480575 pF, a ratio of
19.89099. Each bias-return arm contains 41 high-poly segments totaling nominally
10.46156 Mohm; each common-mode sense arm contains four segments totaling
1.02064 Mohm. There are 90 physical resistor segments altogether. Compensation
is deliberately retuned for the physical combined loop: each differential
Miller capacitor is 4.002096 pF and the controller capacitor is 1.00646975 pF,
replacing the raw ideal 1 pF and 1 fF values. This is a maintained physical
variant, not qualification of the unmodified source. Explicit well/substrate
taps complete the circuit. Internal passives are distinct from output loads.

Qualification covers TT, 27 C, 1.2 V, 0.6 V input common mode and reference,
20 kHz synchronous finite-slope complementary clocks, and 1/5 pF per output,
each with a signed ±10 mV differential step and return. It establishes clocked
DC transfer, integer-period mean recovery, full ripple and actual common-mode
regulation. It does not establish low-noise/low-ripple performance, broadband
response, PSS/PAC/noise, input impedance, internal-loop phase margins, arbitrary
loads or clock phasing, PVT, mismatch, rail-to-rail operation or zero-supply
startup. The full switching ripple and extracted bias shift are material limits.

## Files

- [Problem](problem.md): self-contained interface, physical and measurement contract.
- [Configuration](case.toml): frozen inputs, checks, scoring and witness identity.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): equivalent physical device definitions for the native readers.
- [Testbench](materials/testbench.spice): external bias, six running clocks, signal/load conditions and measurements.
- [Reference layout](reference/ia_006_fan_chopper_cmfb.gds): independently constructed witness with physical passives and matched core placement.

Only the problem and three materials files enter solver inputs. Collection
LICENSE and NOTICE accompany distributions separately. Upstream DSL, layouts,
author generators and scoring are not runtime dependencies.

## Reference Results

The reference passes native main/maximal DRC without waivers, strict named-port
LVS, functional geometry, candidate RC extraction and every electrical bound.
The functional bounding-box area is 1110626.873 um² and the score is 100.
Fixed area anchors of 1200000/4800000 um² accommodate 164 functional devices,
taps and complete routing, including the long physical bias-return chains.
Coefficient 10 reflects the system-level combination of signal/feedback
modulation and interacting differential/common-mode control across clock states
and input polarities. It is not assigned from device count or development effort.

The table gives all four conditions; identical values appear once. DC values
are diagnostics at the solved initial operating point. Running-clock means,
not static differential balance, determine acceptance. B/H/R measurement
windows each contain two complete clock periods; power over the accepted
sequence contains 22 periods. The problem defines exact boundaries and units.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `gain_vv` | V/V | 19.61634–19.61731 | 19.49643–19.4968 |
| `baseline_error_v` | V | 4.943016e-08–5.672646e-08 | 2.97655e-06–3.042652e-06 |
| `return_error_v` | V | 6.371404e-08–8.39291e-08 | 2.298879e-06–2.464465e-06 |
| `high_drift_v` | V | 0–5e-07 | 0–6e-07 |
| `return_drift_v` | V | 4.317e-10–8.58e-09 | 2.4166e-08–2.48036e-07 |
| `ripple_rms_v` | V | 0.007830381–0.00788468 | 0.008779262–0.009416793 |
| `ripple_pp_v` | V | 0.0956577–0.1040801 | 0.0770971–0.0803915 |
| `cm_mean_v` | V | 0.6128099–0.6128107 | 0.6168123–0.6168139 |
| `cm_min_v` | V | 0.6104253–0.6104701 | 0.6152353–0.6154966 |
| `cm_max_v` | V | 0.6137994–0.6146429 | 0.6177742–0.6188013 |
| `sum_cm_v` | V | 0.6000626 | 0.6000512–0.6000513 |
| `sum_error_v` | V | 6.71883e-05–6.755051e-05 | 0.0001046344–0.0001056003 |
| `mean_power_w` | W | 0.0003175971–0.0003176063 | 0.0002278427–0.0002278484 |
| `clock_power_w` | W | 8.664582e-10–8.672072e-10 | 1.034141e-08–1.034846e-08 |
| `dc_cm_v` | V | 0.6128227 | 0.616833 |
| `dc_dm_v` | V | -2.796539e-05 | -0.007679971 |
| `baseline_v` | V | -5.672646e-08–-4.943016e-08 | 2.97655e-06–3.042652e-06 |
| `plateau_v` | V | -0.1961729–0.196173 | -0.1949625–0.194971 |
| `return_v` | V | -1.234058e-07–2.720264e-08 | 5.284363e-06–5.498803e-06 |
| `dc_power_w` | W | 0.0003175407 | 0.0002275794 |

The extracted mean differential gain is about 19.50 V/V, compared with 19.62
before extraction and the nominal capacitor ratio of 19.89. The zero-input
mean is about 3 uV, while unfiltered ripple RMS is 8.8–9.4 mV and peak-to-peak
ripple reaches about 80.5 mV. All switching edges are included; no spike
blanking or post-filter hides this ripple. Success means the declared period
means and full-ripple bounds pass, not a quiet instantaneous output.

VDD-supplied mean power falls from about 317.6 to 227.8 uW after extraction;
output common mode shifts from about 0.6128 to 0.6168 V. Supply/interconnect
resistance materially changes this bias-sensitive circuit. Mean clock power
rises from about 0.867 to 10.35 nW. Clock power sums each source's positive
supplied power over complete periods without credit for recovered energy.
VDD power remains positive during the measured sequence. External bias/reference
and signal-generator overhead is excluded; supplied clock energy is reported
separately and is not a clock-driver implementation's total power.

The extracted circuit preserves 61 MOS, 13 physical MIM units and 90 physical
poly segments. Collapsing only parasitic resistors, removing parasitic
capacitors and applying the declared ideal-tap boundary recovers the source
124-net device graph, including MIM plate orientation. Native LVS checks the
explicit taps and dimensions. Source simulation retains finite tap models;
Magic idealizes the tap connections. Distributed substrate resistance/noise is
unqualified. Half-grid import and a writable isolated Magic import preserve
process-grid geometry; the submitted GDS is immutable. No extraction diagnostic
or native DRC/LVS failure is waived.

With Gear order 2, reducing maximum time step from 500 to 250 ns at all four
conditions, and to 100 ns at 1 pF positive / 5 pF negative controls, changes
gain by less than 0.0005%, ripple RMS by less than 8 uV, peak-to-peak ripple
by less than 60 uV, period-mean errors/drift by less than 1 uV and clock power
by less than 0.03%. Tightening reltol/abstol/vntol tenfold and increasing the
numerical shunt from 1e13 to 1e14 ohm at all four conditions changes gain by
less than 0.015%, ripple RMS by less than 94 uV, peak-to-peak ripple by less
than 0.45 mV and VDD power by less than 0.6%. All bounds still pass.

A SPARSE-versus-KLU control at 1 pF positive input also passes, with gain
change below 0.00007 V/V and ripple RMS change below 35 uV. Only required
waveform vectors are saved; the native KLU solver is used for scored runs.
Independent integration of the saved source/reference waveforms verifies all
20 reported observations in each of the four conditions, including signed
transfer and positive-only clock energy. These checks establish numerical
consistency for this sequence, not general periodic or physical accuracy.

## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

Run from the repository root with the [shared tool setup](../../../../../docs/tools.md#manual-tools).
The existing `analog-res-models` profile supplies pinned MOS/MIM and R3_CMC
models. The maintained case uses existing physical, extraction and scoring
mechanisms; no image rebuild or new framework/PDK capability is required.

```bash
python -m layout_eval.preview prepare \
  --case ia_006_fan_chopper_cmfb --image iclayout-bench-tools:local \
  --output build/runs/chopper-ia-prepared
python -m layout_eval.preview run \
  --prepared build/runs/chopper-ia-prepared --output build/runs/chopper-ia-reference
python -m pytest tests/integration/test_public_references.py \
  -k ia_006_fan_chopper_cmfb
```

These commands generate the reader's prepared resources, reports, candidate
extraction and waveforms. Use fresh output directories. After that preview,
run this source calibration and candidate-RC numerical recipe with the same
acceptance bounds. The finer-step and SPARSE variants select the controls
identified above; source, half-step and tight variants cover all four conditions.

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

case = Path('build/runs/chopper-ia-prepared/case/case.toml')
reference = Path('build/runs/chopper-ia-reference/reference')
task = load_task(case)
report = json.loads((reference / 'report.json').read_text())
assert report['task_success']
rc = Asset((reference / report['jobs']['parasitics']['outputs']['netlist']['path']).read_bytes(), 'spice')
base = tomllib.loads(case.read_text())['task']['evaluation']
for variant in ('source', 'half-step', 'tight', 'fine-step', 'sparse'):
    plan = copy.deepcopy(base)
    plan['mode'] = 'characterization'
    plan.pop('scoring')
    plan['jobs'] = [j for j in plan['jobs'] if j['stage'] == 'simulate']
    if variant == 'fine-step':
        plan['jobs'] = [plan['jobs'][0], plan['jobs'][3]]
    if variant == 'sparse':
        plan['jobs'] = plan['jobs'][:1]
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
    if variant in ('half-step', 'fine-step'):
        step = '250n' if variant == 'half-step' else '100n'
        deck = deck.replace('tran 500n 1.5m 0 500n', f'tran {step} 1.5m 0 {step}')
    if variant == 'tight':
        deck = deck.replace('rshunt=1e13 reltol=1e-5 abstol=1e-13 vntol=1e-8',
                            'rshunt=1e14 reltol=1e-6 abstol=1e-14 vntol=1e-9')
    if variant == 'sparse':
        deck = deck.replace('.option klu ', '.option ')
    inputs['input:performance'] = Asset(deck.encode(), 'spice')
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('chopper-ia-' + variant),
    )
    assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [analog-db ia_006_fan_chopper_cmfb at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_006_fan_chopper_cmfb).
The fixed manifest attributes normalized schematic capture/composition to
Danial Noori Zadeh after Fan et al.; it supplies no separate component license
label. The fixed database LICENSE and NOTICE cover original/normalized
materials under PolyForm Noncommercial 1.0.0. The derivative circuit and
independent witness retain those terms and the Required Notice in the collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE); the normalized material is
not relicensed MIT. The independently authored measurement deck is MIT.
