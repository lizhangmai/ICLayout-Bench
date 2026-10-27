"""Caller-owned time and cancellation policy for EDA executions."""

import subprocess
import time
from contextlib import contextmanager
from contextvars import ContextVar

_LIMIT_TOOLS = ContextVar('limit_eda_tools', default=False)
_DEADLINE = ContextVar('eda_phase_deadline', default=None)
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


def wait_for_retry(seconds):
    """Back off without renewing the owner's deadline or losing cancellation."""
    until = time.monotonic() + seconds
    while True:
        if tool_cancelled():
            return 'cancelled'
        now, deadline = time.monotonic(), current_tool_deadline()
        if deadline is not None and now >= deadline:
            return 'deadline'
        remaining = until - now
        if remaining <= 0:
            return None
        delay = min(.1, remaining, deadline-now if deadline is not None else remaining)
        cancellation = current_tool_cancellation()
        if cancellation is not None:
            cancellation.wait(delay)
        else:
            time.sleep(delay)


@contextmanager
def tool_time_limits(enabled):
    token = _LIMIT_TOOLS.set(enabled)
    try:
        yield
    finally:
        _LIMIT_TOOLS.reset(token)


def current_tool_time_limits():
    """Capture the shared policy before dispatching EDA work to another thread."""
    return _LIMIT_TOOLS.get()


def current_tool_deadline():
    return _DEADLINE.get()


@contextmanager
def tool_deadline(deadline):
    previous = current_tool_deadline()
    token = _DEADLINE.set(min(previous, deadline) if previous is not None and deadline is not None
                          else previous if deadline is None else deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def tool_timeout(seconds):
    """EDA jobs finish by default; only explicit tool limits or enclosing deadlines apply."""
    value = seconds if _LIMIT_TOOLS.get() else None
    deadline = current_tool_deadline()
    if deadline is not None:
        remaining = max(0, deadline-time.monotonic())
        return remaining if value is None else min(value, remaining)
    return value
