"""Codex configuration and isolated command construction."""

import json
import sys
import tomllib
from pathlib import Path

from .contracts import EFFORTS, HarnessMetadata, LaunchContext, ParticipantSelection

METADATA = HarnessMetadata('codex', 'CODEX_HOME', '.codex', 'auth.json')

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}


def resolve(model, effort, env):
    path = Path(env.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    settings = tomllib.loads(path.read_text()) if path.exists() else {}
    profile = settings.get("profile")
    effective = dict(settings)
    if profile:
        effective.update(settings.get("profiles", {}).get(profile, {}))
    model = model or effective.get("model")
    resolved_effort = effort
    source = "experiment" if effort is not None else "harness default (unresolved)"
    if effort is None:
        resolved_effort = effective.get("model_reasoning_effort")
        if resolved_effort:
            source = "codex user configuration"
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Supply --model or configure a default model in the selected harness")
    if resolved_effort is not None and resolved_effort not in EFFORTS:
        raise ValueError("Unsupported effort value; use an effort accepted by your CLI/model")
    condition = {
        "harness": "codex",
        "model": model,
        "effort_requested": effort,
        "effort_resolved": resolved_effort,
        "effort_source": source,
        "provider_effective_effort": None,
    }
    return ParticipantSelection(condition, env, {})


def prepare(context: LaunchContext) -> list[str]:
    condition = context.selection.condition
    env = context.selection.environment
    settings = context.selection.settings
    bridge = context.bridge
    args = [
        "codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--json",
        "-m",
        condition["model"],
    ]
    values = {
        "approval_policy": "never",
        "project_doc_max_bytes": 0,
        "web_search": "disabled",
        "mcp_servers.layout.default_tools_approval_mode": "approve",
        "mcp_servers.layout.command": sys.executable,
        "mcp_servers.layout.args": ["-I", str(bridge)],
        "mcp_servers.layout.env_vars": [
            "ICLAYOUT_BENCH_ENDPOINT",
            "ICLAYOUT_BENCH_TOKEN",
            "ICLAYOUT_BENCH_SESSION",
            "ICLAYOUT_BENCH_PARTICIPANT_TOOL_LOG",
            "ICLAYOUT_BENCH_COMMAND_SECONDS",
            "ICLAYOUT_BENCH_RECOVERY",
        ],
        "mcp_servers.layout.tool_timeout_sec": int(
            env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]
        ),
        "features.skip_host_skill_discovery": True,
        "suppress_unstable_features_warning": True,
    }
    for name, spec in settings.get("mcp_servers", {}).items():
        values.update(
            {
                f"mcp_servers.{name}.command": spec["command"],
                f"mcp_servers.{name}.args": spec["args"],
                f"mcp_servers.{name}.env_vars": list(spec["env"]),
                f"mcp_servers.{name}.default_tools_approval_mode": "approve",
                f"mcp_servers.{name}.tool_timeout_sec": int(
                    env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]
                ),
            }
        )
    effort = condition["effort_resolved"]
    if effort:
        values["model_reasoning_effort"] = effort
    for feature in (
        "plugins",
        "apps",
        "hooks",
        "multi_agent",
        "multi_agent_v2",
        "shell_tool",
        "unified_exec",
        "image_generation",
        "skill_search",
    ):
        values["features." + feature] = False
    for key, value in values.items():
        args += ["-c", key + "=" + json.dumps(value)]
    if env.get("ICLAYOUT_BENCH_RESUME_ID"):
        args += ["resume", env["ICLAYOUT_BENCH_RESUME_ID"]]
    return args + ["-"]


def session_id(output, state):
    paths = sorted(output.glob("launch-*-harness.jsonl"), key=lambda p: int(p.name.split("-")[1]))
    paths += [output / "harness.jsonl"]
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "thread.started":
                return event.get("thread_id")
    return None
