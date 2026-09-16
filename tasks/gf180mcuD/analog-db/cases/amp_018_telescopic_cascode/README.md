> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Tail-Referenced Telescopic Cascode Amplifier

## Overview

Ten MOS devices form an NMOS-input telescopic cascode amplifier. Fixed upstream W/L/m are retained, including the single finger of XM5. The two ideal internal sources become external bias connections: VDD minus gate_pc is 1.143 V, and casc_n minus tail is 0.917 V. Exposing tail preserves the second source's relative bias instead of replacing it with an absolute ground-referenced voltage.

VDD = 3.3 V; VSS = 0 V; a 20 uA current source from VDD into ibias. VINP is 1.65 V DC with AC amplitude +0.5 V; VINN has DC output feedback through a 1 TH inductor and AC -0.5 V through a 1 F coupling capacitor. These ideal measurement elements are external apparatus. Output loads are 1, 3 and 5 pF. AC uses 100 points/decade from 1 Hz to 1 GHz and transfer V(vout)/(V(vinp)-V(vinn)).  The declared bias gives about 15 dB gain; this is not a high-gain OTA qualification. Large-signal settling, noise, mismatch, other biases and PVT are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Solver contract and scoring |
| [case.toml](case.toml) | Inputs, tool bindings, constraints and evaluation |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative physical circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source/post-layout measurements |
| [reference/amp_018_telescopic_cascode.gds](reference/amp_018_telescopic_cascode.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

Reference functional area: 10300.2200 um2. The independent witness passes artifact, GF180 variant-D DRC including antenna, with chip-level density and seal-ring closure outside scope; strict named-port LVS; geometry, candidate-derived distributed RC and all 21 electrical observations. No DRC waivers are used.

Ranges below cover all 3 declared conditions. Both columns use the same maintained testbench; they are nominal calibration, not statistical accuracy claims.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 1.7459291 | 1.7453759 |
| `bias_v` | V | 0.79373017 | 0.79463622 |
| `tail_v` | V | 0.57707779 | 0.57500994 |
| `power_w` | W | 0.00010464449 | 0.0001047761 |
| `gain_db` | dB | 15.53969 | 15.39755 |
| `unity_hz` | Hz | 101230.5 to 503431.9 | 98648.65 to 481537.6 |
| `phase_margin` | deg | 99.22954 to 99.5422 | 99.34666 to 99.69217 |

A coefficient of 5 reflects independently supplied cascode branches and their internal parasitics. The electrical targets require 14 dB gain, 90 kHz unity crossing, 80-degree phase margin and 130 uW power across the declared loads. Acceptance and zero-score boundaries are calibrated against independent source/RC measurements, not upstream scoreboards. Area target 11000 um2 and zero-utility budget 44000 um2 are fixed absolute anchors supported by the witness, not changing reference-area ratios or claimed optima. Typical GF180 3.3 V MOS and high-resistance poly models, statistical variation disabled. The substrate is not a distributed silicon resistance network. Fabrication signoff is outside scope.

## Reproduce

From the repository root, follow the [shared tool preparation](../../../../../docs/tools.md#gf180), then prepare/reuse this case's profiles:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/amp_018_telescopic_cascode/case.toml \
  tasks/gf180mcuD/analog-db/cases/amp_018_telescopic_cascode/reference/amp_018_telescopic_cascode.gds \
  --output build/runs/analog-db-amp_018_telescopic_cascode-reference
uv run --locked --group eda pytest tests/integration/test_public_references.py -k amp_018_telescopic_cascode
```

Reuse verified support destinations; preparation refuses an existing directory. These commands generate the reader's reports/waveforms under `build/runs/`; choose fresh output directories. The catalog regression accepts the reference and rejects an empty layout.

Reproduce Pre-layout with the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration), replacing its case/output paths with this case and a fresh run directory. The characterization keeps every condition and does not produce a layout score.

Retain collection LICENSE and NOTICE with material distributions. They, the reference, source records and host configuration stay outside declared solver inputs.

## Source and License

Derived from [MacAnalog analog-db amp_018_telescopic_cascode](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_018_telescopic_cascode), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
