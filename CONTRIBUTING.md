# Contributing and Verification

ICLayout-Bench provides participant runners, shared contracts, resource preparation,
isolated sessions, EDA backends and independent evaluation. Changes should work
without a maintainer's other repositories, datasets or machine configuration.
Exclude `third_party/` from framework searches, lint and tests.

## Development setup

Use Python 3.12+ and uv. From a fresh clone:

```bash
git clone https://github.com/lizhangmai/ICLayout-Bench.git
cd ICLayout-Bench
uv sync --locked --extra results
```

`uv sync` creates the project environment when needed and installs the package in
editable mode with the locked development dependencies. The offline checks below
need no Docker, Dataset, agent CLI or model credentials. EDA checks require the
additional tools and explicit inputs described in [verification](#verification).
Keep credentials and generated experiment results out of tracked source; choose
configuration and output paths to suit your workflow.

## Implementation map

Use the package that owns the operation. The same boundaries apply to Python
imports, command entry points and bundled helper scripts.
Keep case names, circuit fixes and process-specific preparation in declared task
resources rather than shared orchestration modules.

| Package | Responsibility and internal organization |
| --- | --- |
| `tasks/` | `contract.py` validates immutable task declarations; `dataset.py` selects cases and their declared files; `documents.py` renders authored problem documents. No EDA execution or participant scheduling. |
| `evaluation/` | `contracts.py` defines plans and backend results; `plans.py` decodes and validates the complete job/metric graph; `runner.py` executes that graph; `measurements/` interprets observations; `scoring.py` calculates task scores; `qualification.py` audits and verifies reference evidence. `feedback.py` projects participant diagnostics. `cli.py` composes these operations with selected EDA backends. |
| `eda/` | `toolchain.py` validates declarations and lazily constructs adapters; `runtime.py` binds declared case inputs and resources. `backends/` owns tool invocation and native report acceptance; `oa/` provides native authoring interfaces; `resources/` prepares reviewed installations and support bundles; `netlists/` parses native circuit representations. `_scripts/` contains only EDA job helpers. Process and case policies remain in declared task resources. |
| `execution/` | `tools/` executes bounded frozen jobs through Docker or native tools; `workspace/` stages and operates isolated solver workspaces; `process.py`, `leases.py` and `retry.py` provide shared process control. `inference/` owns the controlled model gateway. `harness.py` defines portable tool schemes. `_scripts/` contains staged workspace/protocol helpers. Execution does not schedule experiments or judge a design. |
| `evidence/` | `bundles.py` validates immutable artifact bundles; `journal.py` writes and reads ordered committed events; `archive.py` reconstructs recorded run evidence; `identity.py` records the installed implementation. Only an unfinished final journal line may be ignored; malformed committed lines and sequence gaps are errors. |
| `participants/` | `batch/` resolves experiment configuration, schedules repetitions and supervises independent workers. `attempt/` owns one solve's durable state, launch, continuation, recovery, settlement and terminal evidence collection. `harnesses/` registers native adapters and keeps each provider's configuration, event parsing, traces and usage interpretation in that provider's module. `mcp.py` exposes the participant HTTP tools. |
| `service/` | `application.py` translates HTTP routes; `controller.py` owns authenticated mutations and replay; `views.py` projects responses; `state.py` stores service records. `session.py` composes solver execution with independent evaluation; `supervisor.py` owns live session handles. A controller can receive a dedicated supervisor, runner and workspace factory. |
| `results/` | `package.py` exports explicit immutable evaluation and participant evidence; `verification.py` checks terminal records; `analysis.py` and the statistics modules return structured data. `preview.py` and `native_preview.py` produce EDA preview assets. `importing.py` validates artifacts before `store.py` transactionally imports metadata; `objects.py` stores content-addressed files. `outbox.py` and `transfer.py` own handoff. Charts and website publishing belong to consuming applications. |

`results.retention` owns purpose-based terminal retention, compressed evidence
resolution and maintenance migration. Extend `test_result_retention.py` and the
evaluation/export regressions when changing retention: functional rejection is
distinct from a successful simulator exit; final evidence, observed feedback,
unknown usage and portable byte identities must survive collection. Test corruption,
interrupted cleanup, active-owner exclusion and independent archive copying without
running models or EDA. Ordinary successful-check omissions must remain distinguishable
from accidental missing evidence.

The evaluation core depends on backend contracts rather than concrete EDA tools;
CLI and service composition choose implementations. Adapters depend on execution
primitives and evaluation contracts. Batch orchestration calls attempt operations.
Result packaging accepts explicit evidence records rather than interpreting
participant runtime directories. SQL remains optional for previews and handoff.
Presentation code uses `ResultStore` operations rather than its SQL engine.

Related tool modes share an implementation: Spectre base/X/APS and native
construction live in `eda/backends/spectre.py`; each harness owns its native
records and events. Keep small files only where they establish a distinct
responsibility, rather than splitting one operation across forwarding modules.
Include new evaluation/session implementation files in their recorded identities.

Commands use `benchmarking.evaluation`, `benchmarking.execution` and
`benchmarking.eda`. Existing documented client imports (`benchmarking.dataset`,
`benchmarking.task_documents`, `benchmarking.transfer`, result progress/finalization
and the resource cache resolver) and legacy engine CLI commands have explicit
compatibility facades. Framework code and updated consumers import the owning
modules directly; do not add compatibility wrappers for internal implementations.

<a id="verification"></a>

## Verification

Choose verification by change scope and delivery stage:

| Stage or change | Required verification |
| --- | --- |
| Before a local commit | Review the diff, run `git diff --check`, and run checks relevant to the changed behavior. For documentation edits, run `uv run --locked pytest tests/unit/test_documentation_links.py` and inspect changed commands; example configuration edits need parsing/configuration checks. |
| Before pushing, or in PR CI | Run the full offline checks below, including the distribution build and isolated wheel and sdist installation smoke test. PR CI may satisfy this stage; successful local checks for the same revision need not be repeated before pushing. |
| Packaging, dependencies, package structure, entry points, or bundled resources change | Run the affected build and isolated installation checks before committing, so packaging failures are caught during development. |

Routine local commits do not require a distribution build or isolated installation test.
The affected container, evaluator, and task qualification checks below still apply
when their behavior changes. Report which checks ran and which are deferred to CI.

After [development setup](#development-setup), run the offline checks:

```bash
uv sync --locked --extra results
uv run --locked ruff check .
uv run --locked pytest -m 'unit or acceptance_fast'
uv build --out-dir build/dist
bash scripts/check_distributions.sh build/dist "$(git rev-parse HEAD)"
git diff --check
```

The [distribution check](scripts/check_distributions.sh) installs each built wheel
and sdist into a fresh virtual environment and verifies its entry points and
embedded release identity, as [the checks workflow](.github/workflows/checks.yml) does.

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
and the participant runner, service and evaluator CLI must start. Run the relevant
tests during development; the CI package job checks a clean wheel installation
independently of the source checkout.
The wheel includes `benchmarking` and its subpackages with their
runtime data; it excludes operator modules. Use the default `uv build` command
above: it builds the wheel from a fresh source distribution, keeping retired
modules in a checkout's `build/lib` out of the wheel. Direct wheel builds from a
checkout require a clean build tree.
Follow [test conventions](tests/AGENTS.md)
before adding regressions.

Keep one owner for each tested behavior. `test_task_sources.py` checks synthetic
Dataset indexes, core ordering and isolated source materialization without an
external Dataset. `tests/integration/test_catalogs.py` separately checks declared
files, simulator interfaces, isolated inputs and native table loading against an
explicit delivery snapshot. These checks do not establish reference qualification.
Problem wording, numeric disclosures and engineering estimates belong to Dataset
author review; framework tests do not parse prose with publication-specific regexes.
`test_evaluate.py` owns execution and
verdicts; `test_scoring.py` owns score arithmetic and baseline semantics.
`test_hbt_extraction.py` owns HBT conversion, correspondence and extraction
diagnostics; `test_run_config.py` owns runtime and harness configuration.
Extend these existing checks instead of repeating their setup in new files.
Use parameter combinations when the dimensions interact; otherwise retain a
representative success and failure for the public behavior. Related assertions
should reuse one workflow, such as materializing a frozen task and refusing to
overwrite it. Do not maintain unused Agent implementations just to test those
implementations. Test counts include parameter expansion and are not a target.
Shared plans, backend doubles and result builders belong in `tests/helpers/`;
fixtures belong in the nearest `conftest.py`. Do not import test modules from
other tests or register test modules as fixture plugins.

`test_participant_runner.py` owns shared recovery and settlement workflows, with
decision tables for bounded waits and representative subprocess continuations;
`test_harness_adapters.py` owns native event classification and persisted-history
binding. Exercise shared stopping rules with one representative harness and keep
each adapter's native success, binding and format-specific failure checks. Expand
cross-products only when the dimensions interact in the behavior being checked.

The offline suite prioritizes the following contracts:

| Area | Retained scope |
| --- | --- |
| Tasks and Datasets | Synthetic loading, core selection, declared inputs and solver isolation; real delivery snapshots are checked separately |
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

Pull the published tools image, or select a compatible image you built:

```bash
docker pull docker.io/lizhangmai/iclayout-bench-tools:latest
ICLAYOUT_BENCH_TEST_IMAGE=docker.io/lizhangmai/iclayout-bench-tools:latest \
  uv run --locked pytest -m acceptance_container
export ICLAYOUT_BENCH_DATASET=/path/to/dataset
ICLAYOUT_BENCH_TEST_IMAGE=docker.io/lizhangmai/iclayout-bench-tools:latest \
  uv run --locked pytest tests/test_http.py
```

The regular HTTP suite uses a small checkpoint round trip. Near-capacity
checkpoint acceptance writes and verifies roughly the full workspace allocation
(normally 2 GiB); run it explicitly when changing checkpoint capacity or transport:

```bash
ICLAYOUT_BENCH_DATASET=/path/to/dataset \
ICLAYOUT_BENCH_TEST_IMAGE=docker.io/lizhangmai/iclayout-bench-tools:latest \
  uv run --locked pytest -m acceptance_capacity
```

The manual evaluator workflow exposes the same check through its
`checkpoint_capacity` input. Capacity acceptance is separate from ordinary HTTP
protocol regression and does not establish EDA correctness.

`ICLAYOUT_BENCH_DATASET` must identify a Dataset directory for the catalog and
HTTP tests. Download a published snapshot if needed:

```bash
uv run --locked hf download lizhangmai/ICLayout-Bench --type dataset \
  --local-dir /path/to/dataset
```

For the native Dataset table, use the locked environment and
run the catalog checks against an explicit local Dataset directory:

```bash
ICLAYOUT_BENCH_DATASET=/path/to/dataset \
  uv run --locked pytest tests/integration/test_catalogs.py
```

The checks use the actual Datasets reader for corpus membership,
the core membership flag, streaming, and contract/input hashes. Dataset authors
maintain the index and select their published cases.
They require no Docker, remote publication or model calls.

Participant-check and release-path changes also require `tests/test_http.py`
and `tests/integration/test_session.py` for protocol, deadline and frozen-snapshot
semantics. Use the installed wheel to qualify affected real cases under
[task qualification](#task-qualification). This is separate from offline table
validation and does not imply model performance.

Reference/counterexample tests require an author verification Dataset containing
the declared witnesses, which participant Datasets omit:

```bash
ICLAYOUT_BENCH_DATASET=/path/to/author-verification-dataset \
ICLAYOUT_BENCH_TEST_IMAGE=docker.io/lizhangmai/iclayout-bench-tools:latest \
  uv run --locked --group eda pytest \
  tests/integration/test_public_references.py -k 'cell_6t or NAND2_X1'
```

These tests resolve their declared resources from the supplied Dataset. A judge,
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
dependencies, including its `agent-tools` group of scientific and scripting
packages. Update those pins only when changing a tool version or source
intentionally. Releases publish
`docker.io/lizhangmai/iclayout-bench-tools:v<version>`, which released packages
select by default; `latest` follows the checked head of `main` and is the default
for development installs. Development builds can use any explicit tag. Select the image with `--image` or `ICLAYOUT_BENCH_IMAGE`, and use
`ICLAYOUT_BENCH_TEST_IMAGE` for container tests.

Choose the smallest image change that covers the work:

| Change | Image action |
| --- | --- |
| Framework code, cases, PDK sources, resource mounts or environment settings | Reuse a compatible image, prepare updated resources and run affected checks. |
| Container Python dependencies | Update `pyproject.toml` and `uv.lock`, then rebuild the root Dockerfile using cached native-tool layers. |
| Native EDA tools or system libraries | Update the public recipe and build scripts; validate the affected tools and container/EDA behavior with a candidate image. |
| No compatible image can be reused, the base system changes, or clean release reproduction is requested | Build the public Dockerfile and run the applicable verification matrix. |

When a full image build and toolchain smoke check are needed, build from the
source checkout and select the resulting image explicitly:

```bash
uv run --locked python -m benchmarking.eda build --source . \
  --image iclayout-bench-tools:dev
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:dev \
  bash tests/integration/test_toolchain.sh
```

Validate the pinned [ngspice `xfer` DC Jacobian patch](scripts/patches/ngspice-xfer-dc-jacobian.patch)
with the [toolchain smoke check](tests/integration/test_toolchain.sh). The
derivative must equal the real transfer value at the first table frequency,
matching the model's DC output equation. Compare `xfer` and an equivalent VCVS
against the analytical DC solution for the same negative-feedback circuit.

The image must provide the complete locked EDA group, including KPEX. Solver and
evaluator containers use the same prepared toolchain; Agent harnesses run outside
the EDA image.

Build through the same entry point for Python and native-tool changes:

```bash
docker build --platform linux/amd64 \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  -t iclayout-bench-tools:dev .
```

Add `--network host` only when the build needs a host loopback proxy. The build
context excludes tasks, PDKs and credentials. Run affected checks from
[Verification](#verification). Participant tools can derive a solver image from
this base; declare that selection through the participant tool scheme.

The public Dockerfile installs Python dependencies after native tool compilation,
so lockfile changes can reuse those native layers. Normal builds use the cache;
disable it only for a cache or clean-build investigation. Stop active experiments
before replacing their toolchain. Historical reports retain the image IDs that
actually produced them; a rebuilt image does not retroactively validate them.

<a id="automatic-publication"></a>

### Publishing the tools image

The [image workflow](.github/workflows/image.yml) publishes the public tools
Dockerfile to Docker Hub after [Framework checks](.github/workflows/checks.yml)
pass for a push to `main`; the [release workflow](.github/workflows/cd.yml)
publishes release tags after its package checks. Both use the
[shared publisher](.github/workflows/tools-image.yml), which pushes an untagged
candidate by digest, checks tool startup and Python imports in that exact digest,
and only then attaches public tags. Release maintainers configure the destination
below; forks can choose their own namespace:

| Setting | Type | Value |
| --- | --- | --- |
| `DOCKERHUB_IMAGE` | Variable | `lizhangmai/iclayout-bench-tools`, or your publication namespace |
| `DOCKERHUB_USERNAME` | Variable | Docker Hub login that owns the access token |
| `DOCKERHUB_TOKEN` | Secret | Access token with write access to the repository |

Without `DOCKERHUB_IMAGE`, publishing is skipped. A checked `main` commit receives
`sha-<full Git commit>` and moves `latest` only while it is still the head of
`main`. A `v*.*.*` tag receives its version and commit tags without replacing
`latest`. Pull requests and commits whose checks fail do not publish; re-run a
failed publication from its workflow run. BuildKit reuses unchanged layers. The
image checks cover tool startup and Python imports, not Dataset qualification;
run affected EDA checks separately.

## Task qualification

The [qualification guide](docs/tasks.md#qualification) defines the audit, run and
verify commands, retained evidence and changed-input rules.
Use the checkout environment for development checks and the selected installed
release for recipient-side verification.

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

Update the owning guide when interfaces change. Architecture owns responsibilities,
the HTTP contract and extension boundaries.
Running owns participant configuration, execution, recovery and result analysis;
tasks owns task/scoring/qualification contracts; tools owns EDA setup and backend
references. Operators document their own formal workflows.
Preserve unrelated changes and verify and commit affected repositories separately.

<a id="ci-cd"></a>

## CI and release

Checks for pushes to `main` and pull requests cover lint, Markdown links and
anchors, offline regressions (`unit` and `acceptance_fast` markers) and independent
wheel and sdist installation. The manually dispatched EDA workflow builds the
public image and checks containers, HTTP sessions and selected public references
without operator applications.
Applications integrating Bench pin a compatible package release and test their
own behavior against it. Hidden assets, credentials and raw model transcripts never
enter release artifacts.

The [release workflow](.github/workflows/cd.yml) builds and checks wheel/sdist
artifacts. Pushing a `v*.*.*` Git tag publishes the release tools image, then those
same artifacts to PyPI via Trusted Publishing, then creates the GitHub release.
PyPI upload starts only after the release image is published, or skipped when
`DOCKERHUB_IMAGE` is unset. Versions come from Git tags; use a canonical PEP 440
version after `v` (for example, `v1.0.0` or `v1.0.0rc1`), and tag a commit that
is already on `main` after its checks pass.
Ordinary branch pushes do not publish Python packages. Manual workflow runs only
build and validate distributions. For a failed upload, re-run the failed jobs so
they reuse the checked artifacts; do not move a published tag or reuse its version.
Tools images follow [Docker Hub publication](#automatic-publication).

Workflow actions are pinned to full commit SHAs with their release tag in a
comment; [Dependabot](.github/dependabot.yml) proposes weekly updates. Review the
upstream release before merging a pin update. GitHub Pages uses the GitHub Actions
source: the manually dispatched [pages workflow](.github/workflows/pages.yml)
verifies the reviewed `gh-pages` manifest before deployment, and a push to
`gh-pages` alone does not deploy.

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
These use a compatible test image and an explicit Dataset. Service subprocesses
use isolated installed-package imports; when testing a development worktree, set
`ICLAYOUT_BENCH_TEST_PYTHON` to the Python interpreter where that worktree is
installed.

## Result archive verification

Install the optional result-storage dependencies:

```bash
uv sync --locked --extra results
uv run --locked --extra results pytest tests/unit/test_results_archive.py tests/unit/test_layout_preview.py tests/unit/test_participant_runner.py
```

The archive regressions use independent synthetic terminal records to verify SQL
transactions, idempotence, preserved revisions, missing-score semantics, artifact
integrity, path isolation, concurrent imports and outbox retry. They do not measure
models. The current table definitions initialize empty databases. Changes to existing
tables require an explicit, backed-up data update and checks against retained data. PostgreSQL uses the same interface; deployment-specific backup and
recovery remain an operator responsibility.

Consuming applications test their own browser interfaces and authorization.
The Bench package provides structured result processing and no browser frontend.
Wheel smoke checks verify that the result CLI works outside the source checkout.
