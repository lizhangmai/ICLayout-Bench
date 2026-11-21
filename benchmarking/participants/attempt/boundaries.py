"""External effects of a participant attempt, passed as one replaceable value.

Production code uses ``DEFAULT_BOUNDARIES``. Offline checks substitute the
evaluation service, native process, CLI version probe and clock here rather
than patching module attributes.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from benchmarking.client import Client
from benchmarking.execution.process import execute
from benchmarking.participants.attempt.service import service
from benchmarking.participants.harnesses import registry
from benchmarking.participants.isolation import NativeRuntime


@dataclass(frozen=True)
class AttemptBoundaries:
    """Collaborators that reach a service, a native CLI or the system clock.

    ``client(endpoint, token, **options)`` returns a session HTTP client.
    ``local_service(case, output, image, recoverable)`` is a context manager
    yielding access to a local evaluation service. ``native_command(context)``
    returns the native CLI argv; ``isolation(context, **declared)`` returns the
    isolated runtime context; ``execute(argv, **process)`` runs one bounded child
    and returns ``(exit_code, timed_out)``. ``cli_version(harness, scheme)`` is
    recorded in frozen conditions. ``clock`` provides ``monotonic()``, ``time()``
    and ``sleep(seconds)``, as the :mod:`time` module does.
    """

    client: Callable[..., Any] = Client
    local_service: Callable[..., Any] = service
    native_command: Callable[..., list[str]] = registry.prepare
    isolation: Callable[..., Any] = NativeRuntime
    execute: Callable[..., tuple[int | None, bool]] = execute
    cli_version: Callable[..., str] = registry.cli_version
    clock: Any = time


DEFAULT_BOUNDARIES = AttemptBoundaries()
