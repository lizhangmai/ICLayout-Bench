"""Lazy adapter lookup for participant harness configuration and launch."""

from __future__ import annotations

import json
import re
import subprocess
from contextlib import nullcontext
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

from benchmarking.files import relative
from benchmarking.participants.harnesses.contracts import (
    EFFORTS,
    HARNESS_MODULES,
    HARNESSES,
    HarnessAdapter,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.credentials import (
    credential_values,
    select_home,
    stage_file_credentials,
    sync_files,
)

if TYPE_CHECKING:
    from benchmarking.participants.attempt.state import AttemptState

def get(harness: str) -> HarnessAdapter:
    try:
        module = HARNESS_MODULES[harness]
    except KeyError as error:
        raise ValueError("Unknown harness") from error
    implementation = import_module(module, __package__)
    from benchmarking.participants.harnesses.events import (
        harness_failure as default_failure,
    )

    return HarnessAdapter(
        METADATA=implementation.METADATA, CAPABILITIES=implementation.CAPABILITIES,
        resolve=implementation.resolve, prepare=implementation.prepare, usage=implementation.usage,
        native_traces=getattr(implementation, "native_traces", lambda output: {}),
        harness_failure=getattr(implementation, "harness_failure", default_failure),
        **{name: getattr(implementation, name, None) for name in
           ("session_id", "stage_credentials", "credential_redactions", "observe_usage")},
    )


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


def stage_credentials(harness, private, env, settings=None):
    adapter = get(harness)
    stage = getattr(adapter, 'stage_credentials', None)
    if stage:
        return stage(private, env, settings)
    metadata = adapter.METADATA
    return stage_file_credentials(metadata, private, env, settings)


def sync_credentials(harness, private, env, settings):
    """Let file-backed adapters retain refreshed authentication before cleanup."""
    if "native_home" in settings:
        sync_files(private)


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
    from benchmarking.participants.harnesses.events import (
        harness_failure as structured_failure,
    )

    parser = getattr(get(harness), "harness_failure", structured_failure)
    return parser(output, exit_code, timed_out)


def resolve(
    harness: str, model: str | None, effort: str | None, env: dict[str, str], *, home: Path | None = None
) -> ParticipantSelection:
    adapter = get(harness)
    if home is None:
        return adapter.resolve(model, effort, env)
    env = env.copy()
    home = select_home(adapter.METADATA, env, home)
    selection = adapter.resolve(model, effort, env, home=home)
    return ParticipantSelection(selection.condition, selection.environment,
                                dict(selection.settings, native_home=str(home)))


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


def usage(harness, agent, native):
    """Interpret native billing evidence without promoting it to service observation."""
    return get(harness).usage(agent, native)


def observe_usage(harness, output, env):
    observer = get(harness).observe_usage
    return observer(output, env) if observer is not None else nullcontext()



__all__ = [
    "EFFORTS",
    "HARNESSES",
    "capabilities",
    "cli_version",
    "credential_redactions",
    "get",
    "harness_failure",
    "harness_version",
    "native_traces",
    "observe_usage",
    "prepare",
    "resolve",
    "session_id",
    "stage_credentials",
    "supports",
    "sync_credentials",
    "usage",
]
