> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Self-Biased Cascode Common-Source Gain Stage

## Overview

Nine MOS devices form a cascode common-source stage with PMOS and NMOS bias ladders. An external 20 uA sink biases the PMOS ladder. Total widths, lengths and multiplicities follow the fixed GF180 binding. Physical body contacts and an independently constructed reference complete the circuit.

VSS = 0 V; VDD = 2.7, 3.0 and 3.3 V; external 20 uA sink from ibias to VSS; external 1 pF output load. A 1 TH external inductor connects output to input for the DC trip-point solve. A 1 F external coupling capacitor injects a unit AC input through acin while isolating the DC fixture. This measures open-loop small-signal gain at each self-biased trip point; it does not prescribe a fixed DC input voltage. Transient settling, fixed-input bias robustness, noise, mismatch, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/gs_001_cascode_cs.gds](reference/gs_001_cascode_cs.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

The reference functional area is 6604.7250 um2. It passes artifact, GF180 variant-D DRC including antenna without
waivers, strict named-port LVS, geometry, distributed RC extraction and all
15 required electrical observations. The table gives ranges over all three
declared conditions; temperature extrema and comparator transient windows are
defined in the problem. Both columns use the same maintained testbench.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.7190888 to 0.71915119 | 0.71939485 to 0.71946533 |
| `bias_v` | V | 0.47188213 to 1.0718821 | 0.4708446 to 1.0708449 |
| `power_w` | W | 0.00015931166 to 0.00019988954 | 0.0001592135 to 0.0001998065 |
| `gain_db` | dB | 33.3961 to 33.66256 | 33.36375 to 33.63149 |
| `bandwidth_hz` | Hz | 521841.2 to 538586.7 | 506604.7 to 522916.8 |

The targets define a 30 dB gain stage with at least 450 kHz bandwidth and a 220 uW DC power budget at its trip point. The coefficient is 4 for a complete compact cascode stage with bias ladders and a load. Acceptance and zero-score bands are calibrated against these nominal
source/RC measurements, rather than inherited from upstream targets. The
absolute area budget is 7000 um2, verified feasible by this witness; area utility
reaches zero at 28000 um2. These frozen budgets do not depend on a submitted
layout, a changing reference-area ratio or model population. The witness is
not an area optimum. Physical area and the final evaluation score are reported
by the reproduction command below.

The extracted RC network and device geometry come from the reference GDS.
Finite substrate resistance, process/statistical corners and fabrication
signoff are outside this nominal physical/simulation boundary.

## Reproduce

From the repository root, prepare the image and shared verified bundles using
the [GF180 instructions](../../../../../docs/tools.md#gf180), then run:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/analog-db/cases/gs_001_cascode_cs/case.toml \
  tasks/gf180mcuD/analog-db/cases/gs_001_cascode_cs/reference/gs_001_cascode_cs.gds \
  --output build/runs/analog-db-gs_001_cascode_cs-reference
```

This generates the reader's identity-bound report and raw waveforms in the
selected output directory; use a fresh directory for every execution. Reproduce
the Pre-layout column using the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration),
with this case path and a fresh `build/runs/analog-db-gs_001_cascode_cs-source` destination.
That recipe keeps all three conditions and replaces only the extracted DUT
with the published source netlist; characterization is not a layout score.

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k gs_001_cascode_cs
```

The catalog-driven checks evaluate the witness and reject an empty layout.
Retain collection LICENSE and NOTICE with distributions; they are outside the
three declared solver inputs. Prepared solves are not redistribution packages.

## Source and License

Derived from [MacAnalog analog-db gs_001_cascode_cs](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/gs_001_cascode_cs), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
