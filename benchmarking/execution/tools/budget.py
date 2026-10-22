"""Caller-owned time and cancellation policy for EDA executions."""

import subprocess
import time
from contextlib import contextmanager
from contextvars import ContextVar

_LIMIT_TOOLS = ContextVar('limit_eda_tools', default=True)
_CANCELLATION = ContextVar('cancel_eda_tools', default=None)


class ToolCancelled(Exception):
    """The owner of this check has cancelled its tool executions."""


@contextmanager
def tool_cancellation(event):
    token = _CANCELLATION.set(event)
    try:
        yield
    finally:
        _CANCELLATION.reset(token)


def current_tool_cancellation():
    """Capture the check's scope before dispatching work to another thread."""
    return _CANCELLATION.get()


def tool_cancelled():
    event = current_tool_cancellation()
    return event is not None and event.is_set()


def wait_for_tool(process, seconds, *, capture=False):
    """Wait without losing cancellation when the caller permits unlimited time."""
    deadline = None if seconds is None else time.monotonic() + seconds
    while True:
        if tool_cancelled():
            raise ToolCancelled('EDA execution cancelled by its check owner')
        remaining = None if deadline is None else max(0, deadline - time.monotonic())
        try:
            wait = process.communicate if capture else process.wait
            return wait(timeout=.1 if remaining is None else min(.1, remaining))
        except subprocess.TimeoutExpired:
            if deadline is not None and time.monotonic() >= deadline:
                raise


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
