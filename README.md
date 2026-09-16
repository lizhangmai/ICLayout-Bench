# ICLayout-Bench

Open-source tools for developing and evaluating integrated-circuit layout agents:
public tasks, an official harness, a generic HTTP client, a shared evaluation engine
and a local evaluation service. [简体中文](README_CN.md)

Run public tasks locally to debug your Agent before participating in an operator's
unified evaluation service. Both paths use the same HTTP contract, isolated EDA
execution and independent scoring implementation. Local results are development
evidence; formal results require operator-controlled conditions and verification.
Private adds hidden tasks, admission, controlled reruns and reviewed releases.

## Quick start

Use Python 3.12+ and uv. From this Public checkout:

```bash
uv sync --locked --group analysis
```

For local self-testing, install Docker on Linux x86-64 and prepare a public task.
The first command builds the public tool image; when a compatible image already
exists, use `--skip-build --image <existing-image>` instead.

```bash
uv run --locked python -m layout_eval.preview quickstart \
  --case cell_6t --output build/local-cell6t
export ICLAYOUT_BENCH_TOKEN="$(openssl rand -hex 32)"
uv run --locked python -m layout_service \
  --prepared build/local-cell6t/prepared --data build/local-service \
  --image iclayout-bench-tools:local --token-env ICLAYOUT_BENCH_TOKEN
```

Quickstart prepares resources and checks the published reference without calling
a model. Its reference is never mounted into the solver workspace. The service
runs in the foreground. In another terminal, use the same creation token:

```bash
export ICLAYOUT_BENCH_ENDPOINT=http://127.0.0.1:8765
# Supply the creation token as ICLAYOUT_BENCH_TOKEN in this terminal.
uv run --locked python -m benchmarking.official \
  --task freepdk45.OpenRAM.cell_6t --model YOUR_CONFIGURED_MODEL \
  --key local-1 --output build/runs/local-1
uv run --locked python -m benchmarking.analyze \
  build/runs/local-1/analysis/result.json --output build/runs/local-analysis --plots
```

The included provider uses an existing authenticated Codex CLI. You can instead
use a custom harness through `benchmarking.client`. For remote participation,
use the operator's endpoint and credentials with these same participant commands;
no local Docker, EDA installation or Private source is needed. No hosted public
endpoint is supplied. See [running](docs/running.md) for local debugging and remote
participation, including evaluating an existing GDS directly.

## Public materials

[benchmark.toml](benchmark.toml) selects qualified cases. `tasks/` holds public
netlists, requirements and reference material across IHP SG13G2, FreePDK45 and
GF180. [Dockerfile](Dockerfile) and pinned submodules define the compatible tool
recipe. Public preparation resolves reviewed inputs and resources into fresh
`build/` output. References are development materials, excluded from standard
solver inputs. DRC/LVS validity is necessary but tasks also impose geometry and
post-layout requirements.

The wheel includes `benchmarking`, `layout_eval` and `layout_service`. Large task
catalogs and upstream PDKs remain source/resource inputs: use a Public checkout
for preparation, or `layout_eval.preview --public-root /path/to/ICLayout-Bench` with
an installed wheel. Serving an already prepared case does not require a checkout.

## Migration

The project is now **ICLayout-Bench**, distributed as `iclayout-bench`. The three
checkout directories use the `ICLayout-Bench` prefix. Current commands read
`ICLAYOUT_BENCH_*` environment variables and use `iclayout-bench-tools` image tags.
Python module names (`benchmarking`, `layout_eval`, `layout_service`) and the HTTP
protocol remain unchanged. Reinstall the renamed package and prepare fresh resources
after moving a checkout; historical reports retain their original identities.


Version 0.3 makes the shared evaluator and local service public. Private's formal
operations now live in `layout_operator`; it imports the same Public engine.
Use `python -m layout_eval.cli` for local evaluate/run/recover commands and
`python -m layout_service` for local HTTP sessions. Batch admission and verified
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
| Formal reruns and disclosure | [Admission](docs/admission.md) |
| Verification and contribution | [Contributing](CONTRIBUTING.md) |
| Earlier migration history | [Development record](docs/refactoring-plan.md) |

## Validation scope

Public owns client/harness tests, engine regressions, container isolation checks
and public reference/counterexample checks. Offline tests need neither Docker nor
Private. Container/EDA tests require the declared tools. Private verifies admission,
controlled reruns and disclosure using that same engine. Synthetic protocol runs
are not model scores; reference evaluation is not an Agent measurement.
