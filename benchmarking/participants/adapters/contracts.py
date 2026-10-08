"""Small structural contract shared by participant harness adapters."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

HARNESS_MODULES = {
    "codex": ".codex",
    "claude-code": ".claude",
    "dsh": ".dsh",
    "kimi-code": ".kimi",
    "command": ".command",
}
HARNESSES = tuple(HARNESS_MODULES)
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")


@dataclass(frozen=True)
class ParticipantSelection:
    """Public condition and private launch inputs resolved by one harness."""

    condition: dict[str, Any]
    environment: dict[str, str] = field(repr=False)
    settings: dict[str, Any] = field(repr=False)

    def with_environment(self, **values):
        return ParticipantSelection(self.condition, dict(self.environment, **values), self.settings)

    def launch_payload(self):
        """Private worker-pipe payload; never part of a persisted condition."""
        return {"condition": self.condition, "environment": self.environment, "settings": self.settings}


@dataclass(frozen=True)
class LaunchContext:
    """Prepared private launch inputs; never serialize this into public results."""

    selection: ParticipantSelection = field(repr=False)
    mcp: Path
    directory: Path
    output: Path
    bridge: Path
    prompt: str


@dataclass(frozen=True)
class HarnessMetadata:
    executable: str | None
    home_environment: str
    home_directory: str
    credential_file: str | None = None

    def home(self, env):
        return Path(env.get(self.home_environment, str(Path.home() / self.home_directory)))


class HarnessAdapter(Protocol):
    CAPABILITIES: ClassVar[dict[str, bool]]
    METADATA: ClassVar[HarnessMetadata]

    def resolve(
        self, model: str | None, effort: str | None, env: dict[str, str]
    ) -> ParticipantSelection: ...

    def prepare(self, context: LaunchContext) -> list[str]: ...
