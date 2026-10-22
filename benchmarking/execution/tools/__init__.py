"""Result values shared by containerized and native tools."""

from dataclasses import dataclass

from benchmarking.files import Asset


@dataclass
class ToolResult:
    returncode: int | None
    reason: str
    files: dict[str, Asset]
    evidence: dict[str, Asset]
