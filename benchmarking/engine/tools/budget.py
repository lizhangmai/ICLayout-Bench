"""Caller-owned time policy for EDA executions, including parallel jobs."""

from contextlib import contextmanager
from contextvars import ContextVar

_LIMIT_TOOLS = ContextVar('limit_eda_tools', default=True)


@contextmanager
def tool_time_limits(enabled):
    token = _LIMIT_TOOLS.set(enabled)
    try:
        yield
    finally:
        _LIMIT_TOOLS.reset(token)


def tool_timeout(seconds):
    """Probes remain bounded; evaluation callers may let started jobs finish."""
    return seconds if _LIMIT_TOOLS.get() else None
