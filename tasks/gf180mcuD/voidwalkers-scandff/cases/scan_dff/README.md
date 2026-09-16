> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Scan D Flip-Flop with Active-Low Reset

## Overview

**Qualified, with a passing reference layout.** A transmission-gate scan multiplexer and resettable D flip-flop. The reference retains the upstream geometry and uses the authoritative source top-cell name. Its contract checks data selection, stored high/low values, asynchronous reset and clock-to-output timing.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/gf180mcu_voidwalkers_sc_sdffrnq_4.gds](reference/gf180mcu_voidwalkers_sc_sdffrnq_4.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

Standard materialization contains only the five declared input files. It excludes this README, the case configuration, references, upstream checkouts and generation history. Physical/model resources are supplied separately as verified support bundles.

## Reference Results

The reference passed artifact validation, GF180 D geometric/connectivity/off-grid DRC, antenna checks, named-interface LVS, the hard functional outline, distributed RC extraction, and every required electrical observation. No DRC marker waivers are used. The functional area is **175.5775 um2**; the complete reference evaluation scored **100/100**. This is a reference qualification result, not an agent/model score.

The table gives the minimum-to-maximum range across every sample/condition in each metric; each observation is accepted separately, so a range is not an average. Measurement definitions and units are unchanged between the source and reference runs.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `low` | V | 6.604153e-09 to 5.576545e-08 | 1.049328e-08 to 3.660766e-08 |
| `high` | V | 3.3 | 3.3 |
| `delay` | s | 8.644622e-10 | 9.552946e-10 |
| `supply` | W | 4.187209e-05 | 4.996386e-05 |

The high/low requirements use 90%/10% of the 3.3 V rail. The 2 ns delay budget is 10% of the clock period, and the 75 uW power budget covers both source and extracted operation. The reset sample before a clock edge proves asynchronous behavior. Coefficient 5 covers the dynamic storage circuit and its scan/reset paths.

The full-area utility target is **200 um2**, a rounded absolute area budget supported by the measured feasible layout above. The zero-area utility anchor is **800 um2**, reserving four times that fixed area budget (twice each linear dimension) for substantial routing expansion. These anchors were frozen before model evaluation and are not recalculated from submitted or replacement reference layouts. Electrical zero boundaries define the declared degraded-response endpoints; nonnegative delay and supplied power use a hard cliff at zero. All applicable dimensions take their worst requirement before the single score is formed.

The extracted source/body connections remain distinct where required. The distributed silicon substrate is outside the compact-model boundary. Catalog-driven regression covers positive reference evaluation and empty-layout rejection; it does not independently establish parasitic-coefficient accuracy. Native transistor and poly-resistor source models remain unmodified.

## Reproduce

Run from the repository root after preparing the [GF180 image and support bundles](../../../../../docs/tools.md#gf180). Use a fresh output directory:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/voidwalkers-scandff/cases/scan_dff/case.toml \
  tasks/gf180mcuD/voidwalkers-scandff/cases/scan_dff/reference/gf180mcu_voidwalkers_sc_sdffrnq_4.gds \
  --output build/runs/gf180mcuD.voidwalkers-scandff.scan_dff-reference
uv run --locked pytest tests/integration/test_public_references.py \
  -k 'gf180mcuD and scan_dff' -q
```

The evaluate command creates `report.json` and identity-bound artifacts under the chosen output directory. Reproduce the Pre-layout column using the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration) with `tasks/gf180mcuD/voidwalkers-scandff/cases/scan_dff/case.toml`. The shared regression checks the supplied reference against the current contract and rejects an empty candidate. Source-only calibration is not scored as layout acceptance.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/radityankn/voidwalkers-scandff-gf180mcu/tree/b136150cdcfd55a9568fe14a825c214c3af5dde4/designs/cells/gf180mcu_voidwalkers_sc_sdffrnq_4/sch/gf180mcu_voidwalkers_sc_sdffrnq_4.sch); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
