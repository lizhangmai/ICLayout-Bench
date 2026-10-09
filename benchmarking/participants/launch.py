"""Prepare an attempt's credentials, scoped bridge environment and native CLI."""

import json
import math
import sys
from pathlib import Path

from benchmarking.files import write_json as save

from . import adapters
from .adapters.contracts import LaunchContext, ParticipantSelection
from .recovery import DISABLED
from .scheme import mcp_servers

ROOT = Path(__file__).resolve().parent


class ParticipantLaunch:
    def __init__(self, row, selection: ParticipantSelection, output, created):
        self.harness, self.scheme = row["harness"], row.get("scheme", {})
        self.condition, self.env, self.settings = selection.condition, selection.environment, selection.settings
        self.output, self.created = output, created
        self.private = output / ".private"

    def _configure(self, endpoint, settings_policy, attempt):
        """Stage native credentials and bind only the scoped session to the CLI."""
        private, env, output = self.private, self.env, self.output
        created, condition = self.created, self.condition
        sid = created["session_id"]
        # Native histories belong to the attempt, alongside (but outside) shareable exports.
        # Seed only authentication; continuations preserve native token refreshes.
        # Never copy user hooks, rules or session history.
        attempt.add_redactions(adapters.stage_credentials(self.harness, private, env))
        env["ICLAYOUT_BENCH_NATIVE_ID"] = attempt.state.native_id
        # The bridge owns service transport only; native continuation stays in this supervisor.
        env["ICLAYOUT_BENCH_RECOVERY"] = json.dumps({key: settings_policy[key] for key in DISABLED})
        # Only a scoped session credential reaches the native CLI/bridge subprocess.
        env.update(ICLAYOUT_BENCH_ENDPOINT=endpoint, ICLAYOUT_BENCH_TOKEN=created["session_token"],
                   ICLAYOUT_BENCH_SESSION=sid, ICLAYOUT_BENCH_PARTICIPANT_TOOL_LOG=str(output / "tools.jsonl"),
                   ICLAYOUT_BENCH_COMMAND_SECONDS=str(created["limits"]["max_command_seconds"]),
                   ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS=str(math.ceil(created["limits"]["wall_seconds"]) + 60))
        env["ICLAYOUT_BENCH_TASK_FILE"] = str((output / "session.json").resolve())
        env["ICLAYOUT_BENCH_MODEL"] = condition["model"]
        env["ICLAYOUT_BENCH_EFFORT"] = condition.get("effort_resolved") or ""
        env["MCP_TOOL_TIMEOUT"] = str(int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]) * 1000)

    def prepare(self, endpoint, settings_policy, attempt, instructions) -> LaunchContext:
        """Bind scoped credentials and prepare all inputs needed to construct a command."""
        self._configure(endpoint, settings_policy, attempt)
        private, env = self.private, self.env
        created, scheme, settings = self.created, self.scheme, self.settings
        directory = private / "workspace"
        directory.mkdir(mode=0o700, exist_ok=True)
        mcp = directory / "mcp.json"
        # Explicit bridge env is needed because some CLI versions filter inherited env.
        extra_servers = mcp_servers(scheme, {k: v for k, v in env.items() if k.startswith("ICLAYOUT_BENCH_")})
        settings = dict(settings, mcp_servers=extra_servers)
        if "launch" in scheme:
            settings["launch"] = scheme["launch"]
        save(mcp, {"mcpServers": {**extra_servers, "layout": {"command": sys.executable,
             "args": ["-I", str(ROOT / "bridge.py")],
             "env": {k: v for k, v in env.items() if k.startswith("ICLAYOUT_BENCH_")}}}})
        env["ICLAYOUT_BENCH_MCP_CONFIG"] = str(mcp.resolve())
        prompt = instructions + "\nTASK CONTRACT:\n" + json.dumps(created["task"]) + "\nBudget seconds: " + str(created["limits"]["wall_seconds"])
        return LaunchContext(ParticipantSelection(self.condition, env, settings), mcp,
                             directory, self.output, ROOT / "bridge.py", prompt)
