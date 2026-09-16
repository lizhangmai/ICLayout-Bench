---
name: add-case
description: "Create, promote, or revise an ICLayout-Bench circuit case across PDKs and EDA backends. Apply the case development standard from contract and artifact ownership through isolated inputs, evaluation, scoring, qualification, and change validation."
---

# Add Case

Deliver a self-consistent case whose maintained circuit, layout requirements,
measurements, scoring and published evidence agree. This skill owns the authoring
workflow. The [case development standard](../../../tasks/AGENTS.md) owns artifact
roles, organization, and completion rules. Repository guides own schemas and
acceptance semantics; process resources and backend configuration own technology
and tool details. Apply the whole standard, including when revising an existing
case; satisfying one naming rule or copying a directory is not completion.

## Establish the contract

Locate the repository containing this skill (three directories above this
folder), follow its `AGENTS.md`, and inspect Git status. For public cases, read the
[case development standard](../../../tasks/AGENTS.md) and the
[task guide](../../../docs/tasks.md). Read the
[input-isolation checklist](../../../docs/tasks.md#input-isolation) before
inspecting source assets or historical outputs. For a hidden case, follow the
workspace routing and the destination repository's rules; keep hidden materials
in their authorized repository and reuse the public protocol.

Apply the workspace's public/hidden boundary to tools as well as source assets:
public cases use public designs and open PDK/EDA resources. Resolve restricted
materials through the authorized destination and
[asset-rights rules](../../../docs/tasks.md#asset-rights). A technically supported
backend does not by itself establish distribution rights.

Establish the circuit function, authoritative topology and device parameters,
ordered interface, permitted layout equivalences, operating conditions,
required measurements and intended qualification scope. Distinguish supplied
facts from design choices. Resolve choices within the user's authorization;
ask only for consequential missing decisions while progressing independent work.
For a design-only request, deliver this contract and the implementation plan
without claiming that a case has been built or qualified.

Attribute a referenced design with `origin.url` and preserve asset licenses under
[source requirements](../../../docs/tasks.md#task-design). Judge the maintained
circuit against its own contract. Upstream layout/netlist agreement is not a
qualification prerequisite. Describe modifications as current design choices;
source attribution in the README stays brief.

**Ready to implement:** the circuit, input rights, scope and observable success
criteria are explicit enough to implement without inventing hidden requirements.

## Plan ownership and artifacts

Before creating or moving files, inspect a maintained collection and its cases:
compare the actual tree with input declarations and materialized solver files.
Read relevant cleanup commits for the artifact types being introduced. Resolve
differences using the current standard; existing files demonstrate mechanisms,
not permission to repeat obsolete patterns.

Map the proposed case to the standard's
[ownership boundaries](../../../tasks/AGENTS.md#2-ownership-and-directory-layout)
and [file roles](../../../tasks/AGENTS.md#3-file-roles-and-naming).
In working notes, account for each artifact's owner, role, format, declared path,
solver visibility, source/license, consumer, and why an existing file cannot
serve that purpose. Distinguish maintained files from runtime copies. Include the catalog,
process resources, test helpers, and qualification evidence as
applicable. This is a development check, not another maintained case manifest.

Match artifacts by responsibility; choose technical settings from the actual
circuit and process. Use established roles and filenames, with any necessary
additional artifact explained in the README's Files section. Apply the
[license-file rules](../../../tasks/AGENTS.md#5-sources-licenses-and-reproducibility)
to the actual upstream declarations and copied components before adding license
or notice files. Keep optional artifacts absent until their consumer requires them.

For revisions, identify affected consumers before editing: input declarations,
resource profiles, catalogs, scripts/tests, documentation, and evidence identities.
Follow the standard's [change rules](../../../tasks/AGENTS.md#9-changes-and-completion)
for renames, removals, and semantic changes. Distinguish the requested change from
unrelated cleanup and preserve existing user work and prior evidence. For a
removal, skip construction of the deleted case and validate affected remaining
cases and shared dependencies before the final review.

**Ready to build the artifact set:** every proposed file has a justified owner
and consumer; solver inputs, distribution terms and maintainer assets are
distinguished; affected contracts and validation scope are identified. Every new
test or fixture satisfies the
[regression gate](../../../tests/AGENTS.md#before-adding-a-regression). Leave
unjustified files out of the maintained tree, including generator output.

## Resolve process and tool capabilities

Map the proposed devices and requirements to available model resources, physical
rules, connectivity comparison, geometry checks, candidate extraction and
simulation/measurement capabilities. Record supported corners and model or
extraction boundaries, including relevant body, substrate and passive-device
assumptions. First establish pre-layout functionality with the intended models
and stimuli; a source directory's name does not establish a performance target.

Use the [extension boundaries](../../../docs/architecture.md#ownership)
and [tool guide](../../../docs/tools.md#eda-backend-contract) to reuse or extend
the appropriate backend. Logical evaluation operations bind to tools through
configuration. A new case must not introduce circuit-specific branches into the
runner, scoring core or harness. A backend may use containers, native libraries
or controlled remote execution as supported by the repository.

Choose rule decks, device mappings, layers, units, ports, extraction options and
operating points from the selected process and circuit. An existing case is a
structural example, not a source of default rule waivers, disabled checks,
layer numbers, simulation settings or acceptance thresholds.

**Ready for evaluation:** each requirement has a supported measurement/check
and an identified tool/resource binding. When a capability is missing, implement
the authorized extension or report the specific gap and retain candidate status.
Narrow qualification scope only when that change is authorized and explicit.

## Build the case and calibrate scoring

Publish ready-to-use circuit materials and references. Keep schematic export,
material-generation scripts and intermediate files in development history;
loading and evaluating a published case must not require them.

Create the case in `tasks/<pdk>/<collection>/cases/<circuit>/` for a public task.
Implement the artifact map using the standard
[file roles and naming](../../../tasks/AGENTS.md#3-file-roles-and-naming) and the
[case configuration contract](../../../docs/tasks.md#task-configuration). Bind
files through their declared logical roles, and keep executable requirements,
trusted tool bindings, and source/qualification metadata in their designated
configuration sections. Register the collection entry and required process
profiles. Reuse existing preparation mechanisms; keep development outputs in
fresh `build/runs/` directories and preserve earlier evidence. Reuse verified support bundles when
appropriate instead of deleting and rebuilding them between checks.

Separate solver inputs from source records, references and host configuration.
Validate digests and materialize the declared inputs to inspect what the solver
actually receives. Keep collection licenses and required notices outside the
default solver input set; preserve them with material distributions. Consult
[shared collection inputs](../../../docs/tasks.md#shared-collection-inputs) for
explicitly shared solve inputs. Verify solver materialization against the input
list and, when an export is part of the change, inspect that export for the
applicable attribution outside solver inputs. A solve directory is not a material
distribution. Prepared standalone configurations must read their copied snapshots
rather than the original collection. Derive runtime
requirements and evaluator inputs from the same frozen definitions.

Apply the [evaluation plan contract](../../../docs/tasks.md#evaluation-plan):
physical validity and hard geometry checks precede candidate-derived extraction
and post-layout measurements. Specify every required observation's definition,
unit, conditions and acceptance limits. Simulation must consume the submitted
layout's extracted circuit; source simulation serves calibration. Define the
functional footprint using the selected process's relevant device and complete
routing layers, with explicit exclusions.

Apply the current [unified scoring contract](../../../docs/tasks.md#task-scoring)
and [batch semantics](../../../docs/tasks.md#task-scoring). Assign the task's integer
coefficient using the capability rubric; leave existing cases' coefficients
unchanged. Calibrate dimension assignments, zero-score boundaries and absolute
area anchors before model evaluation. Explain their basis and validate their
behavior with measurements; neither a copied case's constants nor a changing
reference-layout ratio establishes calibration. Keep electrical acceptance,
partial attainment and area utility distinguishable within the single score.

Write both Markdown files using the exact
[documentation templates](../../../docs/tasks.md#case-documentation). Keep the
solver contract self-contained in delivered inputs and runtime metadata. Put
measured reference results and reproducible commands in the README, with units,
conditions and limitations. Refresh affected input digests after editing.

**Ready for qualification:** audit every artifact against the ownership map and
standard. The catalog/configuration loads; materialization contains exactly the
intended inputs with valid digests; source records, testbench measurements,
problem requirements, executable plan and scoring agree. Every requirement has a
measurement/check and every published result has an identified evidence source.

## Qualify the case

Apply the [per-case validation rules](../../../docs/tasks.md#qualification):
check input materialization and circuit/contract consistency, then independently
evaluate any supplied reference through the declared physical and post-layout
checks. Publish results and reproduction commands; preserve generated reports and
identities under `build/runs/`.

Consult shared evaluator regressions for rejection, scoring, error handling,
equivalent transformations and repeatability. Close demonstrated coverage gaps
under the regression gate established above; a new case or PDK alone does not
justify another test circuit. Use pre/post-layout calibration when
it supports a limit or validates a new flow. Reuse established mechanism coverage;
a complete counterexample matrix and an area variant are not required per case.

Set `qualified` when applicable case checks pass. Keep `candidate` for unresolved
material, consistency, reference-execution or capability gaps. For reference-free
cases, disclose feasibility and limit/area-anchor bases as the guide requires.
Formal [admission](../../../docs/admission.md) is a separate workflow.
Maintain the declared circuit and acceptance limits during validation.

## Review and hand off

Run the standard's [completion checks](../../../tasks/AGENTS.md#9-changes-and-completion)
against the final tree and generated results. Trace each requirement from the
problem through the testbench/check, evaluation observation, acceptance/scoring
rule, and evidence. Inspect tracked changes and untracked files; trace each artifact
to its declaration and consumer, including collection files and generated fixtures. Resolve
unexplained discrepancies before reporting completion, including stale references,
misplaced shared helpers, inconsistent roles, and unsupported status claims.

For changed input paths or contents, verify materialization and identity bindings
again. Rerun checks affected by executable changes; distinguish prior validation
from fresh identity-bound reports and preserve old reports as old evidence. For removals, verify remaining task discovery and
shared dependencies. Check that a reader can run the published reproduction
commands with the declared resources.

Finish with the affected checks from
[CONTRIBUTING](../../../CONTRIBUTING.md#verification), reading
[test conventions](../../../tests/AGENTS.md) when editing tests. Report the case's
function, supported scope, qualification and witness status, coefficient and
calibration basis, artifact/contract consistency, actual verification results,
remaining gaps and Git status.
Respect the session's commit and publication instructions; adding a case does
not authorize a push or an external release.
