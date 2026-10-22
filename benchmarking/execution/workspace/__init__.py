"""Solver workspace interfaces and immutable completion data."""

from dataclasses import dataclass, field

from benchmarking.files import Asset


@dataclass
class SessionResult:
    """Why a session stopped, its frozen submission and bounded feedback."""

    termination: str
    reason: str
    elapsed_seconds: float
    exit_code: int | None
    submissions: list[dict]
    candidate: Asset | None
    console: Asset
    console_truncated: bool
    environment: dict
    process_feedback: list[dict] = field(default_factory=list)
    benchmark_feedback: list[dict] = field(default_factory=list)


__all__ = ["SessionResult"]
