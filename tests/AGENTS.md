# Test Conventions

Applies to tests, fixtures and generators. Commands and validation scope belong
to [CONTRIBUTING](../CONTRIBUTING.md#verification).

## Assertions and Configuration

- Extend existing coverage for the public behavior and a concrete failure case;
  add a separate test or fixture only when reuse is insufficient.
- Derive expected results independently from the contract or a separate calculation.
  Read configurable values from their owner; fixed protocol values and independent
  worked examples may use literals. Copying implementation output is not an oracle.
- Assert contract guarantees rather than internal call sequences, paths, ordering
  or counts that the contract does not specify.
- Replace external I/O, tools and execution at their boundaries; run the behavior
  under test for real. Prefer minimal synthetic inputs and reuse existing fixtures.
- Investigate failures against the contract before changing expectations. Remove
  redundant assertions and update callers and documentation when withdrawing coverage.

## Case and EDA Regressions

Discover cases and resources from declared catalogs and profiles; keep circuit
authoring, repair procedures and qualification evidence in Designs. Disposable
test outputs belong in `build/runs/`.
For extraction/model validation, use [analytical controls](../CONTRIBUTING.md#analytical-controls);
for reference acceptance, use [qualification](../CONTRIBUTING.md#task-qualification).

Report the behavior actually checked and remaining gaps. Protocol coverage,
reference feasibility and independent extraction accuracy support distinct claims.
