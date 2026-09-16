> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Quadrature Voltage-Controlled Oscillator

## Overview

**Qualified, with a passing reference layout.** A four-stage differential ring oscillator with a common current-control network and two differential output buffers. The reference is an independently routed feasibility witness with separate source/body contacts and a short control-input wire. It deliberately establishes feasibility rather than a compact-layout optimum.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/vco.gds](reference/vco.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

Standard materialization contains only the five declared input files. It excludes this README, the case configuration, references, upstream checkouts and generation history. Physical/model resources are supplied separately as verified support bundles.

## Reference Results

The reference passed artifact validation, GF180 D geometric/connectivity/off-grid DRC, antenna checks, named-interface LVS, the hard functional outline, distributed RC extraction, and every required electrical observation. No DRC marker waivers are used. The functional area is **35031.25 um2**; the complete reference evaluation scored **100/100**. This is a reference qualification result, not an agent/model score.

The table gives the minimum-to-maximum range across every sample/condition in each metric; each observation is accepted separately, so a range is not an average. Measurement definitions and units are unchanged between the source and reference runs.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `low_control_frequency` | Hz | 9.763184e+07 | 1.753288e+07 |
| `high_control_frequency` | Hz | 2.459757e+08 | 5.01276e+07 |
| `tuning` | 1 | 2.51942 | 2.859062 |
| `quadrature90` | 1 | 0.2499969 to 0.2500067 | 0.2604675 to 0.2605031 |
| `quadrature180` | 1 | 0.4999975 to 0.5000085 | 0.5000282 to 0.5043309 |
| `quadrature270` | 1 | 0.7500025 to 0.7500184 | 0.7613729 to 0.762118 |
| `low` | V | -0.0107174 to -0.004189262 | 0.005874613 to 0.01540607 |
| `high` | V | 3.309453 to 3.317764 | 3.283485 to 3.295631 |
| `supply` | W | 0.001899201 to 0.002622109 | 0.001563096 to 0.002113931 |

The 10 MHz / 30 MHz frequency floors at 1.65 V / 2.10 V control permit the interconnect delay of the supplied feasibility layout while requiring useful oscillation at both points. A tuning ratio of at least two rejects ineffective control. The 0.05-cycle phase tolerance is 18 degrees; power is bounded at each point individually. Coefficient 8 reflects the coupled feedback, tuning, speed and quadrature requirements.

The full-area utility target is **36000 um2**, a rounded absolute area budget supported by the measured feasible layout above. The zero-area utility anchor is **144000 um2**, reserving four times that fixed area budget (twice each linear dimension) for substantial routing expansion. These anchors were frozen before model evaluation and are not recalculated from submitted or replacement reference layouts. Electrical zero boundaries define the declared degraded-response endpoints; nonnegative delay and supplied power use a hard cliff at zero. All applicable dimensions take their worst requirement before the single score is formed.

The extracted source/body connections remain distinct where required. The distributed silicon substrate is outside the compact-model boundary. Catalog-driven regression covers positive reference evaluation and empty-layout rejection; it does not independently establish parasitic-coefficient accuracy. Native transistor and poly-resistor source models remain unmodified.

## Reproduce

Run from the repository root after preparing the [GF180 image and support bundles](../../../../../docs/tools.md#gf180). Use a fresh output directory:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/tt_tnt_gf_vco/cases/vco/case.toml \
  tasks/gf180mcuD/tt_tnt_gf_vco/cases/vco/reference/vco.gds \
  --output build/runs/gf180mcuD.tt_tnt_gf_vco.vco-reference
uv run --locked pytest tests/integration/test_public_references.py \
  -k 'gf180mcuD and vco' -q
```

The evaluate command creates `report.json` and identity-bound artifacts under the chosen output directory. Reproduce the Pre-layout column using the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration) with `tasks/gf180mcuD/tt_tnt_gf_vco/cases/vco/case.toml`. The shared regression checks the supplied reference against the current contract and rejects an empty candidate. Source-only calibration is not scored as layout acceptance.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/smunaut/tt_tnt_gf_vco/tree/897b3ec12ed693161fb56f4205d1b19dc5e56c1a/xschem/vco.sch); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
