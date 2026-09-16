> Historical development record for the 0.2 migration. Its ownership tables and
> commands describe that stage, not current usage. Version 0.3 restores the shared
> evaluator and local service to Public; see [architecture](architecture.md) and
> [running](running.md) for the current two-path workflow.

# Public Harness and Private Evaluation Service: Refactoring Plan

Status: stages 1–4 are implemented and locally validated (2026-09-16).
Public owns participation and analysis; Private owns trusted execution and reruns.
This completes the software migration and public-development acceptance. It does
not claim a hosted deployment or qualification/publication of real hidden tasks.

## Goal and ownership

`Layout-Bench` becomes the open-source official participant harness, generic
client, public protocol, public development tasks and result analysis toolkit.
`Layout-Bench-Private` becomes the evaluation service: isolated EDA workspaces,
task delivery, submissions, independent judging, hidden tasks and official runs.

Participants run their existing Claude Code or the official harness locally.
They need a service endpoint, not private source or a Claude-specific image.
EDA execution and final judging remain isolated and controlled by the evaluator.

Source dependency remains Private → Public. Private pins the public protocol and
shared definitions. Public installation and CI must not import Private.
Credentials and growing run artifacts remain outside Git. Hidden inputs and
restricted tools retain their source, authorization and disclosure requirements.

## Public modules

- Protocol: task, session, submission, diagnostic, opinion and result contracts.
- Client: HTTP client, Python interface and CLI; MCP can be added later.
- Official harness: model calls, context, prompts, tool orchestration, output
  budgets, early submission and recovery policy.
- Analysis: statistics, tables, plots, missing-data handling and result comparison.
- Public tasks: development inputs, reference materials and qualification examples.
- Documentation: scoring formulas, metrics, failures, tools and integration guides.

Custom participant harnesses use the same client contract without implementing
the official harness internals. Model, harness, prompt, tools and budgets jointly
define a condition; official and custom harness results must be labeled separately.

The public package alone will not provide full offline evaluation. Provide an
accessible development service. A protocol simulator supports client tests only
and must never produce results represented as real measurements.

## Private modules

- Service: authentication, session lifecycle and external operations.
- Execution: EDA containers, authorized resources, scheduling and budget enforcement.
- Evaluation: independent DRC/LVS, geometry, performance and score computation.
- Tasks and qualification: hidden designs, authorization, witnesses and counterexamples.
- Evaluations: suite selection, frozen conditions and official rerun plans.
- Deployment: environment, storage and optional controlled inference gateway.

Start with one service process managing containers. Distributed scheduling,
cluster infrastructure and a leaderboard website are not prerequisites.
Public scoring specifications remain auditable; private execution is authoritative.

## Session contract

Expose session creation/status/closure, scoped file reads and writes, command
execution/status/cancellation, diagnostic checks, candidate submission, participant
opinions and result retrieval. Long commands return execution identifiers.

Required semantics:

1. Credentials and paths are scoped to one session, with bounded files and responses.
2. The server enforces deadlines, resource limits and diagnostic budgets.
3. Disconnects do not pause time; explicit closure, crashes and expiry have defined outcomes.
4. Submission retries are idempotent and return durable receipts with candidate
   digest, submission identifier and server acceptance time.
5. Acceptance means delivery, not physical validity. Preserve the last-accepted
   candidate rule during migration unless explicitly versioning a change.
6. Final judging consumes immutable accepted snapshots in a separate trusted
   environment, never the mutable solver workspace.
7. Diagnostics bind to snapshots; opinions are separate and cannot affect scoring.
8. Responses cannot reveal hidden references, other tasks, private host paths or secrets.
9. Results distinguish server observations, participant reports and unknown values.
10. Protocol versions and compatible public/private revisions are explicit.

## Trust and publication

Distinguish local development, service-recorded evaluation and evaluator-operated
verified reruns. A service can validate a GDS and record interactions without
proving the claimed model generated it unaided. Official verification freezes
conditions and records execution and model access under evaluator control.

The controlled inference gateway is optional for ordinary participation. Record
whether usage is gateway-observed or participant-reported; never replace unknown
usage with zero. Provider identity and data handling have independent trust assumptions.

Reports and plots retain task/tool versions, model/harness conditions, budgets,
candidate identity, verification level and missing-data status. Hidden-task
exports pass disclosure review before publication.

## Migration map

| Existing responsibility | Destination |
|---|---|
| Sessions, snapshots and container control | Private service/execution |
| Evaluation backends and trusted preparation | Private evaluation/execution |
| Controlled inference gateway and credentials | Private optional capability |
| Model calls and solving policy | Public official harness |
| Submission/diagnostic/opinion client helpers | Public client |
| Shared task/result definitions | Public protocol |
| Scoring specification | Public documentation; Private execution |
| Statistics, tables and plots | Public analysis |
| Internal audit, raw evidence and restricted export | Private |
| Public task/reference materials | Public; fetched and frozen by Private |

Split mixed orchestration in `agent.py` and `swarm.py` by responsibility rather
than moving whole files mechanically. Preserve validated judging semantics.

## Delivery stages

### 1. Contracts and baseline

Inspect Git state and preserve existing work. Verify Private Git initialization.
Update workspace routing, repository instructions, architecture and onboarding.
Specify lifecycle, errors, versions, deadlines, idempotency and results. Clearly
separate target behavior from currently executable workflows.

Acceptance: a client can be implemented from public documentation without private
source or paths.

### 2. First real workflow

Reuse existing EDA/judging code behind a minimal Private service. Implement the
Public client. Run a locally installed participant harness against `cell_6t`
without a vendor-specific image. The first integration used Codex and its existing
model configuration by user choice; Claude Code uses the same interface. Capture
real model calls, a model-generated candidate, server receipt, independent verdict
and analysis data.

Acceptance: a genuine candidate reaches independent evaluation. Physical failure
is reported honestly; a dummy layout, copied reference or operator-written
candidate cannot stand in for model output. Passing the task is not required to
establish the integration works.

### 3. Complete migration

Move service execution and judging to Private; complete the official harness and
shared client. Test Public against a protocol simulator and Private against real
EDA. Replace old entry points only after validating the new workflow.

Acceptance: Public installs/tests independently; Private pins compatible public
contracts; real execution needs neither previous `build/` files nor private
source on the participant machine.

### 4. Verification and publication

Freeze official conditions, implement rerun evidence and trust labels, validate
hidden-material access and disclosure, and export analysis without conflating
missing, failed, unsubmitted or infrastructure-error outcomes. Expand task and
repetition coverage after the workflow is stable.

## Validation and implementation constraints

Test client compatibility, retries and recovery; server isolation, budgets,
snapshots and judging; and cross-repository real EDA workflows. Rerun affected
reference/counterexample controls when moving evaluation code. Generated `build/`
content remains disposable. Reuse compatible EDA images. Check and commit each
repository separately; never mutate implementation/configuration during a live
run. Deliver the real workflow before expanding infrastructure.

## Migration checkpoint: 2026-09-16

The existing implementation is preserved before refactoring. Private has been
initialized as an independent Git repository. The separate participant trial and
its Benchmark working copy are also committed; they are historical integration
evidence rather than the new service implementation.

Ruff, documentation links, distribution build, 525 unit tests and seven participant harness tests
passed at this checkpoint. The container session suite had 17 failures: Docker
cannot apply CPU limits in the current host configuration. A minimal reproduction
is `docker run --rm --network none --memory 64m --cpus 1 --pids-limit 16
--entrypoint python layout-bench-tools:dev -c 'print("container smoke")'`.
The daemon reports `NanoCPUs can not be set, as your kernel does not support CPU
CFS scheduler or the cgroup is not mounted`. Fix the host resource-control setup
before claiming container acceptance; do not silently remove resource limits.

No real bridge2 model candidate was submitted. Its run stopped at container
creation with zero forwarded model requests. This is historical evidence; the current implementation checkpoint follows below.

## Contract checkpoint

Stage 1 defines the HTTP wire contract in [architecture](architecture.md#http-session),
updates repository ownership and preserves legacy execution during migration.
The public and private migration baselines are `833a3b8` and `a33a5f4`; the
participant trial baseline `c7b679e` remains historical evidence. The HTTP implementation checkpoint below describes the stage 2 boundary.

## HTTP implementation checkpoint

The public generic client and result-table exporter now connect to the Private
local service adapter. That adapter reuses DockerSession, RunRecorder, immutable
snapshots and run_agent evaluation rather than introducing another container
runtime or database. One container lives for the session; commands execute inside
it. CPU quotas remain enforced after host configuration repair.

Public client tests cover transport failures, explicit retry, response integrity
and credential-safe redirects. Private real-container tests cover the HTTP seam,
receipt replay, archived bytes, file isolation and command cancellation. The
reproduction commands are in each repository's running/validation guide. These
tests are synthetic protocol checks, not model scores.

Stage 2 subsequently completed with the locally installed Codex harness and its
configured model, as approved for the first working integration after the Claude
provider rejected authentication. The model created and submitted real candidates
through the generic client; the final frozen snapshot reached independent
evaluation and JSON/CSV export. This establishes the integration path, not an
official harness score or verified rerun. Private retains the development record;
raw local trial artifacts are not a public benchmark release. Claude-specific
authentication remains separate from the common interface.

## Stages 3 and 4 completion

Trusted preparation, sessions, EDA backends, raw evidence and admission now live
in Private `layout_eval`. Public has no Private imports and its wheel installs
independently. Private requires Public `0.2.0a1`; operator reruns freeze complete
source and tool identities. The official Public observe/action loop and custom
harnesses use the same HTTP client. Legacy operator entry points moved to Private.

The operator rerun workflow freezes model/harness/task/resource/tool/budget
conditions before execution, verifies complete scheduled evidence and exports
results with explicit trust and nullable usage. Public analysis keeps conditions
separate and distinguishes missing, failed, unsubmitted and infrastructure-error
outcomes. Hidden admission/disclosure regressions retain the existing conservative
policy; the public-task rerun exporter rejects hidden datasets.

Acceptance included Public 98 and Private 438 unit tests, 19 container tests,
2 HTTP tests, 2 rerun/tamper tests, and 4 real EDA reference/counterexample checks.
Four actual official-harness model runs used two public tasks with two independent
repetitions: cell_6t passed at 99.74071429 and 99.46071429; NAND2_X1 passed at 100
and 100. Each final GDS was generated by the model, accepted with a receipt and
independently evaluated. Conditions and verification levels remain distinct from
the earlier custom-harness trial. JSON, CSV and SVG/PDF exports were exercised.

Private retains the curated development record, frozen manifest and disclosed
four-attempt results. The public running guide and Private README give executable
reproduction steps using newly generated directories. Raw run evidence remains
outside Git. These small public-development measurements are not a model ranking.
Real hidden designs still require rights, qualification and disclosure approval;
optional HTTP diagnostics/opinions remain unadvertised with zero budgets. No
external release, remote identity certification or production deployment was made.
