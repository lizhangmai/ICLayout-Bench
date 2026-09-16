# Verified Reruns and Disclosure

The public [protocol](architecture.md#http-session) owns trust labels and result
fields. Admission, raw evidence verification and release construction execute in
Private. A request that claims an official harness does not raise its trust level.

## Frozen evaluator-operated reruns

Before model calls, an operator freezes the task set and digests, model/harness
configuration, prompt policy, source digests, provider version, EDA image and
backend identities, resource inventories, budgets and repetition schedule. Each
slot starts an independent workspace. The pre-run manifest digest is retained
outside the output bundle as the verification anchor.

The operator checks every scheduled slot, the harness configuration and action
transcript, last durable submission, archived candidate bytes and independent
verdict. Modified evidence or missing repetitions fail verification. Only the
controlled harness loop receives `evaluator_verified`; a harness failure retains
`service_recorded`. Local custom runs remain `local_development`. These are
operator assertions backed by evidence, not signatures authenticating a remote
operator. Publish the identity/trust arrangement separately when deploying a service.

CLI-reported token counters remain separate from service-observed usage. A frozen
model identifier establishes requested conditions, not an assertion about a remote
provider's internal implementation. Unknown cost/usage is never zero-filled.

## Hidden data

The operator HTTP rerun exporter accepts only `public_development`. Hidden designs
use Private's admission-controlled workflow: unpublished sources and authorization,
qualification evidence, resource/endpoint review, an immutable task/repetition
plan and a single-use exposure reservation are required before execution.
Synthetic hidden fixtures test these boundaries; they are not real hidden tasks.
Software cannot prove unpublished origin, licensing rights or provider retention
arrangements. Those remain explicit operator records.

A hidden release is reconstructed from an approved field allowlist and fixed
aggregate groups. It suppresses small task/family/trial groups and exposes neither
per-task identifiers/metrics nor raw logs, paths, candidates or qualifications.
Changing the release policy after a run cannot relax its original restrictions.
Public-task rerun releases and hidden aggregate releases are different artifacts.

## Publication boundary

Analysis is local by default. Generating a reviewed release artifact does not
upload it or make a leaderboard. Keep credentials and growing raw evidence out
of Git. Actual hidden-task qualification, deployment identities and authority to
publish restricted materials must exist before a real hidden release. The
framework's tests and a successful public rerun do not supply that authority.
