> Qualification commands require the installed Private operator package (`layout_eval`); run them from the Public task checkout. Participant-only installations use the HTTP service.

# Eight-Bit R-2R DAC Core

## Overview

**Qualified, with a passing reference layout.** An eight-bit passive R-2R ladder made from the GF180 1 kOhm/square unsalicided poly resistor, including its tied dummy resistors. Bit drivers and output loading belong to the testbench. The supplied reference retains the upstream core geometry.

The validated scope is nominal **3.3 V, 27 C**, using the GF180 D typical models and candidate-derived distributed RC. [The problem](problem.md) supplies the complete interface, timing, acceptance intervals and scoring contract. Qualification does not establish statistical yield, RF/EM accuracy or chip-level density/seal-ring closure; formal admission remains separate.

## Files

| File | Role |
| --- | --- |
| [case.toml](case.toml) | Executable task, trusted tool bindings, input identities and qualification metadata |
| [problem.md](problem.md) | Complete solver contract |
| [materials/circuit.spice](materials/circuit.spice) | Authoritative source circuit |
| [materials/testbench.spice](materials/testbench.spice) | Source calibration and candidate-derived post-layout measurements |
| [LICENSE](../../LICENSE) | Source and applicable component terms; retained with the collection, outside solver inputs |
| [reference/r2r.gds](reference/r2r.gds) | Ready-to-use feasibility witness; excluded from standard solver inputs |

Standard materialization contains only the five declared input files. It excludes this README, the case configuration, references, upstream checkouts and generation history. Physical/model resources are supplied separately as verified support bundles.

## Reference Results

The reference passed artifact validation, GF180 D geometric/connectivity/off-grid DRC, antenna checks, named-interface LVS, the hard functional outline, distributed RC extraction, and every required electrical observation. No DRC marker waivers are used. The functional area is **3732.784 um2**; the complete reference evaluation scored **100/100**. This is a reference qualification result, not an agent/model score.

The table gives the minimum-to-maximum range across every sample/condition in each metric; each observation is accepted separately, so a range is not an average. Measurement definitions and units are unchanged between the source and reference runs.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| `accuracy` | V | 0 to 3.75e-07 | 0 to 5.7e-05 |
| `settling` | V | 0 to 3.75e-07 | 0 to 5.7e-05 |

The 0.1 mV per-code accuracy limit resolves well below one 12.890625 mV LSB. Zero, every independent bit weight and full scale exercise the linear ladder; the separate 1 us observation constrains transient settling. This is deterministic nominal conversion, not mismatch-limited eight-bit yield. Coefficient 4 covers resistor matching and a complete loaded ladder.

The full-area utility target is **4000 um2**, a rounded absolute area budget supported by the measured feasible layout above. The zero-area utility anchor is **16000 um2**, reserving four times that fixed area budget (twice each linear dimension) for substantial routing expansion. These anchors were frozen before model evaluation and are not recalculated from submitted or replacement reference layouts. Electrical zero boundaries define the declared degraded-response endpoints; nonnegative delay and supplied power use a hard cliff at zero. All applicable dimensions take their worst requirement before the single score is formed.

The extracted source/body connections remain distinct where required. The distributed silicon substrate is outside the compact-model boundary. Catalog-driven regression covers positive reference evaluation and empty-layout rejection; it does not independently establish parasitic-coefficient accuracy. Native transistor and poly-resistor source models remain unmodified.

## Reproduce

Run from the repository root after preparing the [GF180 image and support bundles](../../../../../docs/tools.md#gf180). Use a fresh output directory:

```bash
python -m layout_eval.cli evaluate \
  tasks/gf180mcuD/gf-r2r-dac/cases/r2r/case.toml \
  tasks/gf180mcuD/gf-r2r-dac/cases/r2r/reference/r2r.gds \
  --output build/runs/gf180mcuD.gf-r2r-dac.r2r-reference
uv run --locked pytest tests/integration/test_public_references.py \
  -k 'gf180mcuD and r2r' -q
```

The evaluate command creates `report.json` and identity-bound artifacts under the chosen output directory. Reproduce the Pre-layout column using the [source-calibration recipe](../../../../../docs/tools.md#gf180-source-calibration) with `tasks/gf180mcuD/gf-r2r-dac/cases/r2r/case.toml`. The shared regression checks the supplied reference against the current contract and rejects an empty candidate. Source-only calibration is not scored as layout acceptance.

## Source and License

The circuit is attributed to [the pinned upstream source](https://github.com/mattvenn/gf-r2r-dac/tree/1c5c8ddec54fc4e70ce03a19510d4d7461b919e9/xschem/simulation/r2r.spice); see the collection [LICENSE](../../LICENSE) for source and applicable component terms.
