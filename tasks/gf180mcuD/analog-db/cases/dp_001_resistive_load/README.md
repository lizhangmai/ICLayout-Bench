> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Resistively Loaded Differential Pair

## Overview

Four NMOS devices form a differential input pair and tail-current mirror. Two physical GF180 ppolyf_u_1k loads each have width 2 um and length 44 um (22 squares, nominally 22 kohm). MOS dimensions and the resistor ratio follow the fixed binding; the ideal source resistors become process devices with substrate terminals at VSS.

VDD = 3.3 V, VSS = 0 V; 20 uA from VDD into ibias; input common mode = 1.2, 1.65 and 2.1 V; external 1 pF on each output. The input differential signal is split +0.5/-0.5 around common mode. AC differential amplitude is 1 V. DC transfer sweeps differential input from -10.1 to +10.1 mV in 0.1 mV increments; requirements use only -10 to +10 mV. Output differential voltage is V(voutn)-V(voutp). The output has a high common-mode level; it is not a rail-to-rail amplifier. Transient settling, mismatch, noise, PVT and EM are outside scope.

## Files

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver-facing contract and scoring |
| [case.toml](case.toml) | Inputs, physical checks, RC extraction and three simulation conditions |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative fixed circuit and source-calibration DUT |
| [materials/testbench.spice](materials/testbench.spice) | Shared source/post-layout measurement deck |
| [reference/dp_001_resistive_load.gds](reference/dp_001_resistive_load.gds) | Independently constructed witness, excluded from solver inputs |

## Reference Results

The reference functional area is 6016.8349 um2. It passes artifact, GF180 variant-D DRC including antenna without
waivers, strict named-port LVS, geometry, distributed RC extraction and all
24 required electrical observations. The table gives ranges over all three
declared conditions; temperature extrema and comparator transient windows are
defined in the problem. Both columns use the same maintained testbench.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 2.9949753 to 3.0889733 | 2.9955457 to 3.0886041 |
| `imbalance_v` | V | 5.5067062e-14 to 6.3504757e-14 | 0.00011469437 to 0.00018880337 |
| `bias_v` | V | 0.63335378 to 0.63335378 | 0.63414911 to 0.63421696 |
| `power_w` | W | 0.00012824943 to 0.00015597732 | 0.00012819085 to 0.00015556783 |
| `gain_db` | dB | 10.89406 to 12.94184 | 10.87388 to 12.89242 |
| `bandwidth_hz` | Hz | 7805460 to 8235992 | 7578490 to 7990155 |
| `linearity_v` | V | 1.820086e-05 to 2.070048e-05 | 1.817173e-05 to 2.064105e-05 |
| `slope` | V/V | 3.499673 to 4.432213 | 3.491636 to 4.407118 |

The targets define at least 10 dB differential gain, 7 MHz bandwidth, at most 100 uV endpoint-line error across a 20 mV input span, 2 mV output imbalance and a 180 uW DC budget. The coefficient is 4 for a biased differential block with physical matched loads. Acceptance and zero-score bands are calibrated against these nominal
source/RC measurements, rather than inherited from upstream targets. The
absolute area budget is 6500 um2, verified feasible by this witness; area utility
reaches zero at 26000 um2. These frozen budgets do not depend on a submitted
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
  tasks/gf180mcuD/analog-db/cases/dp_001_resistive_load/case.toml \
  tasks/gf180mcuD/analog-db/cases/dp_001_resistive_load/reference/dp_001_resistive_load.gds \
  --output build/runs/analog-db-dp_001_resistive_load-reference
```

This generates the reader's identity-bound report and raw waveforms in the
selected output directory; use a fresh directory for every execution. Reproduce
the Pre-layout column using the shared
[source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration),
with this case path and a fresh `build/runs/analog-db-dp_001_resistive_load-source` destination.
That recipe keeps all three conditions and replaces only the extracted DUT
with the published source netlist; characterization is not a layout score.

```bash
uv run --locked --group eda pytest tests/integration/test_public_references.py \
  -k dp_001_resistive_load
```

The catalog-driven checks evaluate the witness and reject an empty layout.
Retain collection LICENSE and NOTICE with distributions; they are outside the
three declared solver inputs. Prepared solves are not redistribution packages.

## Source and License

Derived from [MacAnalog analog-db dp_001_resistive_load](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/dp_001_resistive_load), under the retained [collection license](../../LICENSE) and [notices](../../NOTICE).
