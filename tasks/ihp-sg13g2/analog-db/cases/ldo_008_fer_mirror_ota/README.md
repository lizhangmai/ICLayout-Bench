> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Mirror-OTA Regulator with Bilateral Return-Ratio Measurements

## Overview

A seven-group mirror-OTA/PMOS-pass regulator retains 81 physical MOS fingers,
40 MIM units and three high-poly resistors. Its 160 pF series compensation and
9/9 kohm feedback divider remain inside the DUT. There is no separate COUT.
The reference is explicitly adjusted from source 0.6 V to 0.5 V for a nominal
1.0 V output; 20 uA supply-fed bias and all source MOS dimensions are retained.

The independent physical witness reuses the verified MOS/MIM/poly/RC path.
The loop measurement uses voltage and current injections at the divider/input
boundary. It preserves port loading and both transmission directions; a raw
voltage ratio at this boundary can falsely cross unity at high frequency.
Qualification includes complete return-difference screens, final crossover,
line/load/headroom, specified startup and fast/large load recovery.

## Files

- [Problem](problem.md): complete circuit and acceptance contract.
- [Configuration](case.toml): frozen inputs, score and witness.
- [Native circuit](materials/circuit.cdl) and [simulator circuit](materials/circuit.spice): matching physical devices.
- [Main deck](materials/testbench.spice): two-injection return ratio and load recovery.
- [Startup](materials/startup.spice), [DC sweeps](materials/sweeps.spice) and [fast response](materials/fast.spice): distinct initialization/time-scale requirements.
- [Reference GDS](reference/ldo_008_fer_mirror_ota.gds): independent physical witness.

Only the problem and six material files are solver inputs. Collection license
and notices accompany distributions separately; source generators and maintainer
waveforms are excluded.

## Reference Results

The independent reference passes native main/maximal DRC without waivers,
strict named-port LVS, functional geometry and candidate-derived RC simulation.
Functional area is 1,003,099.879 um²; absolute target/zero anchors are
1,100,000/4,400,000 um² and coefficient is 9. The resulting score is 100.
The budgets cover all physical passives and routing; this is a feasibility
witness, not an area optimum. No PDK, image, runner or scorer changes are needed.

The grade combines startup, regulation, fast and large load recovery, and bilateral return-ratio measurements with multiple-crossing checks.

Twenty nominal jobs cover four operating points/large load steps, eight
zero-state startups, four line/load sweeps and four fast responses. Source
simulation uses the maintained circuit with finite taps; candidate RC uses
the extractor's ideal-tap boundary. The independent terminal-role audit matches
all 124 functional devices and 11 nets after collapsing interconnect resistance.
Every internal capacitor and resistor remains present. Units and exact windows
for these observations are specified in the problem.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 1.001597–1.00836 | 1.000258–1.00786 |
| `bias_v` | V | 0.3264929–0.3264929 | 0.3270808–0.3270815 |
| `quiescent_a` | A | 0.0001452354–0.0001460222 | 0.0001441912–0.0001450456 |
| `power_w` | W | 0.0002949608–0.0008391818 | 0.0002937841–0.0008378832 |
| `dc_gain_db` | dB | 44.61466–49.0275 | 33.87283–48.66397 |
| `unity_hz` | Hz | 407773.7–458663.1 | 502705.5–1247719 |
| `phase_margin_deg` | deg | 125.8726–131.739 | 145.6133–163.46 |
| `final_unity_hz` | Hz | 407773.7–458663.1 | 502705.5–7.638939e+07 |
| `final_phase_margin_deg` | deg | 125.8726–131.739 | 75.9188–151.3182 |
| `minimum_return_distance` | 1 | 0.8119622–0.8513839 | 0.5018963–0.7062579 |
| `return_phase_excursion_deg` | deg | 78.81361–81.41008 | 68.48608–80.42912 |
| `hf_gain_db` | dB | -7.633848–-6.412583 | -27.2402–-18.28299 |
| `minimum_v` | V | 0.9742929–0.9934197 | 0.9386478–0.9871642 |
| `maximum_v` | V | 1.020852–1.025424 | 1.026383–1.067796 |
| `recovery_load_v` | V | 0.002639145–0.005987694 | 0.005166428–0.02089693 |
| `recovery_release_v` | V | 0.002086921–0.008601531 | 0.002874725–0.008467015 |
| `mean_power_w` | W | 0.0003549922–0.001164775 | 0.0003538111–0.001163427 |
| `startup_error_v` | V | 0.00217294–0.008335321 | 0.00400122–0.01461069 |
| `startup_peak_v` | V | 0.9970235–1.018812 | 0.9853964–1.017846 |
| `startup_minimum_v` | V | 2.09718e-06–2.438187e-05 | 2.756605e-07–3.005093e-06 |
| `regulation_floor_v` | V | 0.9730788–0.9917698 | 0.9996434–1.171609 |
| `headroom_v` | V | 0.0030788–0.0217698 | 0.0296434–0.201609 |
| `line_span_v` | V | 0.000541–0.0008117 | 0.000512–0.0115839 |
| `load_span_v` | V | 0.0100067–0.0113595 | 0.0113922–0.0234888 |
| `fast_peak_v` | V | 0.0002317423–0.0004908346 | 0.0001864905–0.0002222358 |
| `fast_tail_v` | V | 6.278331e-08–1.788685e-07 | 9.042496e-08–2.454448e-07 |

### Return-ratio diagnosis and scope

At the 1.2 V / 0.1 mA operating point, the voltage-only ratio crosses unity
again near 471 MHz, where the bilateral ratio is about −49 dB. Port impedance
division dominates the old result; reverse active transmission alone does not
explain it. Two independent voltage/current injections preserve loading.
Independent reconstruction of the two-port Y matrix from saved terminal
voltages/currents agrees with the implemented return ratio.

This correction does **not** remove all high-frequency crossings. At 1.3 V,
the extracted circuit has three unity crossings: parasitic peaking creates
an ascending crossing around 26–30 MHz and a final descending crossing at
50.42/76.39 MHz, with final phase margins 82.11/75.92 degrees. At 1.2 V,
there is one crossing around 0.50–0.69 MHz. The minimum sampled `|1+T|`
exceeds 0.50 across all four cases, and the return-difference phase excursion
stays below 81 degrees. The final-crossing, return-distance, full-sweep phase
and high-frequency attenuation requirements prevent acceptance based only on
the first descending crossover. A voltage-only failure probe is provided below.

Qualification is a finite external-loop frequency screen plus observed
large/fast recovery, not an exhaustive proof of all internal poles. It covers
typical models at 27 C, 1.2/1.3 V supply, a 0.5 V reference and the specified
loads/startup ramps. It does not establish arbitrary sequencing, PVT, RF model
accuracy, noise, or precision-reference performance. A pole-zero trial did not
provide a reliable exhaustive pole inventory and is not used as a certificate.

### Numerical and boundary checks

The calibration recipes below halve maximum main/startup/fast steps to
0.5 ns / 1 ns / 2.5 ps. A separate run tightens reltol/abstol/vntol tenfold,
raises rshunt to 1e13 ohm, doubles AC density and halves DC increments.
The fast tests additionally compare Gear and trapezoidal integration. A
200 us single-load-pulse probe checks both source and extracted circuits,
including sustained recovery over 100–195 us, without repeating the load pulse.
These are finite observable recovery checks; no hidden internal servo is used.

All calibration variants pass. Independent saved-waveform recomputation checks
608 observations across 92 source/reference/numerical jobs, including two-port
reconstruction and interpolated recovery endpoints. Using the same frozen RC
as the reference, the largest half-step change in the load-step minimum is
0.513 mV; the tighter run changes it by 0.598 mV. Tightening changes final
phase margin by at most 0.00257 degrees, final crossover by 920 Hz, and sampled
high-frequency maximum by 0.09553 dB. DC span/floor changes stay at or below
1.1 uV. Gear/trapezoidal fast-peak differences stay below 4.1 nV, with fast tails
below 0.246 uV. Sustained 100–195 us errors remain below 8.36 mV in source and
7.86 mV after extraction. These changes preserve every fixed acceptance bound.

Transient extrema are sampled window maxima/minima. Independent recomputation
also checks interpolated recovery-window endpoints. For example, the first
nominal RC condition differs by about 0.33 uV at 13 us; acceptance is unchanged. DC extrema printed by ngspice are
rounded before subtraction, so independent span recomputation accounts for
that rounding while checking the full sweep endpoints.

The initial draft's 300 uV fast-peak limit was corrected to 600 uV during
source/RC calibration: source peaks reach approximately 491 uV versus 222 uV
after extraction. The 2 uV fast-tail limit remains fixed. The regulation-floor
lower bound is 0.97 V because crossing output is approximately 0.97 V; an initial
0.98 V lower bound incorrectly rejected better source headroom. Neither change
alters stimulus, compensation or simulation tolerances. The maintained circuit
changes relative to the upstream source are disclosed in the overview/problem.


## Reproduce

These operator commands require the installed `ICLayout-Bench-Private` package.
Run preparation from the Public checkout; run any `tests/integration/` commands
from the Private checkout using that environment.

From the repository root use the [shared tools](../../../../../docs/tools.md#manual-tools).
Commands generate the reader's own resources, candidate RC and reports under
`build/runs/`. Use fresh output paths; reuse the verified tool image.

```bash
python -m layout_eval.preview prepare \
  --case ldo_008_fer_mirror_ota --image iclayout-bench-tools:local \
  --output build/runs/ldo_008_fer_mirror_ota-prepared
python -m layout_eval.preview run \
  --prepared build/runs/ldo_008_fer_mirror_ota-prepared \
  --output build/runs/ldo_008_fer_mirror_ota-reference
python -m pytest tests/integration/test_public_references.py \
  -k ldo_008_fer_mirror_ota
```

After preview, run the following source/numerical and boundary probes using
its frozen inputs and candidate RC. All acceptance bounds stay fixed. The final
`voltage-only` experiment is intentionally expected to fail high-frequency
attenuation: it restores the invalid raw voltage-ratio measurement while
preserving the same circuit and operating conditions. These commands generate
new reports and require no maintainer output directory.

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

case = Path('build/runs/ldo_008_fer_mirror_ota-prepared/case/case.toml')
reference = Path('build/runs/ldo_008_fer_mirror_ota-reference/reference')
task = load_task(case)
report = json.loads((reference / 'report.json').read_text())
assert report['task_success']
rc = Asset((reference / report['jobs']['parasitics']['outputs']['netlist']['path']).read_bytes(), 'spice')
base = tomllib.loads(case.read_text())['task']['evaluation']
for variant in ('source', 'half-step', 'tight', 'trap', 'long-source', 'long', 'voltage-only'):
    plan = copy.deepcopy(base)
    plan['mode'] = 'characterization'
    plan.pop('scoring')
    plan['jobs'] = [j for j in plan['jobs'] if j['stage'] == 'simulate']
    plan['metrics'] = [m for m in plan['metrics'] if m['category'] == 'performance']
    for job in plan['jobs']:
        job['inputs']['dut'] = 'input:simulation'
    for metric in plan['metrics']:
        for key in ('dimension', 'zero_lower', 'zero_upper'):
            metric.pop(key, None)
    inputs = task.evaluation_inputs()
    if variant not in ('source', 'long-source'):
        inputs['input:simulation'] = rc
    for role in ('performance', 'startup', 'sweeps', 'fast'):
        deck = inputs['input:' + role].content.decode()
        if variant == 'half-step':
            deck = deck.replace('tran 1n 18u 0 1n', 'tran 0.5n 18u 0 0.5n')
            deck = deck.replace('tran 2n 30u 0 2n', 'tran 1n 30u 0 1n')
            deck = deck.replace('tran 5p 100n 0 5p', 'tran 2.5p 100n 0 2.5p')
        if variant == 'tight':
            deck = deck.replace('rshunt=1e12 reltol=1e-5 abstol=1e-14 vntol=1e-8',
                                'rshunt=1e13 reltol=1e-6 abstol=1e-15 vntol=1e-9')
            deck = deck.replace('ac dec 300', 'ac dec 600')
            deck = deck.replace('dc VDD 1.3 0.8 -0.001', 'dc VDD 1.3 0.8 -0.0005')
            deck = deck.replace('dc ILOAD 0.0001 0.001 0.00001',
                                'dc ILOAD 0.0001 0.001 0.000005')
        if variant == 'trap':
            deck = deck.replace('method=gear', 'method=trap')
        if variant.startswith('long'):
            deck = deck.replace('8u 16u)', '8u 1m)')
            deck = deck.replace('tran 1n 18u 0 1n', 'tran 10n 200u 0 10n')
            deck = deck.replace('from=2u to=18u', 'from=2u to=200u')
            deck = deck.replace('from=13u to=17.5u', 'from=100u to=195u')
        if variant == 'voltage-only':
            deck = deck.replace('let transfer=(2*delta-aa+dd)/denominator',
                                'let transfer=ac1.oldratio')
        inputs['input:' + role] = Asset(deck.encode(), 'spice')
    if variant.startswith('long') or variant == 'voltage-only':
        plan['jobs'] = [j for j in plan['jobs'] if j['id'].startswith('condition_')]
        plan['metrics'] = [m for m in plan['metrics']
                           if all(x.startswith('condition_') for x in m['observations'])]
    if variant == 'trap':
        plan['jobs'] = [j for j in plan['jobs'] if j['id'].startswith('fast_')]
        plan['metrics'] = [m for m in plan['metrics'] if m['id'].startswith('fast_')]
    result = run_evaluation(
        parse_evaluation(json.dumps(plan).encode(), file_format='json'),
        inputs, load_toolchain(case), Path('build/runs') / ('ldo_008_fer_mirror_ota-' + variant),
    )
    if variant == 'voltage-only':
        assert result['outcome'] == 'failed'
        assert result['metrics']['hf_gain_db']['status'] == 'failed'
    else:
        assert result['outcome'] == 'passed', result
PYCODE
```

## Source and License

Derived from [the fixed analog-db snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_008_fer_mirror_ota).
Normalized derivatives and witness retain PolyForm Noncommercial terms and
the Required Notice; the snapshot records Token Zhang / Arcadia-1 ferrosim MIT
attribution. Its original notice was not independently retrieved. See collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). Independently authored
measurement decks are MIT.

The two-injection expression follows Eq. (30) of [Tian et al., 2001](https://kenkundert.com/docs/cd2001-01.pdf).
Its sign convention here uses `if = −I(VPROBE)` and `ve = V(SENSE)`.
