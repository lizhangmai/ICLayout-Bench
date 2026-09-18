# Two-NMOS Temperature-Response Core

## Overview

The fixed GF180 binding contains eight parallel 8/0.28 um upper NMOS with gates tied to their sources, and eight parallel 4/1 um diode-connected lower NMOS. Both groups have grounded bodies. This is a two-group temperature-response core; neither its PTAT name nor a successful simulator exit establishes a useful slope or a converged extracted operating point.

The reference passes native physical checks and same-condition source-paired temperature evaluation. This is a nominal temperature-response core, not a precision sensor or a demonstrated self-starting reference. The [GF180 model guide](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_1.html) identifies -40, 25 and 125 C extraction temperatures; this task stays inside that interval. The [geometry guide](https://gf180mcu-pdk.readthedocs.io/en/latest/analog/model_parameters/LV/LV_2_2.html) distinguishes measured and pseudo-device dimensions. Coefficient 3: local analog temperature-dependent bias and transfer; [problem](problem.md) records the independent area estimate.

## Files

- [Schematic](materials/schematic.svg): digest-bound main-sheet overview; hierarchical device banks remain expandable in the editable source project. This presentation asset is excluded from solver inputs.

- [Problem](problem.md): complete solver-facing boundary and scoring contract.
- [Case configuration](case.toml): frozen inputs, native backends and source-paired observations.
- [Physical netlist](materials/circuit.cdl), [simulator circuit](materials/circuit.spice), and [testbench](materials/testbench.spice).
- [Temperature sweep](materials/temperature.spice): ascending and descending independent temperature analyses.
- [Reference GDS](reference/tsn_001_ptat_2t.gds): independent physical witness, excluded from solver inputs.

## Reference Results

Native DRC/LVS, full device/port graph and candidate-derived RC evaluation pass. Reference score: **47.47491682**; area 6622.67 um2. Independent raw checks verify external KCL, ascending/descending agreement and independent temperature operating points.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `output_v` | V | 0.0140948764 … 0.137051995 | 0.0536682454 … 0.13686945 |
| `power_w` | W | 2.04604936e-13 … 1.44164995e-09 | 7.097499e-14 … 1.44816004e-09 |
| `slope_v_c` | V/C | 0.000878265135 | 0.00059429432 |
| `curvature_v` | V | 0.0636609968 | 0.0382600397 |

Halving the temperature sweep step from 5 to 2.5 C and tightening reltol/abstol/vntol tenfold changes the paired score from 47.47491682 to 47.48188933 (absolute 0.00697251). The maximum independent OP voltage change is 6.86 nV. Curvature is a finite-grid maximum: the refined source/candidate values change by 125.1/7.70 uV. This numerical sensitivity does not establish model accuracy, process variation or linear PTAT behavior.

## Numerical formulation

The high-impedance output connected through low-ohmic metal is ill-conditioned in ordinary nodal conductance stamping. A minimal linear example gives an independent explanation: 1 pA into a 1 Tohm load through 0.1895 ohm must produce 1 V at the load. Double precision represents `(1/0.1895 + 1e-12) - 1/0.1895` as approximately `1.000088900582341e-12`, giving 0.9999111073 V instead. In the nonlinear extracted core this error disrupts Newton convergence; transient OP fallback can report success with invalid external KCL. It is not evidence of a wrong transistor connection or a missing bias branch.

The declared ngspice backend uses `resistor_formulation = "branch"` with Sparse 1.3. Each constant extracted resistor retains its terminals/value and is represented by a zero-volt series current sensor plus a CCVS enforcing V=R*I. No resistance or capacitance is removed, no shunt/bias is introduced, and the core topology is unchanged. The original extracted netlist remains available for graph checks; `effective_dut` records the digest-bound simulator representation. Source and candidate use the same backend setting. Thermal resistor noise is not provided by this representation; the adapter rejects noise analyses in this mode. Model-dependent/temperature-coefficient resistor cards are rejected rather than approximated; PDK device subcircuits are left intact.

The independent analytical, DC, AC and transient formulation regressions can be run from Bench with:

```bash
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:ngspice45 uv run --locked pytest tests/integration/test_characterization.py
```

All static core devices, passives, compact models and ordered ports were checked against the fixed binding and both native topology/RC netlists. Same-condition source simulation supplies the baseline, not the witness score. Qualified cases also pass independent raw-waveform/KCL/window checks; candidate failures are never substituted with a finite score. The verified compatible image contains ngspice 45, Magic 8.3.678 and KLayout 0.30.11. No statistical mismatch, noise or manufactured silicon validation is asserted.

## Reproduce

From the Bench root, reuse a compatible image following the [tools guide](../../../../../docs/tools.md#image-development). These commands create new disposable resources and reports; use a fresh directory when repeating. No Designs or Private checkout is needed.

```bash
uv run --locked python -m benchmarking.engine.preview prepare \
  --case tsn_001_ptat_2t --image iclayout-bench-tools:ngspice45 \
  --output "$PWD/build/runs/tsn_001_ptat_2t-prepared"
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/runs/tsn_001_ptat_2t-prepared/case/case.toml \
  tasks/gf180mcuD/analog-db/cases/tsn_001_ptat_2t/reference/tsn_001_ptat_2t.gds \
  --output build/runs/tsn_001_ptat_2t-evaluation
```

## Source and License

Derived from [MacAnalog tsn_001_ptat_2t at commit 263d0322f8900dc331536fbbe6c0e804514fc454](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/tsn_001_ptat_2t); retain [collection LICENSE](../../LICENSE) and [NOTICE](../../NOTICE). The fixed manifest identifies a normalized CODA-Team AnalogGym BSD-3-Clause topology. All available open-PDK bindings are retained separately in the snapshot. Proprietary reference variants and historical sizing comments are not implementation inputs. Physical conversion adds native contacts and routes, expands declared multiplicities and implements resistors with native series segments; topology and total MOS dimensions remain fixed. Independently authored observation decks are MIT; database derivatives retain their separate terms.
