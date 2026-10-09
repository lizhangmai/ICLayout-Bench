"""Lazy adapter lookup for participant harness configuration and launch."""

from __future__ import annotations

import json
import re
import subprocess
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from benchmarking.files import atomic_write, relative

from ..credentials import credential_values
from .contracts import EFFORTS as EFFORTS
from .contracts import (
    HARNESS_MODULES,
    HarnessAdapter,
    LaunchContext,
    ParticipantSelection,
)
from .contracts import HARNESSES as HARNESSES

if TYPE_CHECKING:
    from ..attempt import AttemptState

def get(harness: str) -> HarnessAdapter:
    try:
        module = HARNESS_MODULES[harness]
    except KeyError as error:
        raise ValueError("Unknown harness") from error
    return import_module(module, __name__)


def capabilities(harness: str) -> dict[str, bool]:
    return get(harness).CAPABILITIES


def supports(harness: str, capability: str) -> bool:
    return capabilities(harness).get(capability, False)


def cli_version(harness, scheme=None):
    executable = get(harness).METADATA.executable
    if executable is None:
        return scheme["version"]
    return subprocess.check_output([executable, "--version"], text=True, timeout=20).strip()


def harness_version(harness):
    raw = cli_version(harness)
    match = re.search(r"(?<![\w.])v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)", raw)
    if not match:
        raise ValueError("Cannot identify harness version from --version: " + harness)
    return match.group(1), raw


def stage_credentials(harness, private, env):
    adapter = get(harness)
    stage = getattr(adapter, 'stage_credentials', None)
    if stage:
        return stage(private, env)
    metadata = adapter.METADATA
    filename = metadata.credential_file
    if filename is None:
        return set()
    original = metadata.home(env)
    target = private / "native-home"
    target.mkdir(mode=0o700, exist_ok=True)
    credential = original / filename
    redactions = set()
    if credential.is_file():
        raw = credential.read_bytes()
        if not (target / filename).exists():
            atomic_write(target / filename, raw)
        try:
            redactions = credential_values(json.loads(raw))
        except ValueError:
            pass  # Native CLI owns validation of its opaque credential format.
    env[metadata.home_environment] = str(target.resolve())
    return redactions | credential_redactions(harness, private.parent)


def credential_redactions(harness, output):
    """Include native token refreshes in every exported trace, not only native files."""
    adapter = get(harness)
    reader = getattr(adapter, 'credential_redactions', None)
    if reader:
        return reader(output)
    filename = adapter.METADATA.credential_file
    if filename is None:
        return set()
    home = Path(output) / '.private/native-home'
    path = home / filename
    if path.is_file() and path.resolve().is_relative_to(home.resolve()):
        try:
            return credential_values(json.loads(path.read_bytes()))
        except (ValueError, UnicodeError):
            pass
    return set()


def harness_failure(harness, output, exit_code=None, timed_out=False):
    from .events import harness_failure as structured_failure

    parser = getattr(get(harness), "harness_failure", structured_failure)
    return parser(output, exit_code, timed_out)


def resolve(
    harness: str, model: str | None, effort: str | None, env: dict[str, str]
) -> ParticipantSelection:
    return get(harness).resolve(model, effort, env)


def prepare(context: LaunchContext) -> list[str]:
    return get(context.selection.condition["harness"]).prepare(context)


def session_id(harness: str, output: Path, state: AttemptState) -> str | None:
    adapter = get(harness)
    provider_session_id = getattr(adapter, "session_id", None)
    return provider_session_id(output, state) if provider_session_id else None


def native_traces(harness: str, output: Path) -> dict[str, bytes]:
    """Optional adapter-owned records; callers apply attempt-wide redaction."""
    collector = getattr(get(harness), 'native_traces', None)
    return {relative(name, 'native trace name'): raw for name, raw in collector(output).items()} if collector else {}
