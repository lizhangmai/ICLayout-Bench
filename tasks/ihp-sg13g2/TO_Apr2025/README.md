# Maintained TO_Apr2025 circuits

The [catalog](catalog.toml) indexes four maintained circuits derived from
[TO_Apr2025](https://github.com/IHP-GmbH/TO_Apr2025).
Each case's `case.toml` defines its current status and executable requirements;
its README describes the circuit boundary, modifications and validation scope.
Qualification applies to the maintained circuit and candidate-derived
post-layout results. Historical upstream simulations and physical checks do
not establish qualification.

| Case | Circuit role |
| --- | --- |
| [DC–130 GHz TIA, design 1](cases/DC_to_130_GHz_TIA.design_1/README.md) | Two-stage SiGe HBT transimpedance amplifier: converts input current into output voltage |
| [40 GHz low-noise TIA](cases/40_GHZ_LOW_NOISE_TIA/README.md) | Three-HBT transimpedance amplifier core with separately supplied stages |
| [97 GHz linear TIA](cases/97_GHZ_LINEAR_TIA/README.md) | Transimpedance amplification with bias and feedback circuitry |
| [160 GHz LNA](cases/160GHz_LNA/README.md) | Cascaded HBT voltage amplification |

The directory names preserve source identifiers. They do not promise the
upstream frequency or noise targets: consult each case's explicit operating
conditions and metric limits. Circuit changes may resolve source/layout
inconsistencies or define a reproducible benchmark boundary, provided their
provenance and functional consequences are documented.

## Asset roles and rights

The upstream [root license](LICENSE) is Apache-2.0;
design 1 also declares Apache-2.0 in its project README. No separate LICENSE,
NOTICE or COPYING file was found inside these four selected project trees.
Retain per-file author notices and review any newly selected dependency's own
license. PDK symbols, compact models and tools remain separately licensed.
The collection license is declared through `collection_source` and copied into
each materialized case as `materials/LICENSE`.
Each case records its upstream circuit link in `origin.url`; the maintained
materials define the current task.

Executable task inputs are declared in `[task.inputs]`: their LVS circuit,
simulation circuit and shared testbench define the maintained circuit.
`problem.md` explains the interface, constraints and performance limits;
`reference/` holds a published witness where available. Reference geometry,
historical EM results and full source checkouts are not implicit solver
inputs. Upstream sources are available through each case's attribution link.
Follow the [isolation checklist](../../../docs/tasks.md#input-isolation).
