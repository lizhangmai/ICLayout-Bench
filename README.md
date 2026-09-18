# ICLayout-Bench

An MIT-licensed framework for developing and evaluating integrated-circuit layout
agents, with separately licensed public tasks, independent observation, a generic
HTTP client, a shared evaluation engine and a local evaluation service. [简体中文](README_CN.md)

Run public tasks locally to debug your Agent before participating in an operator's
unified evaluation service. Both paths use the same HTTP contract, isolated EDA
execution and independent scoring implementation. Local results are development
evidence; formal results require operator-controlled conditions and verification.
Private adds hidden tasks, admission, controlled reruns and reviewed releases.

Current tasks use source simulation as the 100-point electrical reference and a
frozen compact-area reference (`layout-v2`); scores may exceed 100. See
[scoring and task design](docs/tasks.md#task-scoring). Historical results retain
their original scoring version.

## Licensing

The framework is licensed under [MIT](LICENSE). Task materials, reference layouts,
PDKs and EDA tools retain their own terms; the repository is not uniformly MIT.
In particular, both analog-db collections include **PolyForm Noncommercial 1.0.0**
circuit materials and reference layouts, with additional upstream component terms.
Public availability and case qualification do not grant commercial-use rights.
See [Licensing and distribution](LICENSING.md) for collection scopes and notices
before using or redistributing task materials.

## Quick start

Use Python 3.12+ and uv. From this Public checkout:

```bash
uv sync --locked --group analysis
```

For local self-testing, install Docker on Linux x86-64 and prepare a public task.
The first command builds the public tool image; when a compatible image already
exists, use `--skip-build --image <existing-image>` instead.

```bash
uv run --locked python -m benchmarking.engine.preview quickstart \
  --case cell_6t --output build/local-cell6t
export ICLAYOUT_BENCH_TOKEN="$(openssl rand -hex 32)"
uv run --locked python -m benchmarking.service \
  --prepared build/local-cell6t/prepared --data build/local-service \
  --image iclayout-bench-tools:local --token-env ICLAYOUT_BENCH_TOKEN
```

Quickstart prepares resources and checks the published reference without calling
a model. Its reference is never mounted into the solver workspace. The service
runs in the foreground. Connect your Codex, Claude Code, DSH or other Agent harness
using the [experiment runner](docs/running.md#experiment-runner),
`python -m benchmarking.run`, or the [generic HTTP client](docs/running.md#generic-client). The participant
controls its own conversation and tool loop; ICLayout-Bench observes service
operations, enforces execution constraints and scores immutable submissions.

For remote participation, use the operator's endpoint and credentials with the
same client. No local Docker, EDA installation or Private source is needed. No
hosted public endpoint is supplied. See [running](docs/running.md) for session
creation, observation exports, analysis and evaluating an existing GDS directly.

## Public materials

[benchmark.toml](benchmark.toml) selects qualified cases. `tasks/` holds public
netlists, requirements and reference material across IHP SG13G2, FreePDK45 and
GF180. [Dockerfile](Dockerfile) defines the compatible tool recipe; process
manifests pin PDK releases or source submodules. Public preparation resolves reviewed inputs and resources into fresh
`build/` output. References are development materials, excluded from standard
solver inputs. DRC/LVS validity is necessary but tasks also impose geometry and
post-layout requirements.

GF180MCU and IHP SG13G2 use fixed prebuilt releases downloaded through ciel.
`ICLAYOUT_BENCH_CACHE_DIR` overrides the default `~/.cache/iclayout-bench` cache
(or `$XDG_CACHE_HOME/iclayout-bench`). FreePDK45 uses the pinned community
installation. Preparation verifies cached resources and filters out example answers.
See [PDK preparation](docs/tools.md#external-sources) for sources and extraction scope.

The wheel provides one `benchmarking` namespace, including its `engine`,
`service` and `participants` subpackages. Large task catalogs and upstream PDKs remain source/resource inputs: use a Public checkout
for preparation, or `benchmarking.engine.preview --public-root /path/to/ICLayout-Bench` with
an installed wheel. Serving an already prepared case does not require a checkout.

## Migration

The project is now **ICLayout-Bench**, distributed as `iclayout-bench`. The three
checkout directories use the `ICLayout-Bench` prefix. Current commands read
`ICLAYOUT_BENCH_*` environment variables and use `iclayout-bench-tools` image tags.
All Public Python implementation now lives under `benchmarking`: use
`benchmarking.engine` and `benchmarking.service` in place of the former top-level
`layout_eval` and `layout_service` packages. The HTTP protocol remains unchanged. Reinstall the package and prepare
fresh resources after moving a checkout; historical reports retain their original identities.


Version 0.3 makes the shared evaluator and local service public. Private's formal
operations now live in `iclayout_bench_private`; it imports the same Public engine.
Use `python -m benchmarking.engine.cli` for local evaluate/run/recover commands and
`python -m benchmarking.service` for local HTTP sessions. Batch admission and verified
rerun/release commands remain operator-owned. Old generated runs are evidence of
their recorded implementation, not inputs required by the current workflow.

<a id="resources"></a>

## Guides

| Topic | Guide |
|---|---|
| Protocol, ownership and trust | [Architecture](docs/architecture.md) |
| Local self-testing, remote participation and analysis | [Running](docs/running.md) |
| Task contracts, scoring and qualification | [Tasks](docs/tasks.md) |
| Tool images and resource preparation | [Tools](docs/tools.md) |
| Result storage, comparisons and presentation data | [Result storage](docs/running.md#result-archive) |
| Formal reruns and disclosure | [Admission](docs/architecture.md#verified-reruns-and-disclosure) |
| Verification and contribution | [Contributing](CONTRIBUTING.md) |

## Validation scope

Public owns client/observation tests, engine regressions, container isolation checks
and public reference/counterexample checks. Offline tests need neither Docker nor
Private. Container/EDA tests require the declared tools. Private verifies admission,
controlled reruns and disclosure using that same engine. Synthetic protocol runs
are not model scores; reference evaluation is not an Agent measurement.
