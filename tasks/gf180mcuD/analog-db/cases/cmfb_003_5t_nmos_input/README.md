> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Segmented-Resistor NMOS Common-Mode Controller

## Overview

Seven MOS devices form an NMOS-input common-mode error amplifier and self-bias network. Each ideal 5 Mohm sense arm is implemented as twenty series GF180 ppolyf_u_1k segments, each 2 um wide and 500 um long: 5,000 squares per arm. The segmentation, substrate terminals and intermediate nodes are part of the maintained circuit. The independent witness uses compact rows connected by metal; it retains both complete resistance chains.

VDD = 3.3 V; VSS = 0 V; VREF = 1.65 V. The external first-order inverting plant has drive = 3.3 V - V(vcmfb), followed by 100 kohm and 100 nF to common mode. V(vinp/vinn) = plant output + disturbance +/- d, where d = 0, 0.1 and 0.2 V in separate conditions. Disturbance is 0 through 10 ms, +0.1 V at 10.01 ms through 30 ms, -0.1 V at 30.01 ms through 50 ms, and 0 at 50.01 ms through 70 ms. A 10 pF external capacitor loads vcmfb. Transient output/max step is 10 us. This plant is test apparatus, not an internal ideal servo or a claimed transistor amplifier. Recovery windows are 25–29 ms and 45–49 ms for the positive/negative disturbances; error is measured at the average sensed inputs against VREF. Controller power excludes the external plant. Qualification covers recovery with this specified external plant, not stability with arbitrary amplifiers. The long physical sense chains retain candidate-derived parasitics. Startup, mismatch, noise, PVT and a complete differential amplifier are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative physical circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/cmfb_003_5t_nmos_input.gds](reference/cmfb_003_5t_nmos_input.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

Reference functional area: 266260.9950 um2. The independent witness passes artifact, GF180 variant-D DRC including antenna, with chip-level density and seal-ring closure outside scope; strict named-port LVS; geometry, candidate-derived distributed RC and all 24 electrical observations. No DRC waivers are used.

Ranges below cover all 3 declared conditions. Both columns use the same maintained testbench; they are nominal calibration, not statistical accuracy claims.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 1.6521036 | 1.6519569 to 1.6519574 |
| `error_v` | V | 0.0021036363 to 0.0021036363 | 0.0019568884 to 0.0019574266 |
| `power_w` | W | 0.00016284625 | 0.00016202185 |
| `recovery_up_v` | V | 0.001780462 | 0.001634297 to 0.001634836 |
| `recovery_down_v` | V | 0.002431036 | 0.00228474 to 0.002285278 |
| `recovery_zero_v` | V | 0.002103118 | 0.001956893 to 0.001957431 |
| `peak_error_v` | V | 0.2011193 | 0.200973 to 0.2009735 |
| `mean_power_w` | W | 0.0001628409 | 0.0001620166 |

A coefficient of 6 reflects interacting physical sensing, feedback and recovery requirements. The targets require at most 3 mV steady/recovered common-mode error, 220 mV peak disturbance error and 180 uW controller power; external plant power is not controller power. Acceptance and zero-score boundaries are calibrated against independent source/RC measurements, not upstream scoreboards. Area target 280000 um2 and zero-utility budget 1120000 um2 are fixed absolute anchors supported by the witness, not changing reference-area ratios or claimed optima. Typical GF180 3.3 V MOS and high-resistance poly models, statistical variation disabled. The substrate is not a distributed silicon resistance network. Fabrication signoff is outside scope.

Halving the transient step from 10 to 5 us preserves all limits. The largest peak-error change is 12.3 uV; recovered errors are unchanged at reported precision and average controller power changes by at most 0.1 nW.

## Reproduce

From the repository root, follow the [shared tool preparation](../../../../../docs/tools.md#gf180), then prepare/reuse this case's profiles:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/cmfb_003_5t_nmos_input/case.toml \
  tasks/gf180mcuD/analog-db/cases/cmfb_003_5t_nmos_input/reference/cmfb_003_5t_nmos_input.gds \
  --output build/runs/analog-db-cmfb_003_5t_nmos_input-reference
uv run --locked --group eda pytest tests/integration/test_public_references.py -k cmfb_003_5t_nmos_input
```

Reuse verified support destinations; preparation refuses an existing directory. These commands generate the reader's reports/waveforms under `build/runs/`; choose fresh output directories. The catalog regression accepts the reference and rejects an empty layout.

Reproduce Pre-layout with the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration), replacing its case/output paths with this case and a fresh run directory. The characterization keeps every condition and does not produce a layout score.


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

source = Path("tasks/gf180mcuD/analog-db/cases/cmfb_003_5t_nmos_input")
copy = Path("build/runs/analog-db-cmfb_003_5t_nmos_input-half-case")
shutil.copytree(source, copy)  # destination must be new
config = copy / "case.toml"
data = tomllib.loads(config.read_text())
entry = data["task"]["inputs"]["performance"]
deck = copy / entry["path"]
text = deck.read_text()
assert "tran 10u" in text
deck.write_text(text.replace("tran 10u", "tran 5u"))
entry["sha256"] = hashlib.sha256(deck.read_bytes()).hexdigest()
data["status"] = "candidate"
config.write_text(tomli_w.dumps(data))
PYCODE
python -m layout_eval.cli evaluate \
  build/runs/analog-db-cmfb_003_5t_nmos_input-half-case/case.toml \
  build/runs/analog-db-cmfb_003_5t_nmos_input-half-case/reference/cmfb_003_5t_nmos_input.gds \
  --output build/runs/analog-db-cmfb_003_5t_nmos_input-half-reference
```

Retain collection LICENSE and NOTICE with material distributions. They, the reference, source records and host configuration stay outside declared solver inputs.

## Source and License

Derived from [MacAnalog analog-db cmfb_003_5t_nmos_input](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmfb_003_5t_nmos_input), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
