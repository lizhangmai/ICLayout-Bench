# Case Development Standard

Applies to creating, promoting, modifying, reorganizing, and removing public cases
under `tasks/`, across all PDKs and source collections. This file owns authoring
conventions; the [task guide](../docs/tasks.md) owns schemas, scoring semantics,
documentation templates, and qualification requirements. The
[tools guide](../docs/tools.md) owns resource preparation and backend contracts.
Use the [add-case workflow](../.agents/skills/add-case/SKILL.md) to apply this
standard. A schema-valid directory is not, by itself, a conforming or qualified case.

## 1. Circuit Contract and Scope

Before creating files, establish the circuit's function, authoritative topology,
models and device parameters, ordered ports, supply/body connections, permitted
layout equivalences, operating conditions, and observable success criteria.
Distinguish upstream facts, maintained design choices, and unverified assumptions.
Source names, device counts, and upstream simulation claims do not establish the
maintained task's requirements or difficulty.

Map each requirement to a supported physical check or electrical measurement.
Declare extraction/model boundaries and unsupported conditions explicitly. Resolve
routine choices within the user's scope; present a concrete proposal before an
unauthorized change to circuit topology, DRC disposition, acceptance limits, or
qualification scope. A missing capability remains a gap until implemented or
explicitly excluded from the authorized contract.

## 2. Ownership and Directory Layout

Use one circuit per `tasks/<pdk>/<collection>/cases/<circuit>/`. Assign every file
a role and owner before adding it. The same role has the same location across PDKs;
process-specific implementation belongs in resources and backend configuration.

Before creating files, inspect an existing collection and its cases, plus relevant
cleanup commits. Establish what is shared, what is case-local, and what is generated
only at runtime. Use the current standard to resolve differences with older cases.
Each added file needs a concrete consumer and a reason existing files cannot serve
that purpose; a template or generator producing it is not such a reason.

| Owner | Maintained contents |
|---|---|
| PDK | `pdk.toml` defines reviewed tool/model preparation profiles; source collection directories hold the cases. Keep shared preparation instructions in the tools guide. |
| Collection | `catalog.toml` indexes cases; `README.md` provides collection navigation and scope; retain required collection licenses/notices. |
| Case | `case.toml`, `problem.md`, `README.md`, declared `materials/`, and optional `reference/` as defined below. |
| Framework | Public task/schema/scoring definitions in `benchmarking/`; shared preparation, evaluation and EDA backends in Public `layout_eval/`. Circuit-specific dispatch stays outside the runner, scoring core, and harness. |
| Tests | Regressions and fixtures admitted under the [test conventions](../tests/AGENTS.md#before-adding-a-regression). Circuit-specific witness assets and results belong with the case; exploratory circuits and generators remain local development materials. |
| Local development | Fresh `build/runs/` outputs, prepared bundles under `build/support/`, and development history in Git. Generated reports, netlists, waveforms and their archives stay here; case READMEs publish results and commands to reproduce them. |

Keep case configuration consolidated: tool instructions belong in `problem.md`,
backend bindings in `case.toml`, and constraints/scoring in its inline task tables.
Do not introduce parallel `tools/`, `maintenance/`, standalone constraint files,
or separate scoring plans for a new public case. Framework support for legacy
layouts does not define the authoring convention.

## 3. File Roles and Naming

| File or directory | Contract |
|---|---|
| `case.toml` | Single configuration entry point: identity, task inputs/output, constraints, evaluation, toolchain, source attribution, and maintainer asset/qualification records. |
| `problem.md` | Complete solver-facing circuit and acceptance contract; input role `description`. |
| `README.md` | Maintainer/reader overview, file map, reference results, reproduction, and source attribution; excluded from solver inputs. |
| `materials/circuit.<format>` | Authoritative circuit, using the actual format suffix (`.cdl` or `.spice`, for example); input role `netlist`. A separate simulator representation, when required, uses role `simulation` and must describe the same circuit. |
| `materials/testbench.spice` | Main SPICE simulation testbench; input role `performance`. Supplies stimuli, bias, loads, analyses, measurements, and waveform export. |
| Collection `LICENSE` and required upstream notices | Store shared terms once at collection level, outside solver inputs. Preserve applicable terms with repository distributions and material exports; retain separate component attribution where required. |
| `materials/` supporting files | Only required declared inputs, named by their function and format. Use configuration parameters for operating-point variants of one testbench; separate decks are justified by distinct analyses or tool requirements. |
| `reference/` | Ready-to-use witness GDS when supplied. Record qualification results and reproduction in the README; generated run evidence stays under `build/runs/`. Name GDS files by circuit/top-cell identity and declare them in the case's asset records. |

Use role-based names consistently; a new PDK or author preference is not a reason
to invent another name for the same artifact. Keep public IDs, port/subcircuit
names, and declared paths stable during unrelated edits. For additional artifact types,
first check the existing role and format conventions; explain a necessary extension
in the case README's Files section. Optional directories exist only when used.

## 4. Configuration and Input Isolation

Follow the [configuration contract](../docs/tasks.md#task-configuration). Organize
`case.toml` into identity, executable task, trusted toolchain, and maintainer metadata;
keep related tables together and arrays readable. Use existing logical input roles,
operation names, units, and scoring fields. Filename spelling is an authoring
convention; runtime routing must use declared roles and paths.

Every solver input must have its path, format, and digest declared in
`[task.inputs]`, with an identified use in solving the circuit task. Repository
membership and redistribution obligations do not make a file a solver input.
Declare the target subcircuit, GDS top cell, output path and size
bound explicitly. Materialize the task and inspect the resulting files: the solver
receives only its declared inputs and reviewed resources. Host configuration,
source checkouts, witnesses, generators, and qualification answers remain outside
that input set. Read the [historical asset exclusion checklist](../docs/tasks.md#input-isolation)
before inspecting source assets or earlier outputs.

Use one frozen definition for executable requirements and evaluator inputs. The
problem describes that same contract; the README reports measured results. Host
paths, backend implementation details, and evidence archives cannot carry an
otherwise undisclosed solver requirement.

## 5. Sources, Licenses, and Reproducibility

Keep case attribution to the upstream circuit URL under the
[source and rights rules](../docs/tasks.md#task-design). Bind digests to maintained
inputs and references; catalogs only index cases. Publish ready-to-use materials;
keep authoring scripts, intermediate schematics and export logs in development
history. Resource preparation only assembles PDK/tool bundles.
Distinguish untouched upstream assets from case-owned derivatives; retain required
copyright, license, and modification notices with the corresponding exported assets.
Store shared terms once per collection and keep the framework license separate
from upstream component terms. Collection scope follows source provenance;
identical license names alone do not merge unrelated source collections.

`task.inputs` contains files needed to solve the task. License and attribution
files belong to distribution metadata, not the default Agent input set. Keep
them with the collection and preserve them when exporting its materials;
`Task.materialize()` creates solver inputs, not a redistribution package.

Before adding license-related files, inspect the actual upstream declarations
and existing collections. Use a collection `LICENSE` by default; `NOTICE` is
optional, not a template companion. Retain an upstream NOTICE when applicable;
create a separate notice only for an identified attribution requirement that
the existing files cannot satisfy. Keep copied component terms attributable in
LICENSE and dependency-only terms with the resource that distributes them.
Describe current circuit/layout modifications in the case README and appropriate
source-file headers. Qualification status, pending calibration and development
history do not belong in license or notice files. Removing an unnecessary file
also removes its input declaration and links and refreshes affected digests.
Public designs and PDK/EDA resources must meet the workspace's public-use boundary.

An upstream layout/netlist mismatch does not invalidate an independently maintained
circuit, but modifications must agree across its authoritative netlist, simulation,
problem, and witness. Qualification consumes the maintained netlists and
candidate-derived extraction.
Resource versions and tool commands come from their owning manifests and guides.

## 6. Evaluation and Scoring

Follow the [evaluation plan](../docs/tasks.md#evaluation-plan) and
[unified score](../docs/tasks.md#task-scoring) contracts. Each case must establish:

- Artifact, DRC, named-interface LVS, and hard geometry checks on the submitted GDS;
  any intentional waiver is explicit, justified, and bound to the case plan.
- Candidate-derived parasitic extraction followed by simulation consuming that
  extracted circuit. Source simulation provides pre-layout calibration only.
- For every required observation: operating point, stimuli/load, measurement and
  time/frequency window, unit, limits, scoring dimension, and zero-score boundary.
  Evaluate every required condition; aggregation cannot hide a failure.
- A complete functional footprint, including relevant device and routing layers,
  with explicit exclusions; fixed absolute area anchors supported by feasible
  layout evidence, independently of a changing witness or submitted layout area.
- An explicit integer coefficient justified by the capability rubric, frozen before
  model evaluation; physical rejection, electrical failure, full acceptance, and
  evaluator error must retain the unified score's distinct meanings.

Structural conventions are shared; model classes, layers, rule choices, supply,
loads, tolerances, and limits must be derived for the actual circuit and process.
Copying another case's numerical settings or waivers is not calibration.

## 7. Qualification and Published Evidence

Apply the [case and evaluator validation rules](../docs/tasks.md#qualification).
Each case must have consistent, independently usable inputs and a passing actual
evaluation of its supplied reference. Keep measured results, limitations and
reproduction commands in the README; generated evidence belongs under `build/runs/`.

Common rejection, scoring, error, transformation and repeatability checks belong
in shared regression tests. For new devices, extraction methods or special judging
rules, identify the coverage gap and apply the
[regression gate](../tests/AGENTS.md#before-adding-a-regression) before adding tests
or fixtures. Calibrate when needed to establish limits or
validate a new flow; reuse established coverage elsewhere. Per-case area variants
and complete counterexample matrices are not status prerequisites.

Set `qualified` after the applicable per-case checks pass; keep `candidate` for
actual material, consistency, execution or capability gaps. Reference-free cases
follow the guide's feasibility disclosures. Formal admission remains separate.

## 8. Documentation

Write in English using the exact [case documentation templates](../docs/tasks.md#case-documentation).
The problem must be self-contained for a solver. The README must map maintained
files to their roles and report reference measurements with units, conditions,
scoring/calibration basis, limitations, and commands runnable from a clean checkout.
Link shared setup instructions to their owning guide. Keep source attribution brief;
keep experiment chronology and discarded results out of reader-facing documents.

## 9. Changes and Completion

Treat additions, promotions, renames, removals, and semantic changes as case changes:

| Change | Required follow-through |
|---|---|
| New case or PDK | Assign file ownership, use the role conventions, register catalog/resources, and complete contract, materialization, and qualification checks. |
| Rename or move | Update callers, configuration, docs, and affected digests; verify delivered inputs and preserve circuit/scoring semantics. Check task identity even when file contents are unchanged. |
| Circuit, judge, resource, or scoring change | Rerun affected case checks and shared mechanism regressions; calibrate when the changed limits or flow require it. |
| Removal | Update catalogs, navigation, selectors and regression dependencies; retain resources/controls still required by other cases under their correct owner. |

Preserve previous evidence in development history. When a change invalidates its
identity binding, generate evidence for the new task; do not relabel old reports as
new executions. Pure documentation changes require only the affected checks from
[CONTRIBUTING](../CONTRIBUTING.md#verification), plus any input/identity updates.

Before handoff, verify all of the following against the actual files and results:

1. Every maintained artifact, including untracked files, has a justified consumer
   and the correct owner, role, name, and declaration. Collection files are not
   duplicated under individual cases; optional files have an identified need.
   Collection navigation and public membership agree with the task set.
2. Configuration loads, materialization contains exactly the intended inputs,
   and every input serves the solve. Distribution terms remain with their assets
   outside the default input set. Links/commands resolve, and no stale paths or
   digests remain.
3. Circuit, testbench, problem, executable checks, scoring, and README results
   describe the same contract; evidence supports the current qualification status.
4. Affected verification passes, with required tests following [test conventions](../tests/AGENTS.md).
   Report actual scope, gaps, and Git status; preserve unrelated changes and follow
   the session's commit/publication authorization.
