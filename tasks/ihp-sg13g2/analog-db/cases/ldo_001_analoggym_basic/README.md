> Qualification commands use the Public evaluation engine (`benchmarking.engine`); run them from the Public task checkout. Remote participants use the HTTP service.

# Multistage Error-Amplifier PMOS Regulator

## Overview

The PMOS-input folded error amplifier, cascoded bias branches and mirrored
loads drive a separate intermediate PMOS/NMOS branch and the pass-gate node
`net1`. The auxiliary PMOS source/body is tied to `net1`; the input pair has
a separate source-tied `net20` well. The physical 300/100 kohm divider returns
one quarter of output through the declared VFB/SENSE measurement interface.
This complete internal drive network adds coverage beyond the simpler LDO004,
LDO008 and LDO009 error-amplifier paths.

| Related maintained case | Distinction of this case |
| --- | --- |
| [LDO004](../../../../gf180mcuD/analog-db/cases/ldo_004_basic_pmos/README.md) | Its four-transistor error amplifier uses an external 1 uF load capacitor; this folded/cascoded core retains internal compensation and qualifies its own bilateral loop and specified zero-state startup. LDO004 retains its own GF180 supply/load and rejection contract. |
| [LDO008](../ldo_008_fer_mirror_ota/README.md) | Its mirror OTA uses divider/series compensation; this core has separate source-tied input and auxiliary wells, a pass-gate-coupled auxiliary branch, and net106/net10 output-connected compensation. Neither case proves all internal poles. |
| [LDO009](../ldo_009_fer_5t_pass/README.md) | Its NMOS-input five-transistor amplifier uses unity feedback and internal COUT; this PMOS-input multistage core has a physical 3:1 divider and two internal compensation paths, without added output-to-ground storage. |

All 24 original MOS groups remain. Equivalent parallel regrouping converts
1,168 raw fingers into 831 physical MOS, preserving each group's total W and L;
individual W/m and diffusion perimeter change. The pass PMOS retains its 464
fingers. All original bias and feedback devices remain. The 8 uA external sink
is unchanged; the reference is explicitly calibrated from 0.4 to 0.225 V,
setting an ideal 0.9 V output target within the 1.2/1.3 V LV supply range.

All internal passives are physical: three 42.685 um square MIM units retain
approximately 8.2 pF `net106–output` compensation; an additional 51.64 um square
MIM provides approximately 4 pF `net10–output` local compensation. Twelve/four
series high-poly segments (W=1 um, L=17.465 um) implement the complete divider.
No extra output-to-ground capacitor, ideal servo or diagnostic clamp is added.
There is real output-connected capacitance in both compensation branches.

Qualification covers typical models at 27 C, two supplies, 0.2/0.5 mA loads
doubled with 200 ns edges, line/load/headroom sweeps and synchronized 10/20 us
zero-state startup into 900/4500 ohm loads. The [problem](problem.md) owns the
complete circuit, body, interface, physical and electrical contract.

## Files

- [Problem](problem.md): complete solver-facing requirements.
- [Configuration](case.toml): inputs, checks, limits, scoring and witness.
- [Native circuit](materials/circuit.cdl) and [simulation circuit](materials/circuit.spice): matching device graphs.
- [Loop/load deck](materials/testbench.spice): bilateral return ratio and sustained current-load recovery.
- [Startup deck](materials/startup.spice): zero-state supply/reference/bias ramps with resistive loading.
- [Sweep deck](materials/sweeps.spice): line/load and downward regulation-floor measurements.
- [Reference GDS](reference/ldo_001_analoggym_basic.gds): independent physical witness.

Only the problem and five declared materials enter solver inputs. Collection
license/notice accompany distributions separately; source checkouts, reference,
configuration and qualification results remain outside solver inputs.

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

Source and extracted simulations both use `.option itl1=1000` to allow the
declared low-supply DC operating point to converge with the same solver settings.

Measured `layout-v2` score: **15.278587**, with electrical quality
**E = 1.0504463** and area quality **Q = 0.022222481**.
The score is `100 * sqrt(E * Q)` after validity and functional checks; 100 is a
reference, not a ceiling. Functional area is **1906376.736 um2**.

Area reference: **42364.42 um2**. 1240 expanded device instances; sum of device/contact envelopes 27974.3733 um2, per-side envelope allowance 0.6 um, 50% routing allowance and outer margin 1.2 um. Estimate = ceil(100 * (1.5 * envelope_sum + 4 * margin * sqrt(envelope_sum) + 4 * margin^2)) / 100. MOS/passive envelopes use declared W/L (or resistor dimensions) and multiplicity; explicit tap areas and HBT emitter/contact envelopes are included. This is a frozen engineering estimate, not a foundry minimum or a feasibility claim.

| Metric | Unit | Pre-layout range | Post-layout range | Worst quality ratio |
| --- | --- | ---: | ---: | ---: |
| `output_v` | V | 0.88468938 … 0.8898397 | 0.88797595 … 0.89272701 | 0.99747825 |
| `bias_v` | V | 0.70471514 … 0.80471509 | 0.69671207 … 0.79777746 | 0.99388052 |
| `quiescent_a` | A | 8.5053755e-05 … 8.5628348e-05 | 8.7556295e-05 … 8.82045e-05 | 0.97006051 |
| `power_w` | W | 0.00034212681 … 0.00076126411 | 0.00034506755 … 0.00076466585 | 0.99147778 |
| `dc_gain_db` | dB | 50.32356 … 52.69066 | 50.84443 … 53.46268 | 1.0618019 |
| `unity_hz` | Hz | 401330.1 … 406136.2 | 418191.5 … 424666.3 | 1.0418778 |
| `phase_margin_deg` | deg | 87.34981 … 87.45723 | 81.14572 … 81.35229 | 0.96668124 |
| `final_unity_hz` | Hz | 401330.1 … 406136.2 | 418191.5 … 424666.3 | 1.0418778 |
| `final_phase_margin_deg` | deg | 87.34981 … 87.45723 | 81.14572 … 81.35229 | 0.96668124 |
| `minimum_return_distance` | 1 | 0.95113151 … 0.95446115 | 0.87624604 … 0.88135331 | 0.93028005 |
| `return_phase_excursion_deg` | deg | 83.842341 … 84.626678 | 84.370013 … 85.162061 | 0.99338138 |
| `hf_gain_db` | dB | -81.75554 … -78.15391 | -111.6189 … -111.5727 | 30.964067 |
| `minimum_v` | V | 0.8736976 … 0.8798426 | 0.8674489 … 0.8756491 | 0.9952163 |
| `maximum_v` | V | 0.8945545 … 0.8992763 | 0.9107276 … 0.9141766 | 0.98641165 |
| `recovery_load_v` | V | 0.01237304 … 0.01810482 | 0.009248785 … 0.01443391 | 1.2543078 |
| `recovery_release_v` | V | 0.01015946 … 0.01531135 | 0.007272993 … 0.01202405 | 1.273371 |
| `mean_power_w` | W | 0.0004651032 … 0.001094364 | 0.000468117 … 0.001097931 | 0.99356187 |
| `loaded_ripple_v` | V | 0 | 0 | 1 |
| `released_ripple_v` | V | 0 | 0 | 1 |
| `startup_error_v` | V | 0.01012422 … 0.018016 | 0.007249471 … 0.01437422 | 1.2533373 |
| `startup_peak_v` | V | 0.881984 … 0.8898758 | 0.8856259 … 0.8927506 | 0.99720636 |
| `startup_minimum_v` | V | 1.060331e-06 … 2.311701e-06 | 5.846892e-07 … 1.271625e-06 | 0.9999992 |
| `regulation_floor_v` | V | 0.879919 … 0.9339764 | 0.8902489 … 0.9642853 | 0.97721664 |
| `headroom_v` | V | 0.009919 … 0.0639764 | 0.0202489 … 0.0942853 | 0.48987896 |
| `line_span_v` | V | 0.0017495 … 0.0025942 | 0.0017221 … 0.0024839 | 1.0159016 |
| `load_span_v` | V | 0.005342 … 0.006189 | 0.0046761 … 0.005438 | 1.1380769 |

Ranges summarize all declared observations; quality is computed from paired
observations, not from range endpoints. Reports retain each source and extracted
measurement. The area estimate and metric definitions are frozen before model
evaluation. Qualification does not establish PVT, statistical yield, manufacturing
signoff or performance outside the declared simulation/extraction scope.

Coefficient
9 reflects multistage regulation, physical feedback, coupled internal dynamics
and loaded recovery.

## Reproduce

Run from the Public checkout using the [shared tools setup](../../../../../docs/tools.md).
Reuse a compatible tools image or build it from the published Dockerfile. These
commands create fresh local output; the generated directories are not repository
inputs. Public qualification does not require the Private package.

```bash
python -m benchmarking.engine.preview prepare \
  --case ihp-sg13g2.analog-db.ldo_001_analoggym_basic --image iclayout-bench-tools:local \
  --output build/runs/ldo_001_analoggym_basic-prepared
python -m benchmarking.engine.preview run \
  --prepared build/runs/ldo_001_analoggym_basic-prepared \
  --output build/runs/ldo_001_analoggym_basic-reference
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  python -m pytest tests/integration/test_public_references.py -k 'ldo_001_analoggym_basic'
```

The reference run includes the `source_*` jobs; separate source-only plan editing
is unnecessary. Inspect `report.json` under the chosen reference output for raw
source/post-layout values, physical verdicts and the score decomposition. Use a
fresh output directory on each run. The catalog regression checks the supplied
witness and rejects an empty candidate; shared evaluator tests cover continuous
scoring, unknown evidence and functional failure. Original model results are not
relabelled or rescored when the task changes.

## Source and License

Derived from [LDO001 in the fixed source snapshot](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ldo_001_analoggym_basic).
Raw IHP DUT SHA-256:
`4b9daef958a188ec3e419e95f19f9eca010a39611c5765d60adf69dd6af521ed`.
Selected raw DUT, manifest, analyses and collection licensing files were checked
against the fixed Git tree. Normalized materials and the independent witness
retain PolyForm Noncommercial, Required Notice and the recorded CODA-Team
AnalogGym BSD-3-Clause component terms in collection [LICENSE](../../LICENSE)
and [NOTICE](../../NOTICE). The separately authored native measurement decks
are MIT. Component manifest labels do not relicense normalized derivatives.
