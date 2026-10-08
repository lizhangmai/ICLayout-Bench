# Contributing and Verification

Public owns participant code, shared definitions, preparation, isolated sessions,
EDA backends, independent evaluation and the local HTTP adapter. Operators own
operator admission, controlled reruns and reviewed releases. Public installation
and CI must not import operator applications. Exclude `third_party/` from framework
searches, lint and tests.

## Implementation map

Keep declarations, execution and presentation with their owning modules:

| Package or module | Responsibility |
| --- | --- |
| `evaluation/` | Frozen plan contracts, requirements, baseline pairing, parsing and task scoring. `graph.py` owns candidate job ordering, transitive dependencies and source graph correspondence; parsing owns declaration decoding. `benchmarking.evaluation.scoring` owns the installed scoring entry points. `benchmarking.evaluation` retains its import interface. |
| `engine/contracts.py` and `engine/evaluate.py` | Backend result contracts and independent evaluation orchestration. Backends import the contracts without importing the executor. |
| `engine/toolchain_config.py` and `engine/toolchains.py` | Toolchain declarations and support-profile validation without EDA imports; binding to selected trusted backends through a lazy installed registry, respectively. |
| `engine/sessions/` | `config.py` owns frozen solver configuration; `execution.py` owns recorded independent runs; `control.py` supervises live sessions; `recorder.py` and `archive.py` write and read durable evidence. `staging.py` owns declared read-only inputs; `docker.py` owns the container, sockets and bounded console evidence. Workspace and protocol modules own durable control requests. Consumers import these owning modules directly; file/lease primitives come from `benchmarking.files` and `benchmarking.locking`. |
| `engine/feedback.py` | Participant diagnostics, evidence truncation and score observation projection. |
| `service/application.py`, `controller.py` and `views.py` | HTTP framing and route translation; atomic authenticated session reads, mutations and replay; pure status and result projections, respectively. The adapter composes a `SessionController`, which owns the lock and runtime supervision. Callers may inject a dedicated `SessionControl` through the constructor, including its runner and session factory; controller shutdown owns that supervisor's sessions. `ServiceState` owns durable records. |
| `engine/sessions/control.py`, `archive.py` and `service/state.py` | Live runtime supervision, shared reading of ordered committed journal events and run evidence, and durable HTTP projection, respectively. Only a final line without a newline may be ignored when reading a live journal; malformed committed lines and sequence gaps are errors. |
| `participants/planning.py`, `attempt.py`, `launch.py` and `runner.py` | Paired condition records, frozen attempt identity, scoped native CLI preparation and participant lifecycle/recovery. `ParticipantSelection` keeps the public condition separate from private environment/settings, which travel only over the worker pipe. Preparation returns a complete `LaunchContext`; adapters construct commands from that context, including its current continuation prompt. Neither private launch type is a result format. `ParticipantAttempt` owns state transitions and commits them before publishing the in-memory state. Adapters own CLI metadata and native event interpretation; `recovery.py` owns continuation safety and bounded capacity decisions. The runner executes those decisions and rechecks deadline/tool state after waiting. |
| `participants/storage.py`, `case.py`, `batch.py`, `worker.py` and `terminal.py` | `CaseRecord` owns scheduling records and durable summary commits; case execution and collection use one terminal export/cleanup/preview/outbox path. The scheduler dispatches bounded work; independent workers retain case leases beyond scheduler exit. Local services are recovered only through recorded process identities. |
| `engine/sessions/archive.py`, `participants/evidence.py`, `results/participant_export.py` and `participants/terminal.py` | Read frozen evaluator evidence; read and redact participant runtime files; export explicit `ParticipantEvidence` and `AttemptEvidence` records without inspecting runtime paths; then commit terminal state before releasing private runtime data. Failed attempts retain each session's candidate and checks separately. |
| `harnesses.py` | Shared harness declarations and portable participant-tool scheme identities, independent of result storage and participant execution. |
| `participants/adapters/contracts.py` and `adapters/__init__.py` | One declaration of installed harness modules derives the accepted harness names; lazy lookup and adapter operations share that declaration. |
| `engine/backends/hbt/` | Connectivity and passive proofs produce a validated replacement plan; merge only applies approved cards and preserves distributed RC. |
| `engine/netlists/spice.py` and `dspf.py` | Shared SPICE continuation handling, source line indices, quoted tokens and scalar values; strict native DSPF interface adaptation, respectively. HBT extraction and result schematics share lexical rules while owning their device/model interpretation. |
| `files.py` and `engine/tools/docker.py` | Validated asset snapshots and installed-resource provenance; Docker execution and read-only bind arguments, respectively. Solver staging and evaluator tools use the same Docker transport without putting container arguments on the shared resource type. |
| `engine/backends/calibre_config.py` and `calibre.py` | Typed rule, DRC, LVS and RC declarations and operation validation; shared rule binding, strict LVS/CCI controls and result acceptance. Docker and native adapters own execution. StarRC and Quantus select CCI extraction from construction and reuse the same controls/deck preparation. Backend identities include the grouped configuration and its implementation. |
| `engine/backends/spectre.py`, `spectre_x.py`, `spectre_aps.py` and `spectre_native.py` | Shared simulation and measurement acceptance; explicit X/APS command options; Docker or native tool construction. Docker owns its memory allocation, while native construction accepts only host execution settings. |
| `results/` | Export validation, analysis, plots, reports, previews, delivery outbox and optional SQL archives. Artifact validation in `importing.py` precedes transactional metadata import in `store.py`. |

Preview and outbox operations do not require the SQL results extra. Presentation
code uses ResultStore operations rather than accessing its SQL engine. When changing
installed module paths, migrate consumers and documentation to the owning modules
and remove superseded aliases. Include new evaluation/session files in their recorded source identities.

<a id="verification"></a>

## Verification

Choose verification by change scope and delivery stage:

| Stage or change | Required verification |
| --- | --- |
| Before a local commit | Review the diff, run `git diff --check`, and run checks relevant to the changed behavior. For documentation edits, inspect changed links and commands; example configuration edits need parsing/configuration checks. |
| Before pushing, or in PR CI | Run the full offline checks below, including the distribution build and isolated wheel installation smoke test. PR CI may satisfy this stage; successful local checks for the same revision need not be repeated before pushing. |
| Packaging, dependencies, package structure, entry points, or bundled resources change | Run the affected build and isolated wheel checks before committing, so packaging failures are caught during development. |

Routine local commits do not require a distribution build or isolated wheel test.
The affected container, evaluator, and task qualification checks below still apply
when their behavior changes. Report which checks ran and which are deferred to CI.

Reuse the checkout's existing `.venv` for local development and checks. Inspect
its interpreter and installed dependencies before changing it; repair this environment
instead of creating a task-specific Python installation under `build/`, `.local/`
or a temporary directory. The independent participant environment documented in
`examples/README.md` uses an existing installed-package environment; experiments
reuse it without per-run installation or upgrades.
Use the maintained CI wheel-isolation job when that release gate is required.
Build directories hold disposable artifacts, never an alternative runtime or
the only copy of experiment evidence.

From Public, the full offline checks need neither Docker nor operator applications:

```bash
uv sync --locked --extra results --group analysis
uv run --locked ruff check .
uv run --locked --group analysis pytest -m unit
uv build --out-dir build/dist
git diff --check
```

After building, run the isolated wheel installation smoke test defined in
[the checks workflow](.github/workflows/checks.yml). The command list above builds
the distributions; the smoke test separately verifies the installed wheel.

Package metadata is derived from Git tags by `setuptools-scm`; untagged commits
receive development versions. Build from a checkout with full tag history or a
built source distribution. Wheel metadata and the embedded source commit preserve
the identity without Git at runtime. After changing commits or tags, synchronize
the editable installation before running source commands. Do not maintain a
separate version literal in project metadata.

Check built distributions from outside the checkout or with Python `-I`, and
assert that imports come from the installation environment. A source-tree import
cannot validate a wheel. CI runs a short check with `python -I` after installation:
imports must come from the installation, version metadata must match the build,
and the participant runner, service and evaluator CLI must start. Routine local
changes reuse the formal environment and relevant tests. Leave clean installation
checks to CI unless the change affects packaging or an independent local check
is explicitly needed.
The wheel includes `benchmarking` and its subpackages with their
runtime data; it excludes operator modules. Use the default `uv build` command
above: it builds the wheel from a fresh source distribution, keeping retired
modules in a checkout's `build/lib` out of the wheel. Direct wheel builds from a
checkout require a clean build tree.
Follow [test conventions](tests/AGENTS.md)
before adding regressions.

Keep one owner for each tested behavior. `test_catalogs.py` checks catalog
ownership, qualification metadata, SPICE interfaces and isolated materialization
in one traversal of every declared case. `test_evaluate.py` owns execution and
verdicts; `test_scoring.py` owns score arithmetic and baseline semantics.
`test_hbt_extraction.py` owns HBT conversion, correspondence and extraction
diagnostics; `test_run_config.py` owns runtime and harness configuration.
Extend these existing checks instead of repeating their setup in new files.
Use parameter combinations when the dimensions interact; otherwise retain a
representative success and failure for the public behavior. Related assertions
should reuse one workflow, such as materializing a frozen task and refusing to
overwrite it. Do not maintain unused Agent implementations just to test those
implementations. Test counts include parameter expansion and are not a target.

The offline suite prioritizes the following contracts:

| Area | Retained scope |
| --- | --- |
| Published tasks | Every catalog case, declared files, solver isolation, SPICE interfaces and resource bindings |
| Evaluation and scoring | Candidate-derived evidence, validity and failure precedence, unknown versus zero, source pairing, normalization, per-metric caps and the 0–100 score contract |
| Extraction | Representative DRC/geometry failures, HBT device correspondence, passive identity and retained RC paths |
| Participation | Scoped credentials, frozen conditions, budgets, durable recovery, retry idempotence and concurrency |
| Results | Candidate integrity, preserved scores and revisions, transactional import/export, redaction and interrupted finalization |

This is representative regression coverage, not exhaustive input validation.
The suite does not enumerate every malformed configuration type or spelling,
every JSON/SSE error shape, custom wire-adapter registration, or every extractor
parser variation. Container and
EDA checks below remain separate. Coverage comparisons can reveal accidental
losses during cleanup; retaining every historical branch is not a requirement.
Document deliberate reductions and the remaining evidence limits.

Reuse a compatible image for container and shared evaluator changes:

```bash
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-eda-open:local uv run --locked pytest -m acceptance_container
export ICLAYOUT_BENCH_DATASET=/path/to/ICLayout-Bench-Dataset
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-eda-open:local \
  uv run --locked pytest tests/test_http.py
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-eda-open:local uv run --locked --group eda pytest \
  tests/integration/test_public_references.py -k 'cell_6t or NAND2_X1'
```

For the native Dataset table, use the locked environment and
run the catalog checks against an explicit local Dataset directory:

```bash
ICLAYOUT_BENCH_DATASET=/path/to/ICLayout-Bench-Dataset \
  uv run --locked pytest tests/unit/test_catalogs.py
```

The Bench checks use the actual Datasets reader for corpus membership,
the core membership flag, streaming, and contract/input hashes. Designs owns
table regeneration, drift checks, and publication selection.
They require no Docker, remote publication or model calls.

Participant-check and release-path changes also require `tests/test_http.py`
and `tests/integration/test_session.py` for protocol, deadline and frozen-snapshot
semantics. Use the installed wheel to qualify affected real cases under
[task qualification](#task-qualification). This is separate from offline table
validation and does not imply model performance.

Obtain the independent Dataset working copy or set the environment variable to an HF
Dataset ID. Reference/counterexample tests resolve their own cached resources. A judge,
scoring, backend or task change requires all affected case checks and shared
regressions under the [qualification rules](#task-qualification), not just
the two-case smoke selection above. The HTTP suite also derives an import-only Python tool image and compares it
with the base solver against unchanged trusted EDA. It checks participant tool
availability and evaluator identity, without model calls. Synthetic protocol
tests do not establish model ability or physical validity. Run operator admission/rerun/disclosure checks
in operator applications when shared changes affect its consumers.

Tool changes follow [image development](#image-development). Dockerfile,
pyproject and lockfile own versions. Report image reuse/derivation/rebuild and actual
checks. `build/` holds disposable generated data.

<a id="image-development"></a>

## Tools image development

The public [Dockerfile](Dockerfile) is the single open EDA image recipe. It pins
tool sources, archive digests and patches and installs the locked Python `eda`
dependencies. Update those pins only when changing a tool version or source
intentionally. Preparation, authoring, solving and evaluation use
`iclayout-eda-open:local`; individual invocations retain their isolation.

Choose the smallest image change that covers the work:

| Change | Image action |
| --- | --- |
| Framework code, cases, PDK sources, resource mounts or environment settings | Reuse a compatible image, prepare updated resources and run affected checks. |
| Container Python dependencies | Update `pyproject.toml` and `uv.lock`, then rebuild the root Dockerfile using cached native-tool layers. |
| Native EDA tools or system libraries | Update the public recipe and build scripts; validate the affected tools and container/EDA behavior with a candidate image. |
| No compatible image can be reused, the base system changes, or clean release reproduction is requested | Build the public Dockerfile and run the applicable verification matrix. |

When a full image build and toolchain smoke check are needed, use the standard
preview command and integration check:

```bash
python -m benchmarking.engine.preview build --image iclayout-eda-open:local
bash tests/integration/test_toolchain.sh
```

Use `iclayout-eda-open:local` as the standard evaluation image for cases that
use the maintained open toolchain. Do not create case-specific evaluation tags.
The image must provide the complete locked EDA group, including KPEX. Solver and
evaluator containers use the same prepared toolchain; Agent harnesses run outside
the EDA image.

Build through the same entry point for Python and native-tool changes:

```bash
docker build --platform linux/amd64 \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  -t iclayout-eda-open:local .
```

Add `--network host` only when the build needs a host loopback proxy. The build
context excludes tasks, PDKs and credentials. Run affected checks from
[Verification](#verification) before starting an experiment. Do not maintain
separate case, solver, evaluator or dependency-overlay image recipes.

The public Dockerfile installs Python dependencies after native tool compilation,
so lockfile changes can reuse those native layers. Normal builds use the cache;
disable it only for a cache or clean-build investigation. Stop active experiments
before replacing their toolchain. Historical reports retain the image IDs that
actually produced them; a rebuilt image does not retroactively validate them.

<a id="automatic-publication"></a>

### Publishing the tools image

The [image workflow](.github/workflows/image.yml) publishes the public tools
Dockerfile to Docker Hub. Create a public Docker Hub repository and configure:

| Setting | Type | Value |
| --- | --- | --- |
| `DOCKERHUB_IMAGE` | Variable | `YOUR_NAMESPACE/iclayout-bench-tools` |
| `DOCKERHUB_USERNAME` | Variable | Docker Hub login that owns the access token |
| `DOCKERHUB_TOKEN` | Secret | Access token with write access to the repository |

Without `DOCKERHUB_IMAGE`, publishing is skipped. A push to `main` publishes
`latest` and `sha-<full Git commit>` after the image checks pass. A `v*.*.*` tag
publishes its version and commit tags without replacing `latest`. A manual run
publishes a commit tag and updates `latest` only on `main`; pull requests do not
publish. BuildKit reuses unchanged layers. The workflow checks tool startup and
Python imports, not Dataset qualification; run affected EDA checks separately.

## Task qualification

The qualification command evaluates an explicitly supplied reference GDS once
with the complete physical and electrical plan. It does not call a model or use a
participant session. Apply the [validity and quality principle](docs/tasks.md#validity-and-quality)
when defining that plan: qualification proves feasibility, while the score records
solution quality. A low finite reference score is not a qualification failure.
Run it to establish feasibility for a selected reference and evaluation plan:

```bash
python -m benchmarking.engine.qualification audit \
  --dataset /path/to/ICLayout-Bench-Dataset --case CASE_ID
python -m benchmarking.engine.qualification run \
  --dataset /path/to/ICLayout-Bench-Dataset --case CASE_ID \
  --output /path/to/new-qualification
python -m benchmarking.engine.qualification verify \
  --dataset /path/to/ICLayout-Bench-Dataset --case CASE_ID \
  --output /path/to/new-qualification
```

A passing run leaves one compact, portable `qualification.json`. Waveforms, logs and other
run files are scratch by default. Add `--retain-evaluation` to `run` to keep them
in `output/evaluation`, including failed runs. Failed runs do not write a passing
`qualification.json`; retry with a fresh output directory. `verify` checks the recorded passing outcome, reference bytes
and declared evaluation inputs. It does not compare the current task contract,
evaluation plan, PDK declaration, backend identities or evaluator code with the
recorded run. A passing verification therefore confirms historical reference
evidence for matching bytes; evidence that a changed plan or environment passes
requires a new run. Participant HTTP/MCP behavior has separate integration tests
and is not asserted by this qualification report.

Before accepting a delivery, verify each delivered or changed case against its
actual recipient export. Keep qualification evidence outside the static Dataset.
Dataset maintainers own delivery summaries, core-selection acceptance and release
file enumeration; these authoring operations are not part of this package.

Dataset loading and ordinary evaluation do not consume retained qualification
reports. A `qualified` status alone does not establish acceptance. A full
qualification requires a passing complete plan on the same reference GDS; it
establishes feasibility under declared conditions, not manufacturing signoff or
participant performance. Separate repeated runs may be used when numerical
stability itself needs study.

`audit` performs contract classification without an EDA run. `run` repeats this
preflight automatically and rejects legacy implicit metric bounds. Explicit
requirements need a functional rationale; performance targets belong in quality
normalization and weights. The retained report includes this classification.
The audit cannot establish that a written rationale is physically justified;
authors must review it and the invalid/valid-degraded controls. On failure,
diagnose the contract, measurement and environment before changing the reference.

### Validation scope and changed inputs

Witness qualification requires a passing complete physical, geometric and
electrical plan on the same frozen GDS. A declared `qualified` status, a source-only
simulation or a missing witness is insufficient. This establishes feasibility
under the declared contract, not manufacturing signoff or participant performance.

Shared evaluator changes also require the relevant [verification matrix](#verification):
physical/geometry rejection, electrical failure, score boundaries and errors. New extraction/model capabilities require analytical controls and
representative circuits; a passing reference alone does not validate a backend.

Changes to executable requirements, task inputs or affected tools require new
validation of the affected scope. Prose requirements are semantic inputs too.
Documentation-only changes that preserve requirements need link, loading and
packaging checks rather than a new electrical run. Prior reports remain historical
evidence; `verify` does not detect a changed evaluator or contract. Dataset authors
and operators own receipt, evidence retention and publication decisions.


### Analytical controls

For extraction or model changes, choose a minimal control with an independent
physical expectation. Document the governing equation or external reference,
assumptions, justified tolerance and the scope it establishes next to the test.

Distinguish parameters supplied by the configuration from independent evidence.
Reading a deck coefficient can check its application; copying that coefficient
into an expected literal does not establish its accuracy. A formula alone is
insufficient when its device or connectivity assumptions remain unverified.

Reuse declared cases when device behavior is needed. A new routed MOS circuit
requires a reason specific to the behavior under test. Pure geometric controls
can establish geometry behavior without establishing circuit feasibility or
physical signoff. Score-tuned witness geometry and circuit repair procedures
remain authoring work rather than independent extraction oracles.

## Ownership and review

Update the owning guide when interfaces change. Architecture owns the shared
protocol and module responsibilities; running owns local/remote participation;
tools owns preparation/backend setup. Operators document their own formal workflows.
Preserve unrelated changes and verify and commit affected repositories separately.

<a id="ci-cd"></a>

## CI and release

Public push/PR checks cover lint, documentation, offline regressions and independent
wheel installation. Its manually dispatched EDA workflow builds the public image
and checks containers, HTTP sessions and selected public references without operator applications.
The operator's own workflow pins a compatible Public revision and verifies operator
behavior against it. Hidden assets, credentials and raw model transcripts never
enter release artifacts.

The [release workflow](.github/workflows/cd.yml) builds and checks wheel/sdist
artifacts. Pushing a `v*.*.*` Git tag publishes those same artifacts to PyPI via
Trusted Publishing, then creates the GitHub release. Versions come from Git tags;
use a canonical PEP 440 version after `v` (for example, `v1.0.0` or `v1.0.0rc1`).
Ordinary branch pushes do not publish Python packages. Manual workflow runs only
build and validate distributions. For a failed upload, re-run the failed jobs so
they reuse the checked artifacts; do not move a published tag or reuse its version.
Tools images use the separate [Docker Hub workflow](#automatic-publication).

Configure a GitHub environment named `pypi` and a PyPI Trusted Publisher with:

| Field | Value |
|---|---|
| PyPI project | `iclayout-bench` |
| GitHub owner | `lizhangmai` |
| Repository | `ICLayout-Bench` |
| Workflow filename | `cd.yml` |
| Environment | `pypi` |

For the first release, register a pending publisher at
[PyPI Publishing](https://pypi.org/manage/account/publishing/). If you already own
the project, add the publisher under its publishing settings instead. No PyPI API
token or GitHub Secret is required. A pending publisher does not reserve the
project name; the first successful upload creates the project. See the
[PyPI instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

Before publishing framework source, review its [MIT license](LICENSE). For task
materials, review the selected Dataset's licensing information and collection notices.
The Dataset maintains collection licensing; retain
original component terms and required notices with exported materials. Verify
that release descriptions identify noncommercial materials and that archives
contain the applicable declarations. Review authorization evidence separately
from technical case qualification. Offline tests and wheel installation checks
do not establish redistribution rights or resolve missing upstream notices.

Participant recovery regressions run without models or Docker:

```bash
uv run --locked pytest tests/unit/test_client.py tests/unit/test_participant_config.py tests/unit/test_participant_runner.py
```

These inject response loss after a server-side execution commit, bounded transport
failures, quota/authentication errors, process exit, native continuation, lost close
responses, service restart, concurrent recovery and changed configuration. They
verify scheduling/transport/evidence semantics, not model scores or real-provider
session continuation. Container/EDA qualification is separate.

`tests/test_http.py` also terminates real schedulers and case workers to verify
independent settlement, lease ownership and collection of the accepted candidate.
These use the formal test image and an explicit Dataset. Local service subprocesses
use isolated installed-package imports; when testing a development worktree, set
`ICLAYOUT_BENCH_TEST_PYTHON` to an existing formal environment with that worktree
installed. No replacement environment or source-path injection is needed.

## Result archive verification

Install the optional result-storage dependencies:

```bash
uv sync --locked --extra results --group analysis
uv run --locked --extra results pytest tests/unit/test_results_archive.py tests/unit/test_layout_preview.py tests/unit/test_participant_runner.py
```

The archive regressions use independent synthetic terminal records to verify SQL
transactions, idempotence, preserved revisions, missing-score semantics, artifact
integrity, path isolation, concurrent imports and outbox retry. They do not measure
models. The current table definitions initialize empty databases. Changes to existing
tables require an explicit, backed-up data update and checks against retained data. PostgreSQL uses the same interface; deployment-specific backup and
recovery remain an operator responsibility.

The operator Web service owns browser and HTTP authorization tests in operator applications.
Public distributions contain shared result processing without a browser frontend
or standalone viewer. Wheel smoke checks verify the result CLI outside the source
checkout and ensure the retired viewer module is absent.
