---
name: add-case
description: "Create, promote, revise, or remove an ICLayout-Bench circuit case, including its documentation and schematic assets. Select validation by the actual circuit, evaluation, scoring, or presentation change."
---

# Add Case

Deliver maintained circuit materials, executable requirements and published
results that agree. This skill owns the workflow; the
[case development standard](../../../tasks/AGENTS.md) owns authoring conventions,
and the [task guide](../../../docs/tasks.md) owns schemas, scoring, documentation
and qualification. Apply those authorities to the requested scope.

## Select the change path

Locate Public three directories above this skill, read its `AGENTS.md`, and run
`git status --short --branch`. Preserve unrelated edits. For public cases, read
the case standard and task guide above. For hidden cases, follow the workspace
route and destination rules. Before inspecting source assets or historical
outputs, read the [input-isolation checklist](../../../docs/tasks.md#input-isolation).
Public designs and tool resources follow the
[asset-rights boundary](../../../docs/tasks.md#asset-rights).

Classify the actual change using the standard's
[change and evidence rules](../../../tasks/AGENTS.md#9-changes-and-completion):

| Request | Workflow |
|---|---|
| Design proposal only | Establish the circuit and evaluation contract, then deliver the proposal and unresolved decisions. Do not claim implementation or qualification. |
| Documentation only | Compare prose with the current configuration and declared materials; use the documentation checks below and hand off. Refresh affected digests and materialize inputs. An unchanged electrical contract does not require EDA reruns merely because the description identity changed. |
| Presentation only | Use the schematic binding steps below, verify preview loading and unchanged solver inputs, then hand off. A topology/netlist change uses the circuit path. |
| New case, promotion, or circuit/evaluation/scoring/resource change | Establish the contract, build the affected materials, and apply per-case and shared validation. A promotion may use applicable existing evidence under the qualification guide. |
| Rename or move | Update consumers, declarations, catalogs and navigation; verify identity, loading and materialization. Apply electrical validation if semantics also change. |
| Removal | Update catalogs, navigation, selectors and regression dependencies; preserve resources still used by other cases. Validate affected remaining consumers, then hand off. |

A Markdown edit that introduces a different requirement is a semantic change.
When work crosses paths, apply the checks for each affected responsibility.

## Establish the circuit and evaluation contract

Use the standard's [circuit contract](../../../tasks/AGENTS.md#1-circuit-contract-and-scope)
to establish function, authoritative topology, device parameters, ordered ports,
supply/body connections, permitted equivalences, operating conditions and
observable success criteria. Distinguish upstream facts, maintained choices and
unverified assumptions. Establish whether faithful reproduction or adaptation
is authorized; fidelity and agreement with upstream performance are separate
questions. Resolve routine choices within the user's scope; seek a missing
consequential decision only when existing authorization does not settle it.

Before encoding the plan, classify each observation under the standard's
[scoring rules](../../../tasks/AGENTS.md#6-evaluation-and-scoring): continuous
quality, a justified functional/domain bound, an unscored diagnostic, or a
measurement-validity check. For each, identify the producer, conditions, units,
window, consumer and failure meaning. Record the reason for each functional
bound and the same-condition source pairing and normalization for each scored
observation. Upstream targets alone do not justify hard gates.

Place measurement-validity checks on the path producing the observation, for
both source and candidate simulation. Confirm that invalid evidence produces an
evaluator error rather than a functional rejection; merely removing its score
weight does not change a bounded metric's failure meaning. Follow the task
guide's [decision contract](../../../docs/tasks.md#evaluation) for implementation.

**Ready to implement:** the circuit, rights, source relationship, observable
requirements and failure meanings are explicit. Every requirement has an
identified physical check or electrical measurement.

## Plan artifacts and tool support

Inspect a maintained collection and its cases, comparing declarations with
materialized files. Consult relevant cleanup history for artifact types being
introduced. Apply the current standard when older cases differ.

In working notes, map each proposed file to its owner, role, path/format,
consumer, solver visibility and provenance. Explain why an existing file cannot
serve the purpose; this is not a new maintained manifest. Use the standard's
[ownership](../../../tasks/AGENTS.md#2-ownership-and-directory-layout),
[file roles](../../../tasks/AGENTS.md#3-file-roles-and-naming) and
[license rules](../../../tasks/AGENTS.md#5-sources-licenses-and-reproducibility).
Identify affected input declarations, resource profiles, catalogs, docs, tests
and evidence identities before editing. Development recipes remain outside
solver inputs; Bench consumes static deliveries without importing Designs.

Map the circuit's devices and conditions to actual model, DRC, named-interface
LVS, geometry, extraction and measurement capabilities. Establish source
functionality with the intended stimuli/models and record unsupported conditions.
Choose numerical settings and waivers for this circuit and process; copying a
case's structure does not calibrate its limits.

Use the [architecture boundaries](../../../docs/architecture.md#ownership) and
[backend contract](../../../docs/tools.md#eda-backend-contract) for extensions.
Circuit-specific dispatch stays outside the runner, scoring core and harness.
For container validation, follow [image development](../../../docs/tools.md#image-development):
reuse a compatible image or thin derivative and check the full-build triggers.

**Ready to build:** every artifact has an owner and consumer, and every required
capability has a supported binding or an explicit unresolved gap. Implement
missing authorized capabilities or retain candidate status; narrowing scope
requires authorization. Before adding any regression or fixture, apply the
[test gate](../../../tests/AGENTS.md#before-adding-a-regression).

## Build and reconcile the delivery

Use the [configuration contract](../../../docs/tasks.md#task-configuration) and
[evaluation plan](../../../docs/tasks.md#evaluation-plan) to assemble the case.
Register catalogs and resource profiles as needed. Publish ready-to-use inputs;
preparation assembles resources rather than regenerating circuit materials.
Reuse verified support bundles and keep new run outputs in fresh directories.

For a schematic change, apply the
[presentation binding contract](../../../docs/running.md#task-presentations-and-interactive-layouts).
Keep the SVG outside solver inputs, update project provenance, embedded netlist
binding and asset digest together, and verify preview loading. Use presentation
revisions for historical results. Editable projects belong in the workspace's
source-asset location, not disposable build output.

Load and materialize the task; inspect the exact delivered files. Verify
standalone snapshots and exclusion of reference layouts, host configuration,
source checkouts and qualification answers. When exporting a distribution,
check that its applicable license/notices accompany the assets separately from
the solver materialization.

Apply [unified scoring](../../../docs/tasks.md#task-scoring): candidate-derived
extraction feeds post-layout simulation and independent source simulation feeds
the same-condition baseline. Freeze measurement selection, dimensions, pairings,
normalization and the documented area anchor before model evaluation. Preserve
existing coefficients during unrelated edits; authorized regrading follows the
scoring-change rules and retains historical coefficients on old results.

### Documentation checks

Use the [required sections](../../../docs/tasks.md#case-documentation), allowing
circuit-specific additions. Check content against the actual configuration and
declared materials, not just the presence of headings:

- Input paths/roles, ordered ports and their functions agree with the netlists.
- Conditions, loads, stimuli, measurement definitions/windows and units agree
  with the decks and jobs; each functional bound has a stated reason.
- Quality dimensions, source pairings, normalization, aggregation, area anchor,
  coefficient and failure/error meanings agree with the executable plan.
- The published solve budget, GDS top cell, destination, size limit, tool/resource
  discovery and explicit submission procedure match the runtime contract.
- The README maps maintained files and reports measured results with conditions,
  units, limitations and clean-checkout reproduction commands; prior validation
  is distinguished from fresh execution.

The configuration owns budgets, limits and scoring values. Generate their
published representations or check them against that authority, reusing existing
catalog/docs checks where possible. A passing schema or digest check does not
establish semantic agreement. Refresh affected description/input digests after
the final edit, then verify loading, materialization and links.

**Ready for qualification:** circuit, decks, problem, executable checks and score
agree; every published requirement has a consumer and each reported result has
an identified evidence source. Documentation/presentation-only work proceeds to
handoff after its selected checks.

## Qualify and hand off

For new or semantically changed cases, apply the
[per-case validation rules](../../../docs/tasks.md#qualification). Evaluate any
supplied reference through its declared physical gates, candidate extraction and
all required electrical conditions. Preserve reports and identities in fresh
`build/runs/` outputs and publish measured results in the README. Verify that the
prepared task and input snapshots match the intended revised contract.

Reuse shared rejection, error, scoring, transformation and repeatability coverage.
For changed validity checks, exercise valid/invalid observations through the
actual producer and evaluator; for changed functional gates, verify acceptance
and rejection at the relevant boundary. Add a regression only for a demonstrated
gap under the test gate. Use real tool evidence where physical/extraction behavior
is at issue; synthetic arithmetic does not qualify a layout. Calibrate when it
establishes limits or validates a changed model/extraction boundary.

Set status under the standard's
[qualification rules](../../../tasks/AGENTS.md#7-qualification-and-published-evidence).
A lower continuous quality score does not by itself invalidate qualification or
authorize optimizing the DUT. Reference-free cases disclose undemonstrated
post-layout feasibility and the basis of limits/area anchors. Preserve old
reports under their original identities; apply the change/evidence rules above
when reusing prior validation or obtaining fresh identity-bound evidence.

Check the final tree against the standard's
[completion checklist](../../../tasks/AGENTS.md#9-changes-and-completion) and run
the affected [verification](../../../CONTRIBUTING.md#verification). Report scope,
actual checks, remaining gaps and Git status. For electrical changes, include
witness/qualification status and calibration basis; for presentation changes,
report bindings and preview verification. Case qualification does not publish
website results; [handoff](../../../docs/architecture.md#result-handoff-and-storage-ownership),
commits and publication retain the session's authorization boundaries.
