# ICLayout-Bench Repository Conventions

This repository owns the standalone evaluation framework, participant interfaces,
shared scoring, EDA adapters, local HTTP service and result interfaces.
Start with [README](README.md), run `git status --short --branch`, and preserve unrelated changes.

## Read for the Change

| Work | Read first |
| --- | --- |
| Public interfaces or protocol boundaries | [Architecture](docs/architecture.md) |
| Tasks, inputs, metrics or judges | [Task contract](docs/tasks.md) and [qualification](CONTRIBUTING.md#task-qualification) |
| Participation, sessions, batches or statistics | [Running guide](docs/running.md) |
| Archives or presentation assets | [Result storage](docs/running.md#result-archive), [presentation bindings](docs/running.md#task-presentations-and-interactive-layouts) and [archive verification](CONTRIBUTING.md#result-archive-verification) |
| Result delivery, admission or disclosure | [Handoff boundaries](docs/architecture.md#result-handoff-and-storage-ownership) and [verified reruns](docs/architecture.md#verified-reruns-and-disclosure) |
| Images, dependencies, PDKs or backends | [Tools](docs/tools.md) and [image development](CONTRIBUTING.md#image-development) |
| Tests or fixtures | [Test conventions](tests/AGENTS.md) |
| Participant examples | [Installed-package examples](examples/README.md) |
| Generated website artifacts or Pages workflow | [Static hosting](docs/architecture.md#static-website-hosting) |

## Implementation Boundaries

- Follow the public interface boundaries in the architecture guide. Consumers use installed
  public interfaces; package imports, installation and offline CI work without sibling repositories.
- Load static Dataset inputs through explicit paths or IDs. Authoring code and
  qualification evidence remain with the author; operator policy and website code
  remain with their owning applications.
- Standard solves expose only [declared inputs and reviewed resources](docs/tasks.md#input-isolation).
  Evaluate frozen candidates independently of solver credentials and writable directories.
- Keep original scores, identities and verification levels when archiving or
  delivering results. Website review and publication belong to the operator.
- README owns onboarding; `docs/` contains user-facing guides and public contracts.
  CONTRIBUTING owns development and verification workflows. Keep plans, review logs
  and local validation evidence out of `docs/`. Public guides must be usable from
  this repository alone and must not link to local evidence or sibling repositories.
  Update the owning guide when behavior changes; avoid duplicate protocol documents or `CONTEXT.md`.
- Keep generated website content on the reviewed `gh-pages` branch. Package sources
  and CI on `main` remain independent of those artifacts.

## Completion

Select checks by change scope and delivery stage from [CONTRIBUTING](CONTRIBUTING.md#verification).
Check changed links and commands, and report actual validation scope and Git status.
Verify and commit affected repositories separately.
