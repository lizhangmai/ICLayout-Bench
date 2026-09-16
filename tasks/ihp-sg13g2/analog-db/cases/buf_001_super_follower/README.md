> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# MIM-Compensated Local-Feedback Source Follower

## Overview

Six MOS entries expand to 17 physical MOS instances in a local-feedback source follower. Fixed IHP W/L/m are retained. The internal na-to-VSS 250 fF compensation is implemented as a 12.85 by 12.85 um cap_cmim (nominally 249.74 fF at 27 C, including model perimeter capacitance); it is not removed or moved to the output. Explicit physical taps and the MIM dimensions are common to LVS, source simulation and extracted simulation.

VDD = 1.5 V; VSS = 0 V; a 20 uA current source from VDD into ibias. VIN = 0.55 V DC, AC amplitude 1 V. External output loads are 5, 10 and 20 pF. AC uses 100 points/decade from 1 Hz to 1 GHz. VIN stays at 0.55 V through 1 us, ramps to 0.65 V at 1.001 us, holds through 3 us, ramps back at 3.001 us and holds through 5 us. Transient output/max step is 0.2 ns. Recovered errors compare output to its 2.5 us and 0.5 us samples, over 1.5–2.9 us and 3.5–4.9 us respectively. This is a level-shifting source follower with about 0.84 small-signal gain, not a unity-gain rail-to-rail buffer. Qualification is restricted to the stated low-input range; higher input bias compresses the gain. Noise, mismatch, other input levels, PVT and RF/EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.cdl](materials/circuit.cdl) | Authoritative physical circuit |
| [materials/circuit.spice](materials/circuit.spice) | Equivalent simulator representation |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/buf_001_super_follower.gds](reference/buf_001_super_follower.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

Reference functional area: 4928.6770 um2. The independent witness passes artifact, IHP main and maximal DRC, with density and antenna outside this standalone scope; strict named-port LVS; geometry, candidate-derived distributed RC and all 27 electrical observations. No DRC waivers are used.

Ranges below cover all 3 declared conditions. Both columns use the same maintained testbench; they are nominal calibration, not statistical accuracy claims.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.13800078 | 0.1373654 |
| `bias_v` | V | 0.39406997 | 0.39915676 |
| `power_w` | W | 0.00034650957 | 0.00033967943 |
| `gain_vv` | V/V | 0.8375134 | 0.8370302 |
| `bandwidth_hz` | Hz | 1.986676e+08 to 4.328583e+08 | 1.737159e+08 to 3.822466e+08 |
| `step_gain` | V/V | 0.833601 | 0.833981 |
| `recovery_up_v` | V | 3.65123e-08 to 3.651418e-08 | 5.77449e-09 to 5.775515e-09 |
| `recovery_down_v` | V | 1.619487e-08 to 1.62009e-08 | 3.044659e-09 to 3.045383e-09 |
| `mean_power_w` | W | 0.0003466058 to 0.0003466118 | 0.0003397777 to 0.0003397826 |

A coefficient of 5 reflects local feedback, internal compensation and loaded transient behavior. Targets require 0.78–0.90 small/large-signal gain, at least 20 MHz bandwidth, 100 uV recovered step error and 400 uW supply power. Acceptance and zero-score boundaries are calibrated against independent source/RC measurements, not upstream scoreboards. Area target 5500 um2 and zero-utility budget 22000 um2 are fixed absolute anchors supported by the witness, not changing reference-area ratios or claimed optima. Typical IHP low-voltage MOS and resistor models and typical capacitor models; explicit finite physical tap models and a 1e12 ohm ngspice numerical shunt at each node. Candidate Magic RC is extracted with zero coupling-capacitance threshold. Fabrication signoff is outside scope.

Halving the transient step from 0.2 to 0.1 ns preserves all limits. Step gain and average power are unchanged at reported precision; recovered-error changes are below 11 pV. These tiny residual differences are numerical, not an accuracy guarantee.

## Reproduce

From the repository root, follow the [shared tool preparation](../../../../../docs/tools.md#manual-tools), then prepare/reuse this case's profiles:

```bash
python -m layout_eval.prepare_support   third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#klayout build/support/input-pair-klayout
python -m layout_eval.prepare_support   third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#magic build/support/input-pair-magic
python -m layout_eval.prepare_support   third_party/IHP-Open-PDK tasks/ihp-sg13g2/pdk.toml#analog-models build/support/input-pair-models
python -m layout_eval.cli evaluate \
  tasks/ihp-sg13g2/analog-db/cases/buf_001_super_follower/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/buf_001_super_follower/reference/buf_001_super_follower.gds \
  --output build/runs/analog-db-buf_001_super_follower-reference
uv run --locked --group eda pytest tests/integration/test_public_references.py -k buf_001_super_follower
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

source = Path("tasks/ihp-sg13g2/analog-db/cases/buf_001_super_follower")
copy = Path("build/runs/analog-db-buf_001_super_follower-half-case")
shutil.copytree(source, copy)  # destination must be new
config = copy / "case.toml"
data = tomllib.loads(config.read_text())
entry = data["task"]["inputs"]["performance"]
deck = copy / entry["path"]
text = deck.read_text()
assert "tran 0.2n" in text
deck.write_text(text.replace("tran 0.2n", "tran 0.1n"))
entry["sha256"] = hashlib.sha256(deck.read_bytes()).hexdigest()
data["status"] = "candidate"
config.write_text(tomli_w.dumps(data))
PYCODE
python -m layout_eval.cli evaluate \
  build/runs/analog-db-buf_001_super_follower-half-case/case.toml \
  build/runs/analog-db-buf_001_super_follower-half-case/reference/buf_001_super_follower.gds \
  --output build/runs/analog-db-buf_001_super_follower-half-reference
```

Retain collection LICENSE and NOTICE with material distributions. They, the reference, source records and host configuration stay outside declared solver inputs.

## Source and License

Derived from [MacAnalog analog-db buf_001_super_follower](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/buf_001_super_follower), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
