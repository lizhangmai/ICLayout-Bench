> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Differential Polarity-Commutating Switch

## Overview

Eight MOS devices form four transmission paths that connect a differential input directly or with reversed polarity. The two complementary clock nets are independent layout ports. Fixed IHP W/L/m are retained; explicit substrate/well taps are included in both maintained circuit representations.

VDD = 1.5 V; VSS = 0 V; input common mode = 0.75 V; differential input = -0.2 or +0.2 V. Each output has an external 10 kohm resistor to common mode and 1 pF to ground. DC checks both clock states (vctl = 0 or 1.5 V), giving four conditions. Transient clocks are complementary 0/1.5 V pulses, delay 1 us, rise/fall 2 ns, high width 5 us and period 10 us; output/max step is 0.1 ns with Gear order 2, stop time 12 us. A second transient sets both inputs to 0.75 V to separate clock feedthrough/injection from signal reversal. The finite clock slopes deliberately permit overlap; non-overlap operation is not claimed.  Ron includes the declared terminal loading and common mode. Injection is net terminal charge integrated under driven equal inputs, not stored charge on a disconnected sampler. Noise, chopping an amplifier, RF/EM, mismatch and other clock rates are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical circuit |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/sw_002_chopper_diff.gds](reference/sw_002_chopper_diff.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

Reference functional area: 2279.4777 um2. The independent witness passes artifact, IHP main and maximal DRC, with density and antenna outside this standalone scope; strict named-port LVS; geometry, candidate-derived distributed RC and all 40 electrical observations. No DRC waivers are used.

Ranges below cover all 4 declared conditions. Both columns use the same maintained testbench; they are nominal calibration, not statistical accuracy claims.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `ron_p` | ohm | 812.8557 to 1388.0725 | 868.76251 to 1428.376 |
| `ron_n` | ohm | 812.8557 to 1388.0725 | 868.7477 to 1424.1957 |
| `transfer` | V/V | 0.90146839 | 0.89721643 to 0.89798143 |
| `common_error_v` | V | 0.0023356672 | 0.0021881282 to 0.0022202732 |
| `straight_gain` | V/V | 0.9014684 | 0.8972164 to 0.8972177 |
| `crossed_gain` | V/V | -0.9014684 | -0.8979814 to -0.8979807 |
| `common_glitch_v` | V | 1.35409e-05 | 0.000676535 |
| `differential_glitch_v` | V | 3.219647e-15 | 0.00108759 |
| `input_charge_c` | C | 3.422271e-18 | 1.123403e-15 |
| `clock_power_w` | W | 2.250818e-09 | 8.067328e-09 |

A coefficient of 5 reflects dynamic differential commutation and clock-to-signal parasitics. Targets require both transmission signs, Ron below 1.6 kohm, differential gain at least 0.88, bounded clock glitches and at most 3 fC net input charge in the specified edge window. Acceptance and zero-score boundaries are calibrated against independent source/RC measurements, not upstream scoreboards. Area target 2500 um2 and zero-utility budget 10000 um2 are fixed absolute anchors supported by the witness, not changing reference-area ratios or claimed optima. Typical IHP low-voltage MOS and resistor models; explicit finite physical tap models and a 1e12 ohm ngspice numerical shunt at each node. Candidate Magic RC is extracted with zero coupling-capacitance threshold. Fabrication signoff is outside scope.

Halving the transient step from 0.1 to 0.05 ns preserves all limits. Maximum changes are 7.48 uV in differential glitch, 0.0106 fC in input charge and 0.0194 nW in supplied clock power (less than 1% of each nominal value). Gear order 2 and positive supplied energy are explicit parts of the contract; returned clock energy is not credited.

## Reproduce

From the repository root, follow the [shared tool preparation](../../../../../docs/tools.md#manual-tools), then prepare/reuse this case's profiles:

```bash
python -m layout_eval.prepare_support   third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#klayout build/support/input-pair-klayout
python -m layout_eval.prepare_support   third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#magic build/support/input-pair-magic
python -m layout_eval.prepare_support   third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#analog-models build/support/input-pair-models
python -m layout_eval.cli evaluate \
  tasks/ihp-sg13g2/analog-db/cases/sw_002_chopper_diff/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/sw_002_chopper_diff/reference/sw_002_chopper_diff.gds \
  --output build/runs/analog-db-sw_002_chopper_diff-reference
uv run --locked --group eda pytest tests/integration/test_public_references.py -k sw_002_chopper_diff
```

Reuse verified support destinations; preparation refuses an existing directory. These commands generate the reader's reports/waveforms under `build/runs/`; choose fresh output directories. The catalog regression accepts the reference and rejects an empty layout.

Reproduce Pre-layout with the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration), replacing its case/output paths with this case and a fresh run directory. For this two-representation case, set `job["inputs"]["dut"] = "input:simulation"` in that recipe; native CDL remains the physical LVS input. The characterization keeps every condition and does not produce a layout score.


Reproduce the step-halving check without changing the maintained case. This
creates a local case snapshot with a new deck digest;
it evaluates the same witness and every declared condition:

```bash
uv run --locked python - <<'PYCODE'
import hashlib
import shutil
import tomllib
from pathlib import Path
import tomli_w

source = Path("tasks/ihp-sg13g2/analog-db/cases/sw_002_chopper_diff")
copy = Path("build/runs/analog-db-sw_002_chopper_diff-half-case")
shutil.copytree(source, copy)  # destination must be new
config = copy / "case.toml"
data = tomllib.loads(config.read_text())
entry = data["task"]["inputs"]["performance"]
deck = copy / entry["path"]
text = deck.read_text()
assert "tran 0.1n" in text
deck.write_text(text.replace("tran 0.1n", "tran 0.05n"))
entry["sha256"] = hashlib.sha256(deck.read_bytes()).hexdigest()
data["status"] = "candidate"
config.write_text(tomli_w.dumps(data))
PYCODE
python -m layout_eval.cli evaluate \
  build/runs/analog-db-sw_002_chopper_diff-half-case/case.toml \
  build/runs/analog-db-sw_002_chopper_diff-half-case/reference/sw_002_chopper_diff.gds \
  --output build/runs/analog-db-sw_002_chopper_diff-half-reference
```

Retain collection LICENSE and NOTICE with material distributions. They, the reference, source records and host configuration stay outside declared solver inputs.

## Source and License

Derived from [MacAnalog analog-db sw_002_chopper_diff](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sw_002_chopper_diff), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
