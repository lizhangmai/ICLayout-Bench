# Licensing and distribution

ICLayout-Bench contains an MIT-licensed framework and separately licensed public
task materials. Public availability does not mean that every file is MIT-licensed
or permitted for commercial use. This index describes the scope of the retained
licenses; it does not replace their terms or grant additional rights.

## Framework and Python packages

The root [LICENSE](LICENSE) applies to the project's original framework code and
documentation, except material identified under separate terms. The Python
package's `MIT` metadata describes that framework, not every asset in a source
checkout. The wheel and Python source distribution exclude the task collections
and PDKs; both include the MIT license and this scope notice. Collection links
below refer to the repository checkout, not files installed by the wheel.

Dependencies retain their own licenses. Installing the framework or building the
tool image does not relicense its dependencies, EDA tools, models or PDKs.

## Task collections

Paths below are relative to the repository root. Each collection's retained
license, required notices, case attribution and source-file headers define the
applicable scope. This table summarizes those declarations, not a completed
independent clearance of all upstream rights.

| Collection under `tasks/` | Retained terms for sourced circuit materials |
| --- | --- |
| `ihp-sg13g2/IHP-AnalogAcademy` | [Apache-2.0](tasks/ihp-sg13g2/IHP-AnalogAcademy/LICENSE) |
| `ihp-sg13g2/TO_Apr2025` | [Apache-2.0](tasks/ihp-sg13g2/TO_Apr2025/LICENSE) |
| `ihp-sg13g2/analog-db` | [PolyForm Noncommercial 1.0.0 and component terms](tasks/ihp-sg13g2/analog-db/LICENSE); [NOTICE](tasks/ihp-sg13g2/analog-db/NOTICE) defines attribution and derivative scope |
| `gf180mcuD/analog-db` | [PolyForm Noncommercial 1.0.0 and component terms](tasks/gf180mcuD/analog-db/LICENSE); [NOTICE](tasks/gf180mcuD/analog-db/NOTICE) defines attribution and derivative scope |
| `gf180mcuD/2AMLogic-sar-adc` | [Apache-2.0](tasks/gf180mcuD/2AMLogic-sar-adc/LICENSE) |
| `gf180mcuD/Chipathon2023_ADC` | [Apache-2.0](tasks/gf180mcuD/Chipathon2023_ADC/LICENSE) |
| `gf180mcuD/Jianxun-OTA` | [MIT](tasks/gf180mcuD/Jianxun-OTA/LICENSE), retaining upstream attribution |
| `gf180mcuD/gf-r2r-dac` | [Apache-2.0](tasks/gf180mcuD/gf-r2r-dac/LICENSE) |
| `gf180mcuD/tt_tnt_gf_vco` | [Apache-2.0](tasks/gf180mcuD/tt_tnt_gf_vco/LICENSE) |
| `gf180mcuD/voidwalkers-scandff` | [MIT](tasks/gf180mcuD/voidwalkers-scandff/LICENSE), retaining upstream attribution |
| `freepdk45/OpenRAM` | [GNU GPL version 3](tasks/freepdk45/OpenRAM/LICENSE); [NOTICE](tasks/freepdk45/OpenRAM/NOTICE) identifies the source netlists and reference layouts |
| `freepdk45/nangate45-pdk` | [Apache-2.0](tasks/freepdk45/nangate45-pdk/LICENSE) for source/software; [NOTICE](tasks/freepdk45/nangate45-pdk/NOTICE) separately identifies CC BY 4.0 for contributed documentation |

Both analog-db collections retain noncommercial restrictions on the normalized
circuit derivatives and corresponding reference layouts. Independently authored
measurement decks use the [root MIT license](LICENSE) where identified in their
notices. An MIT,
BSD or Apache attribution for an upstream component does not remove the retained
PolyForm terms from the distributed analog-db derivative. Consult the collection
declarations for the particular material and intended use.

The Nangate collection retains generated upstream copyright headers, including
legacy proprietary wording, alongside the Apache license and Silvaco/Si2 notice
from the pinned upstream publication. Preserve these declarations together;
source URLs are recorded in the case manifests.

For ferrosim-derived entries, the direct source is the pinned analog-db release.
Its per-circuit manifests supply the ferrosim attribution and MIT label; the
collection licenses link those manifests and retain their attribution and license
labels without adding a substitute ferrosim license text. Collection notices also
retain the upstream analog-db notice and explain its reference-only entry scope.
These records follow the direct source's declarations without claiming an
independent license grant from the indirect source. A case's `qualified` status
describes technical evaluation, not independent verification of copyright ownership
or permission.

## PDKs, tools and redistribution

PDK/model bundles, EDA tools and `third_party/` repositories retain their own
licenses and component notices. A circuit collection license is not a license
grant for separately sourced process collateral. Consult the pinned sources and
[resource preparation guide](docs/tools.md#external-sources) before redistributing
those resources or a tool image.

When distributing a collection or selected case materials:

- Include the applicable collection `LICENSE`, required `NOTICE`, source
  attribution and modification notices with the exported files. Retain additional
  component terms and fulfill the relevant license's source-distribution
  obligations where applicable.
- Identify noncommercial materials explicitly in the distribution description;
  do not label the whole checkout or task archive as MIT or unrestricted for
  commercial use.
- Preserve the connection between each asset and its applicable terms when
  changing directory layout. Review source and derived-artifact rights separately.

`Task.materialize()` produces isolated solver inputs, not a redistribution
package. Local prepared directories likewise are not certified distribution
bundles. Copying either directory does not ensure that notices or other required
source materials accompany it; assemble and review those before redistribution.
See the [task rights rules](docs/tasks.md#asset-rights) and
[release checks](CONTRIBUTING.md#ci-cd).
