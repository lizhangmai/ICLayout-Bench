# ICLayout-Bench Repository Conventions

This repository owns the standalone evaluation framework, participant interfaces,
shared scoring, EDA adapters, HTTP evaluation service and result interfaces.
Start with [README](README.md), run `git status --short --branch`, and preserve unrelated changes.

## Read for the Change

| Work | Read first |
| --- | --- |
| Public interfaces or protocol boundaries | [Architecture](docs/architecture.md), especially the [HTTP contract](docs/architecture.md#http-session) |
| Tasks, inputs, metrics or judges | [Task contract](docs/tasks.md) and [qualification](docs/tasks.md#qualification) |
| Participation, native configuration, scheduling or recovery | [Running](docs/running.md) |
| Statistics, archives or presentation assets | [Results and analysis](docs/running.md#results-and-analysis) and [archive verification](CONTRIBUTING.md#result-archive-verification) |
| Shared execution, frozen evidence or result finalization | [Shared interfaces](docs/architecture.md#shared-execution-and-evidence-interfaces) |
| Images, PDKs, adapters or measurements | [Tools](docs/tools.md) and [image development](CONTRIBUTING.md#image-development) |
| Result delivery, review or disclosure | [Handoff boundaries](docs/architecture.md#result-handoff-and-storage-ownership) and [controlled runs](docs/architecture.md#verified-reruns-and-disclosure) |
| Tests or fixtures | [Test conventions](tests/AGENTS.md) |

## Implementation Boundaries

- Follow the public interface boundaries in the architecture guide. Consumers use installed
  public interfaces; package imports, installation and offline CI work without sibling repositories.
- Load static Dataset inputs through explicit paths or IDs. Authoring code and
  qualification evidence remain with the author; operator policy and website code
  remain with their owning applications.
- Standard solves expose only [declared inputs and reviewed resources](docs/tasks.md#input-isolation).
  Evaluate frozen candidates independently of solver credentials and writable directories.
- Evaluate submitted circuits without completing solver work. Adapters may bind run
  I/O, parse reports and reorder existing named ports; preserve extracted device
  models, parameters and connections. Process compatibility belongs to declared
  resources and author validation. Before changing extraction or netlist adapters,
  read [evaluator responsibilities](docs/architecture.md#system-roles-and-boundaries).
- Own shared participant lifecycle, single-run evidence verification, machine-readable
  results, usage semantics, shared statistical interfaces and EDA layout preview assets.
  The consuming website owns secondary aggregation, weighting, ranking, charts,
  interactive comparisons and report presentation; analysis commands export JSON/CSV.
- Keep original scores, usage, identities and verification levels when archiving or
  delivering results, and distinguish derived aggregates from original results.
  Website review and publication belong to the operator.
- README introduces the project and owns documentation navigation; `docs/`
  contains user guides and public contracts. Links inside `docs/` stay within that
  directory; explain required behavior locally instead of referring readers to
  repository-root documents or upstream websites.
  CONTRIBUTING owns development and verification workflows. Keep plans, review logs
  and local validation evidence out of `docs/`. Public guides must be usable from
  this repository alone and must not link to local evidence or sibling repositories.
  Update the owning guide when behavior changes. Architecture owns the HTTP
  contract, responsibilities and extension boundaries.
- Set up development dependencies from the project declarations and lockfile using
  [development setup](CONTRIBUTING.md#development-setup). Keep generated results,
  credentials and machine-specific settings out of tracked source. Document commands
  that work from a fresh clone or an installed package; accept explicit Dataset,
  image and output selections without requiring a maintainer's workspace layout.

## Completion

Select checks by change scope and delivery stage from [CONTRIBUTING](CONTRIBUTING.md#verification).
Check changed links and commands, and report actual validation scope and Git status.
Verify affected repositories separately; commit only when authorized, with one repository per commit.
