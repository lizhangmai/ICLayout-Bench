# ICLayout-Bench Repository Conventions

This repository owns the official participant harness, generic client, public protocol, scoring specifications, development tasks and result analysis. It also owns the shared evaluation engine and local HTTP service. Private owns operator-controlled admission, frozen reruns and releases (one-way dependency Private → Public). See the architecture guide for the current package boundary. Write all repository Markdown in English, except `README_CN.md`.

## Starting Work

Run `git status --short --branch` and preserve unrelated changes. Use the [README](README.md) as the entry point and [CONTRIBUTING](CONTRIBUTING.md) for verification rules. Read the guide matching the change:

| Work | Read first |
|---|---|
| Module boundaries and extension interfaces | [Architecture](docs/architecture.md) |
| Tasks, inputs, sources, constraints, metrics, or judges | [Tasks and qualification](docs/tasks.md); the [exclusion checklist](docs/tasks.md#input-isolation) governs source surveys |
| Agents, submissions, events, batches, or statistics | [Running guide](docs/running.md) |
| Images, dependencies, PDKs, EDA backends, or support bundles | [Tools guide](docs/tools.md); dependencies are declared in `pyproject.toml`, synchronized in `uv.lock` |
| Qualification admission, resource or endpoint approval, or report export | [Admission and export](docs/admission.md) |

`third_party/` holds independent upstream submodules: exclude it from framework searches, format checks, and tests, and follow its own conventions for targeted changes. PDK implementation and signoff rules belong to the PDK repository; this framework manages integration and Git references.

## Execution and Completion

- Keep protocol, client, harness and analysis in `benchmarking/`, shared preparation/execution/EDA in `layout_eval/`, and the local HTTP adapter in `layout_service/`. Private imports these modules through `layout_operator`; Public must not import operator code. Task-specific preparation, reference solutions, and qualification evidence live in the corresponding task directory. Public installation and CI must not depend on Private.
- Reuse a compatible existing tool image during development. Before rebuilding, changing container dependencies, or validating release reproduction, follow [image development](docs/tools.md#image-development); keep the public build recipe current and report whether validation reused, derived, or rebuilt an image.
- A standard solve materializes only declared inputs and reviewed resource bundles. Public reference solutions may be downloaded for debugging but are never mounted for a standard solver Agent. Follow the [task guide](docs/tasks.md#asset-rights) for sources and distribution.
- Evaluate frozen candidates independently with trusted materials, without Agent credentials or writable directories. DRC/LVS establishes physical validity; task success also requires the declared geometry and post-layout metrics.
- Rerun affected case validation and shared evaluator regressions when the judge, rules, or task changes; use the task guide to determine calibration scope. Deterministic protocol tests are not model scores.
- Update the owning guide as the single source of truth when behavior changes; keep onboarding in the README and verification guidance in CONTRIBUTING. Do not create `CONTEXT.md` or duplicate protocol documents.

When complete: run the [verification matrix](CONTRIBUTING.md#verification), check documentation links against the commands they describe, and report actual test scope and Git status. Verify and commit cross-repository changes separately; retain reviewable evidence for architecture and upstream-reference changes.
