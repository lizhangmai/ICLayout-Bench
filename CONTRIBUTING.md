# Contributing and Verification

Public owns participant code, shared definitions, preparation, isolated sessions,
EDA backends, independent evaluation and the local HTTP adapter. Operators own
operator admission, controlled reruns and reviewed releases. Public installation
and CI must not import operator applications. Exclude `third_party/` from framework
searches, lint and tests.

<a id="verification"></a>

## Verification

From Public, offline checks need neither Docker nor operator applications:

```bash
uv sync --locked --extra results --group analysis
uv run --locked ruff check .
uv run --locked python scripts/check_docs.py
uv run --locked python scripts/check_repository.py
uv run --locked --group analysis pytest -m unit
uv build --out-dir build/dist
git diff --check
```

Package metadata is derived from Git tags by `setuptools-scm`; untagged commits
receive development versions. Build from a checkout with full tag history or a
built source distribution. Wheel metadata and the embedded source commit preserve
the identity without Git at runtime. After changing commits or tags, synchronize
the editable installation before running source commands. Do not maintain a
separate version literal in project metadata.

Check built distributions from outside the checkout or with Python `-I`, and
assert that imports come from the installation environment. A source-tree import
cannot validate a wheel. The wheel includes `benchmarking` and its subpackages with their
runtime data; it excludes operator modules. After moving packages, build from a
clean checkout or remove stale `build/lib` first; wheel checks reject the retired
top-level namespaces. Follow [test conventions](tests/AGENTS.md)
before adding regressions.

Keep one owner for each tested behavior. `test_catalogs.py` checks catalog
ownership, qualification metadata, SPICE interfaces and isolated materialization
in one traversal of every declared case. `test_evaluate.py` owns execution and
verdicts; `test_scoring.py` owns score arithmetic and baseline semantics.
`test_hbt_extraction.py` owns HBT conversion, correspondence and extraction
diagnostics; `test_model_config.py` owns runtime and harness configuration.
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
| Evaluation and scoring | Candidate-derived evidence, validity and failure precedence, unknown versus zero, source pairing, normalization and uncapped scores |
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
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local uv run --locked pytest -m acceptance_container
export ICLAYOUT_BENCH_DATASET=/path/to/ICLayout-Bench-Dataset
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local \
  uv run --locked pytest tests/test_http.py
ICLAYOUT_BENCH_TEST_IMAGE=iclayout-bench-tools:local uv run --locked --group eda pytest \
  tests/integration/test_public_references.py -k 'cell_6t or NAND2_X1'
```

For the native Dataset table, use the locked environment and
run the catalog checks against an explicit local Dataset directory:

```bash
ICLAYOUT_BENCH_DATASET=/path/to/ICLayout-Bench-Dataset \
  uv run --locked pytest tests/unit/test_catalogs.py
python -m benchmarking.dataset_index --dataset /path/to/ICLayout-Bench-Dataset --check
```

These checks use the actual Datasets reader for complete corpus membership,
the generated core membership flag, streaming, and contract/input hashes. They reject
stale indexes and verify that reselection preserves corpus files and every row field except `in_core`.
They require no Docker, remote publication or model calls.

Participant-check and release-path changes also require `tests/test_http.py`,
which compares a declared witness across direct, MCP check and final HTTP evaluation,
and `tests/integration/test_session.py` for deadline and frozen-snapshot semantics.
Use the installed wheel to qualify affected real cases under
[participant-path qualification](#task-qualification). This is separate from offline table validation and does not imply model performance.

Obtain the independent Dataset working copy or set the environment variable to an HF
Dataset ID. Reference/counterexample tests resolve their own cached resources. A judge,
scoring, backend or task change requires all affected case checks and shared
regressions under the [qualification rules](#task-qualification), not just
the two-case smoke selection above. The HTTP suite also derives an import-only Python tool image and compares it
with the base solver against unchanged trusted EDA. It checks participant tool
availability and evaluator identity, without model calls. Synthetic protocol
tests do not establish model ability or physical validity. Run operator admission/rerun/disclosure checks
in operator applications when shared changes affect its consumers.

Tool changes follow [image development](docs/tools.md#image-development). Dockerfile,
pyproject and lockfile own versions. Report image reuse/derivation/rebuild and actual
checks. `build/` holds disposable generated data.

## Task qualification

The qualification API verifies an explicitly supplied witness with the installed
package through direct evaluation, participant HTTP/MCP checking and final HTTP
evaluation. This uses the same immutable GDS and full task plan in all three paths;
no model is called. The witness is supplied explicitly by the maintenance command,
not exposed to a normal solver.

```bash
python -m benchmarking.engine.qualification run \
  --dataset /path/to/ICLayout-Bench-Dataset --case CASE_ID \
  --output build/qualification/CASE_ID
python -m benchmarking.engine.qualification verify \
  --dataset /path/to/ICLayout-Bench-Dataset --case CASE_ID \
  --output build/qualification/CASE_ID
```

A successful run produces `qualification.json`, `direct.json`, `check.json` and
`final.json`. Verification expects these files together. Service stores and
credentials are disposable scratch and are not evidence inputs. Report retention
belongs to the caller. To export a verified summary entry:

```bash
python -m benchmarking.engine.qualification verify \
  --dataset /path/to/dataset --case CASE_ID --output /path/to/retained-evidence \
  --summary /path/to/author/summary.json \
  --design-commit AUTHORING_COMMIT
```

The external summary map keys entries by case ID. Each entry contains the authoring commit, task and witness digests, qualification-record
digest, `scope = "direct/check/final"` and `passed = true`. The referenced record
binds the full evaluator, PDK, reports and repeatability observations. The summary
records the specified evaluation, not approval of future engine implementations.
Task materials must permit independent reevaluation without a development checkout.
Dataset loading and ordinary evaluation do not consume full historical reports.
A `historical-reference` entry identifies an earlier saved reference record using
`evidence_sha256` and keeps its original report task identity in
`observed_task_sha256`. It may accompany a current task association, but does not
qualify a new core member: the core gate requires current three-path evidence.

The publication gate checks the complete `in_core` selection from the native `test` table using an
explicit external report-directory map and acceptance-summary map. Evidence paths
must remain beneath the report map's directory; no sibling checkout is inferred:

```bash
python -m benchmarking.engine.qualification verify-core \
  --dataset /path/to/dataset --evidence /path/to/author/evidence.json \
  --summaries /path/to/author/validation.json \
  --image iclayout-bench-tools:local
```

Verification resolves the actual local tools/resources but runs no simulation.
It rejects changed contracts, witness bytes, PDK declarations, backend identities,
evaluation code, participant-check code, modified reports, incomplete plans or
diverging acceptance decisions. It preserves all three sets of measurements and
scores and discloses whether they are identical. Qualification also enforces a
numerical repeatability budget across these three independent runs:

- The maximum score minus the minimum score must not exceed **0.1 point**.
- For every declared metric, each individual job observation must have a
  maximum-minus-minimum spread no greater than **0.1% of its dimensional scale**.
  The scale is the maximum absolute value among the repeated observations,
  the metric's declared scale and acceptance bounds, and its paired frozen
  pre-layout baseline, where present. A zero scale permits no spread.
- Acceptance decisions must remain identical. No tolerance is added to the
  task's physical/electrical bounds; a failed or error path cannot qualify.

The gate records the observed spread and limit for every metric/condition,
including conditions hidden by aggregate reducers. Only floating-point roundoff
at the comparison boundary is allowed. These are engineering reproducibility
limits, not confidence intervals or evidence of bit-identical extraction.
Raw diagnostic measurements remain available in all reports. Larger
repeatability studies may supplement the required three-path evidence.
Missing evidence is a failure, not an implicit acceptance
of `status = "qualified"`. Dataset table/hash checks do not replace this gate.
Run the gate with the evaluator wheel and tool image selected for publication;
a different image or affected implementation requires fresh qualification.

### Validation scope and changed inputs

Witness qualification requires a passing complete physical, geometric and
electrical plan on the same frozen GDS. A declared `qualified` status, a source-only
simulation or a missing witness is insufficient. This establishes feasibility
under the declared contract, not manufacturing signoff or participant performance.

Shared evaluator changes also require the relevant [verification matrix](#verification):
physical/geometry rejection, electrical failure, score boundaries, errors and
repeatability. New extraction/model capabilities require analytical controls and
representative circuits; a passing reference alone does not validate a backend.

Changes to executable requirements, task inputs or affected tools require new
validation of the affected scope. Prose requirements are semantic inputs too.
Documentation-only changes that preserve requirements need link, loading and
packaging checks rather than a new electrical run. Prior reports retain their
original identities and do not attest a changed evaluator or contract. Dataset
authors and operators own receipt, evidence retention and publication decisions.


## Ownership and review

Update the owning guide when interfaces change. Architecture owns the shared
protocol and module responsibilities; running owns local/remote participation;
tools owns preparation/backend setup. Operators document their own formal workflows.
Markdown is English except README_CN.md. Preserve unrelated changes and verify and
commit affected repositories separately.

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
Tools images use the separate [Docker Hub workflow](docs/tools.md#automatic-publication).

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
