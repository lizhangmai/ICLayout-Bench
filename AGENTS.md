# ICLayout-Bench Repository Conventions

This repository owns the evaluation observation layer, generic client, public protocol, scoring specifications, development tasks, result archives/visualization and portable result delivery. It also owns the shared evaluation engine and local HTTP service. Private owns operator-controlled admission, frozen reruns, the official website and publication (one-way dependency Private → Public). See the architecture guide for the current package boundary. Write all repository Markdown in English, except `README_CN.md`.

## Starting Work

Run `git status --short --branch` and preserve unrelated changes. Use the [README](README.md) as the entry point and [CONTRIBUTING](CONTRIBUTING.md) for verification rules. Read the guide matching the change:

| Work | Read first |
|---|---|
| Module boundaries and extension interfaces | [Architecture](docs/architecture.md) |
| Tasks, inputs, sources, constraints, metrics, or judges | [Tasks and qualification](docs/tasks.md); the [exclusion checklist](docs/tasks.md#input-isolation) governs source surveys |
| Agents, submissions, events, batches, or statistics | [Running guide](docs/running.md) |
| Result archives or presentation data | [Result storage](docs/running.md#result-archive), [task presentation bindings](docs/running.md#task-presentations-and-interactive-layouts), and [archive verification](CONTRIBUTING.md#result-archive-verification) |
| Result packaging or website delivery | [Handoff boundaries](docs/architecture.md#result-handoff-and-storage-ownership) and [delivery contract](docs/running.md#website-result-delivery) |
| Images, dependencies, PDKs, EDA backends, or support bundles | [Tools guide](docs/tools.md); dependencies are declared in `pyproject.toml`, synchronized in `uv.lock` |
| Qualification admission, resource or endpoint approval, or report export | [Admission and export](docs/architecture.md#verified-reruns-and-disclosure) |

`third_party/` holds independent upstream submodules: exclude it from framework searches, format checks, and tests, and follow its own conventions for targeted changes. PDK implementation and signoff rules belong to the PDK repository; this framework manages integration and Git references.

## Execution and Completion

- Keep protocol, client, observation and analysis in `benchmarking/`, shared preparation/execution/EDA in `benchmarking/engine/`, the local HTTP adapter in `benchmarking/service/`, and reusable participant launch/configuration/MCP adapters in `benchmarking/participants/`. `benchmarking.run` schedules experiments; Agent harnesses retain their own decision loops. Private imports these modules through `iclayout_bench_private`; Public must not import operator code. Task-specific preparation, reference solutions, and qualification evidence live in the corresponding task directory. Public installation and CI must not depend on Private.
- Shared archive/import/query/presentation code belongs in `benchmarking.results`, and portable packaging/upload in `benchmarking.transfer`. Private owns the unified Web frontend and HTTP routes, website accounts, storage integration, publication permissions and leaderboard policy. Keep the local archive separate from the operator database; importing or publishing never changes recorded scores or verification levels.
- Maintained case schematics and their provenance follow the presentation contract above. Keep solver inputs explicit; drawings and a later presentation revision do not rewrite a historical task or attest its evaluation.
- Default to a compatible existing tool image or a thin derived image for development validation. Keep the public recipe/lock current and run affected checks; passing these checks completes development validation without a full rebuild. Before changing container dependencies or starting a full build, apply the triggers in [image development](docs/tools.md#image-development). Report the image used and actual checks.
- A standard solve materializes only declared inputs and reviewed resource bundles. Public reference solutions may be downloaded for debugging but are never mounted for a standard solver Agent. Follow the [task guide](docs/tasks.md#asset-rights) for sources and distribution.
- Evaluate frozen candidates independently with trusted materials, without Agent credentials or writable directories. DRC/LVS establishes physical validity; task success also requires the declared geometry and post-layout metrics.
- Rerun affected case validation and shared evaluator regressions when the judge, rules, or task changes; use the task guide to determine calibration scope. Deterministic protocol tests are not model scores.
- Update the owning guide as the single source of truth when behavior changes; keep onboarding in the README and verification guidance in CONTRIBUTING. Do not create `CONTEXT.md` or duplicate protocol documents.

When complete: select the affected checks from the [verification matrix](CONTRIBUTING.md#verification), check documentation links against the commands they describe, and report actual test scope and Git status. Verify and commit cross-repository changes separately; retain reviewable evidence for architecture and upstream-reference changes.
