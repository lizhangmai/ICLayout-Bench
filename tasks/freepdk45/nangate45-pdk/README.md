# Maintained nangate45-pdk circuits

The [catalog](catalog.toml) indexes the selected first-batch FreePDK45 circuits.
Each case owns its configuration, declared materials, ready-to-use reference GDS,
and documented reference results and reproduction commands. These cases are
`qualified` through input consistency and reference evaluation. Reference validation covers
nominal 1.0 V, 27 C predictive RC simulation; consult each problem for its exact circuit contract.

| Case | Circuit role |
| --- | --- |
| [NAND2_X1](cases/NAND2_X1/README.md) | Two-input NAND |
| [AOI21_X1](cases/AOI21_X1/README.md) | AND-OR-invert logic |

Prepare the shared image and process bundles using the
[tools guide](../../../docs/tools.md#freepdk45), then follow the case README
for reference evaluation and qualification reproduction. References and raw
evidence are excluded from standard solver inputs.

The [LICENSE](LICENSE) and [NOTICE](NOTICE) are stored once for this collection.
Each case declares the shared files as inputs; materialization and reference
export include copies with the selected circuit materials.
