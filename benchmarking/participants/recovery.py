"""Conservative failure evidence and participant recovery defaults."""
import math
import random
from dataclasses import dataclass

from benchmarking.retry import DEFAULTS as TRANSPORT_DEFAULTS
from benchmarking.retry import policy as transport_policy

from . import adapters
from .credentials import credential_values
from .failures import classify, failure

__all__ = ['CAPACITY_DEFAULTS', 'DISABLED', 'CapacityDecision', 'capacity_delay', 'capacity_ready', 'classify', 'continuation_id', 'credential_values', 'failure', 'plan_capacity_resume', 'policy']

DISABLED = TRANSPORT_DEFAULTS | {"resume_session": False}
CAPACITY_DEFAULTS = {"capacity_resumes": 5, "capacity_backoff_seconds": 30,
                     "capacity_max_backoff_seconds": 300, "capacity_cooldown_seconds": 300}


def policy(value=None, *, harness=None):
    defaults = DISABLED | CAPACITY_DEFAULTS
    if harness is not None and not adapters.supports(harness, "capacity_resumes"):
        defaults["capacity_resumes"] = 0
    if value is None:
        return defaults
    if (not isinstance(value, dict) or not set(DISABLED) <= set(value)
            or set(value) - (set(DISABLED) | set(CAPACITY_DEFAULTS))):
        raise ValueError("recovery requires http_attempts, backoff_seconds, max_backoff_seconds, resume_session; only capacity fields are optional")
    transport_policy(value)
    if type(value["resume_session"]) is not bool:
        raise ValueError("Invalid recovery resume_session")
    settings = defaults | value
    if type(settings["capacity_resumes"]) is not int or not 0 <= settings["capacity_resumes"] <= 10:
        raise ValueError("capacity_resumes must be between 0 and 10")
    for key in ("capacity_backoff_seconds", "capacity_max_backoff_seconds", "capacity_cooldown_seconds"):
        if type(settings[key]) not in (int, float) or not math.isfinite(settings[key]) or not 0 <= settings[key] <= 3600:
            raise ValueError(key + " must be finite and between 0 and 3600")
    if settings["capacity_max_backoff_seconds"] < settings["capacity_backoff_seconds"]:
        raise ValueError("capacity_max_backoff_seconds must be at least capacity_backoff_seconds")
    return settings


def capacity_delay(settings, attempt):
    """Bounded exponential delay with positive jitter; native retries have already ended."""
    cap = settings["capacity_max_backoff_seconds"]
    base = min(cap, settings["capacity_backoff_seconds"] * 2 ** attempt)
    return min(cap, base * random.uniform(1, 1.2))


def continuation_id(output, row, state, status):
    """Require the existing native session and fully resolved tool operations."""
    harness = row["harness"]
    if not adapters.supports(harness, "resume_session"):
        raise ValueError("This harness does not support same-session continuation")
    if ((output / "tools.pending.json").exists() or (output / "tools.delivery.json").exists()
            or status.get("active_execution_id")):
        raise ValueError("Unresolved tool operation; reconcile evidence before native continuation")
    native_id = adapters.session_id(harness, output, state)
    if not native_id:
        raise ValueError("No persisted native session ID; refusing a new session")
    return native_id


@dataclass(frozen=True)
class CapacityDecision:
    outcome: str
    native_id: str | None = None
    delay_seconds: float | None = None


def capacity_ready(status, native_id):
    """Recheck deadline and continuation safety immediately before a launch."""
    if status["state"] != "active" or status["remaining_seconds"] <= 0:
        return CapacityDecision("deadline")
    if not native_id:
        return CapacityDecision("unsafe_to_resume")
    return CapacityDecision("continued", native_id)


def plan_capacity_resume(settings, resumes, problem, status, native_id):
    """Choose one bounded wait or a terminal reason without changing attempt state."""
    if resumes >= settings["capacity_resumes"]:
        return CapacityDecision("limit_reached")
    ready = capacity_ready(status, native_id)
    if ready.outcome != "continued":
        return ready
    hint = problem.get("retry_after", 0)
    if hint > settings["capacity_max_backoff_seconds"]:
        return CapacityDecision("retry_after_exceeds_cap")
    delay = max(capacity_delay(settings, resumes), hint)
    if delay >= status["remaining_seconds"]:
        return CapacityDecision("deadline", delay_seconds=delay)
    return CapacityDecision("waiting", native_id, delay)
