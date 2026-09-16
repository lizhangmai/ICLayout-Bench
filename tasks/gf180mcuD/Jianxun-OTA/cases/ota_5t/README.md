> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Five-Transistor OTA with Bias and Dummies

## Overview

**Qualified, with a passing reference layout.** A five-transistor OTA core with a separate bias-reference transistor and rail-tied MOS dummies. The supplied standalone circuit fixes L=0.28 um, W=6 um and its original multiplicities. The reference independently implements each declared finger with separate body contacts.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/ota_5t.gds](reference/ota_5t.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

Standard materialization contains only the five declared input files. It excludes this README, the case configuration, references, upstream checkouts and generation history. Physical/model resources are supplied separately as verified support bundles.

## Reference Results

The reference passed artifact validation, GF180 D geometric/connectivity/off-grid DRC, antenna checks, named-interface LVS, the hard functional outline, distributed RC extraction, and every required electrical observation. No DRC marker waivers are used. The functional area is **5692.55 um2**; the complete reference evaluation scored **100/100**. This is a reference qualification result, not an agent/model score.

The table gives the minimum-to-maximum range across every sample/condition in each metric; each observation is accepted separately, so a range is not an average. Measurement definitions and units are unchanged between the source and reference runs.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `gain` | dB | 24.42387 | 24.42053 |
| `unity` | Hz | 2.635212e+07 | 2.392023e+07 |
| `output_bias` | V | 2.526216 | 2.52818 |
| `supply` | W | 0.0001074716 | 0.0001075173 |

The 20 dB gain and 15 MHz unity-frequency requirements retain useful amplification into 1 pF below the source and reference bandwidths. The 2–2.9 V bias interval rejects a rail-clamped output; the 150 uW power budget covers the measured bias network without accepting milliamp-level shorts. Coefficient 4 covers a compact biased amplifier with matching and load constraints.

The full-area utility target is **6000 um2**, a rounded absolute area budget supported by the measured feasible layout above. The zero-area utility anchor is **24000 um2**, reserving four times that fixed area budget (twice each linear dimension) for substantial routing expansion. These anchors were frozen before model evaluation and are not recalculated from submitted or replacement reference layouts. Electrical zero boundaries define the declared degraded-response endpoints; nonnegative delay and supplied power use a hard cliff at zero. All applicable dimensions take their worst requirement before the single score is formed.

The extracted source/body connections remain distinct where required. The distributed silicon substrate is outside the compact-model boundary. Catalog-driven regression covers positive reference evaluation and empty-layout rejection; it does not independently establish parasitic-coefficient accuracy. Native transistor and poly-resistor source models remain unmodified.

## Reproduce

Run from the repository root after preparing the [GF180 image and support bundles](../../../../../docs/tools.md#gf180). Use a fresh output directory:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/Jianxun-OTA/cases/ota_5t/case.toml \
  tasks/gf180mcuD/Jianxun-OTA/cases/ota_5t/reference/ota_5t.gds \
  --output build/runs/gf180mcuD.Jianxun-OTA.ota_5t-reference
uv run --locked pytest tests/integration/test_public_references.py \
  -k 'gf180mcuD and ota_5t' -q
```

The evaluate command creates `report.json` and identity-bound artifacts under the chosen output directory. Reproduce the Pre-layout column using the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration) with `tasks/gf180mcuD/Jianxun-OTA/cases/ota_5t/case.toml`. The shared regression checks the supplied reference against the current contract and rejects an empty candidate. Source-only calibration is not scored as layout acceptance.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/Jianxun/iic-osic-tools-project-template/tree/178a401d847ce7a602d0ce70a1ba90a15b5f9536/designs/libs/core_analog/ota_5t/ota_5t.spice); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
