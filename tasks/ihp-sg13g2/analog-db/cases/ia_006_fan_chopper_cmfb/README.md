> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

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

[Analog Canvas schematic](materials/schematic.svg) is a maintainer-only result
browsing asset, excluded from solver inputs. Same-name labels denote connected
nets; repeated-device banks retain individual instances in editable child sheets.
SVG metadata binds the source digest and records authoring/verification limitations.
The authoritative netlist, simulation decks and evaluation requirements are unchanged.

## Reference Results

Reference results use the pinned IHP SG13G2 ciel release described in
[resource preparation](../../../../../docs/tools.md#ihp-physical-check-profiles).

The declared reference passes artifact, DRC, LVS, hard geometry, candidate-derived
extraction and the functional checks in the current case plan. Conditions, model
boundaries, measurement windows and normalization rules are specified in
[problem.md](problem.md). Both simulation paths use the same declared testbenches
and trusted resources. The source circuit supplies the electrical baseline;
the reference GDS demonstrates an executable layout, not an optimal solution.

Measured `layout-v2` score: **23.615145**, with electrical quality
**E = 0.60593658** and area quality **Q = 0.092035221**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1110626.873 um2**.

Area reference: **102216.79 um2**. 166 expanded device instances; sum of device/contact envelopes 67727.1707 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `gain_vv` | V/V | 19.616335 … 19.617306 | 19.496412 … 19.496819 | 0.89216245 |
| `baseline_error_v` | V | 4.943016e-08 … 5.672646e-08 | 3.113826e-06 … 3.122269e-06 | 0.25509833 |
| `return_error_v` | V | 6.371404e-08 … 8.39291e-08 | 2.218184e-06 … 2.37605e-06 | 0.31821102 |
| `high_drift_v` | V | 0 … 5e-07 | 1e-07 … 8e-07 | 0.76923077 |
| `return_drift_v` | V | 4.317e-10 … 8.58e-09 | 4.345e-08 … 1.16244e-07 | 0.90105743 |
| `ripple_rms_v` | V | 0.0078303812 … 0.0078846801 | 0.0087477271 … 0.0093846076 | 0.83455826 |
| `ripple_pp_v` | V | 0.0956577 … 0.1040801 | 0.0770803 … 0.0802718 | 1.2258045 |
| `cm_mean_v` | V | 0.6128099 … 0.6128107 | 0.6168123 … 0.6168139 | 0.99667484 |
| `cm_min_v` | V | 0.6104253 … 0.6104701 | 0.6152361 … 0.6154959 | 0.99580699 |
| `cm_max_v` | V | 0.6137994 … 0.6146429 | 0.6177754 … 0.6187997 | 0.99654796 |
| `sum_cm_v` | V | 0.6000626 | 0.6000512 … 0.6000513 | 0.9999905 |
| `sum_error_v` | V | 6.71883e-05 … 6.755051e-05 | 0.000104632 … 0.0001055977 | 0.64046184 |
| `mean_power_w` | W | 0.0003175971 … 0.0003176063 | 0.000227842 … 0.0002278477 | 1.3939278 |
| `clock_power_w` | W | 8.664582e-10 … 8.672072e-10 | 1.034026e-08 … 1.0348e-08 | 0.083839681 |
| `dc_cm_v` | V | 0.6128227 | 0.61683309 | diagnostic |
| `dc_dm_v` | V | -2.7965386e-05 | -0.0076295341 | diagnostic |
| `baseline_v` | V | -5.672646e-08 … -4.943016e-08 | 3.113826e-06 … 3.122269e-06 | diagnostic |
| `plateau_v` | V | -0.1961729 … 0.196173 | -0.1949626 … 0.1949713 | diagnostic |
| `return_v` | V | -1.234058e-07 … 2.720264e-08 | 5.33201e-06 … 5.493735e-06 | diagnostic |
| `dc_power_w` | W | 0.00031754072 | 0.00022757869 | diagnostic |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient 10 reflects the system-level combination of signal/feedback
modulation and interacting differential/common-mode control across clock states
and input polarities.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.ia_006_fan_chopper_cmfb --image iclayout-bench-tools:local \
  --output build/runs/ia_006_fan_chopper_cmfb-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/ia_006_fan_chopper_cmfb-prepared \
  --output build/runs/ia_006_fan_chopper_cmfb-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'ia_006_fan_chopper_cmfb'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [analog-db ia_006_fan_chopper_cmfb at the fixed snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_006_fan_chopper_cmfb).
The fixed manifest attributes normalized schematic capture/composition to
Danial Noori Zadeh after Fan et al.; it supplies no separate component license
label. The fixed database LICENSE and NOTICE cover original/normalized
materials under PolyForm Noncommercial 1.0.0. The derivative circuit and
independent witness retain those terms and the Required Notice in the collection
[LICENSE](../../LICENSE) and [NOTICE](../../NOTICE); the normalized material is
not relicensed MIT. The independently authored measurement deck is MIT.
