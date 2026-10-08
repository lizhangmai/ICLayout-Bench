"""Tool-independent results and the trusted evaluation backend interface."""

from dataclasses import dataclass, field
from typing import Protocol

from benchmarking.evaluation.contracts import Job
from benchmarking.files import Asset


@dataclass(frozen=True)
class Measurement:
    value: float
    unit: str


@dataclass
class JobResult:
    status: str  # passed, failed (completed check), or error (no valid result)
    reason: str = ""
    measurements: dict[str, Measurement] = field(default_factory=dict)
    outputs: dict[str, Asset] = field(default_factory=dict)
    evidence: dict[str, Asset] = field(default_factory=dict)


class Backend(Protocol):
    """A trusted tool adapter. It must not read the solver's mutable workspace.

    run receives only immutable declared inputs and fresh parameters. Return
    failed only for a completed check rejecting the artifact; tool failures and
    unsupported settings are errors. Evidence is returned as bytes for archival.
    A backend may use a container, subprocess, remote worker or native library.
    Reentrant backends may advertise max_parallel_jobs; other backends run serially.
    """

    @property
    def identity(self) -> dict: ...

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult: ...
