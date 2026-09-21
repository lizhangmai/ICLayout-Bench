"""Run a tool with frozen files in a fresh container, retaining failure evidence."""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from benchmarking.evaluation import number
from benchmarking.files import Asset, ReadOnlyMount, read_file, relative


@dataclass
class ToolResult:
    returncode: int | None
    reason: str
    files: dict[str, Asset]
    evidence: dict[str, Asset]


class DockerTool:
    CPUS = 4
    MEMORY_MB = 4096
    PIDS = 256

    @property
    def limits(self) -> dict:
        return {"cpus": self.CPUS, "memory_mb": self.MEMORY_MB, "pids": self.PIDS}

    def _limit_args(self) -> list[str]:
        return ["--memory", f"{self.MEMORY_MB}m", "--cpus", str(self.CPUS),
                "--pids-limit", str(self.PIDS)]

    def __init__(self, image: str, version_command: list[str], timeout_seconds: float):
        self.timeout_seconds = number(timeout_seconds)
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        self.image_id = subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True,
        ).strip()
        self.version = subprocess.check_output(
            ["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
             "--security-opt", "no-new-privileges", *self._limit_args(),
             "--user", "1000:1000", self.image_id, *version_command],
            text=True, stderr=subprocess.STDOUT, timeout=self.timeout_seconds,
        ).strip()

    @property
    def identity(self) -> dict:
        return {"image_id": self.image_id, "tool_version": self.version,
                "timeout_seconds": self.timeout_seconds, "limits": self.limits,
                "execution_sha256": Asset(Path(__file__).read_bytes(), "python").sha256}

    def run(self, command: list[str], files: dict[str, Asset | ReadOnlyMount], exports: dict[str, str], *,
            environment: dict[str, str] | None = None) -> ToolResult:
        """Copy case inputs and bind installed resources read-only.

        exports maps paths to formats. Collect declared files even on failure;
        never interpret tool output as a successful circuit check here.
        """
        for name in (*files, *exports):
            relative(name, "tool file")
        evidence, produced = {}, {}
        code, reason = None, ""
        with tempfile.TemporaryDirectory(prefix="iclayout-bench-tool-") as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            mounts = []
            for name, asset in files.items():
                if isinstance(asset, ReadOnlyMount):
                    target = source / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    mounts.extend(asset.docker_args(f"/workspace/{name}"))
                    continue
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(asset.content)
                path.chmod(0o444)
            # runc creates bind targets as root; tool-generated scripts need writable parents.
            for directory in source.rglob("*"):
                if directory.is_dir():
                    directory.chmod(0o777)
            env_args = [arg for k, v in (environment or {}).items() for arg in ("--env", f"{k}={v}")]
            cid = subprocess.check_output([
                "docker", "create", "--network", "none", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", *self._limit_args(),
                "--user", "1000:1000", "--workdir", "/workspace",
                *env_args, *mounts, self.image_id, *command,
            ], text=True).strip()
            try:
                subprocess.run(["docker", "cp", f"{source}/.", f"{cid}:/workspace"],
                               check=True, capture_output=True)
                try:
                    run = subprocess.run(["docker", "start", "-a", cid], capture_output=True,
                                         timeout=self.timeout_seconds, check=False)
                    evidence["console"] = Asset(run.stdout + run.stderr, "text")
                    code = int(subprocess.check_output(
                        ["docker", "inspect", "--format", "{{.State.ExitCode}}", cid], text=True))
                    if run.returncode or code:
                        reason = f"Tool/container exited with {code} (docker {run.returncode})"
                except subprocess.TimeoutExpired as error:
                    subprocess.run(["docker", "kill", cid], capture_output=True, check=False)
                    evidence["console"] = Asset((error.stdout or b"") + (error.stderr or b""), "text")
                    reason = "Tool exceeded its fixed time limit"
                for index, (name, file_format) in enumerate(exports.items()):
                    destination = f"export-{index}"
                    copied = subprocess.run(["docker", "cp", f"{cid}:/workspace/{name}", str(root / destination)],
                                            capture_output=True, check=False)
                    if copied.returncode:
                        evidence[f"missing:{name}"] = Asset(copied.stderr, "text")
                        reason = reason or f"Declared tool output is missing: {name}"
                    else:
                        produced[name] = Asset(read_file(root, destination), file_format)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                reason = f"{type(error).__name__}: {error}"
                evidence["execution_error"] = Asset(str(error).encode(), "text")
            finally:
                cleanup = subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)
                if cleanup.returncode:
                    reason = reason or "Container cleanup failed"
                    evidence["cleanup_error"] = Asset(cleanup.stderr, "text")
        return ToolResult(code, reason, produced, evidence)
