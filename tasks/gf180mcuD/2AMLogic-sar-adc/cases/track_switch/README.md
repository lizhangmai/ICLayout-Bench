> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Dummy-Compensated Track Switch

## Overview

**Qualified, with a passing reference layout.** A complementary transmission gate with two dummy MOS devices for charge compensation. The source default widths are specialized to 40, 80, 17.5 and 35 um, and its implicit ground is exposed as vss; these changes preserve the original default circuit. The independently constructed reference includes isolated body contacts and a complete physical implementation.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/adc_tgate_dum.gds](reference/adc_tgate_dum.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

Standard materialization contains only the five declared input files. It excludes this README, the case configuration, references, upstream checkouts and generation history. Physical/model resources are supplied separately as verified support bundles.

## Reference Results

The reference passed artifact validation, GF180 D geometric/connectivity/off-grid DRC, antenna checks, named-interface LVS, the hard functional outline, distributed RC extraction, and every required electrical observation. No DRC marker waivers are used. The functional area is **3710.85 um2**; the complete reference evaluation scored **100/100**. This is a reference qualification result, not an agent/model score.

The table gives the minimum-to-maximum range across every sample/condition in each metric; each observation is accepted separately, so a range is not an average. Measurement definitions and units are unchanged between the source and reference runs.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `high` | V | 2.5 | 2.5 |
| `low` | V | 0.5 | 0.5 |
| `hold` | V | 0.003106877 | 0.02900338 |
| `settling` | s | 4.361648e-10 | 7.140159e-10 |

Tracking is required within 20 mV at both levels; the 1 ns settling requirement is longer than both calibrated settling times. The 40 mV hold-error budget includes the worst feedthrough during the disconnected-input transition, not merely the final held sample. Coefficient 4 covers the complementary switch, dummy compensation and loaded tracking/hold behavior.

The full-area utility target is **4000 um2**, a rounded absolute area budget supported by the measured feasible layout above. The zero-area utility anchor is **16000 um2**, reserving four times that fixed area budget (twice each linear dimension) for substantial routing expansion. These anchors were frozen before model evaluation and are not recalculated from submitted or replacement reference layouts. Electrical zero boundaries define the declared degraded-response endpoints; nonnegative delay and supplied power use a hard cliff at zero. All applicable dimensions take their worst requirement before the single score is formed.

The extracted source/body connections remain distinct where required. The distributed silicon substrate is outside the compact-model boundary. Catalog-driven regression covers positive reference evaluation and empty-layout rejection; it does not independently establish parasitic-coefficient accuracy. Native transistor and poly-resistor source models remain unmodified.

## Reproduce

Run from the repository root after preparing the [GF180 image and support bundles](../../../../../docs/tools.md#gf180). Use a fresh output directory:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/2AMLogic-sar-adc/cases/track_switch/case.toml \
  tasks/gf180mcuD/2AMLogic-sar-adc/cases/track_switch/reference/adc_tgate_dum.gds \
  --output build/runs/gf180mcuD.2AMLogic-sar-adc.track_switch-reference
uv run --locked pytest tests/integration/test_public_references.py \
  -k 'gf180mcuD and track_switch' -q
```

The evaluate command creates `report.json` and identity-bound artifacts under the chosen output directory. Reproduce the Pre-layout column using the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration) with `tasks/gf180mcuD/2AMLogic-sar-adc/cases/track_switch/case.toml`. The shared regression checks the supplied reference against the current contract and rejects an empty candidate. Source-only calibration is not scored as layout acceptance.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/2AMLogic/gf180-sar-adc/tree/c32c8da53e52fbb7d75f6f628b8cc9f6f45a13fc/design/adc-top/adc_top.spice); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
