"""Kimi Code print-mode adapter with an isolated home and MCP-only tools."""
import copy
import json
import tomllib
from pathlib import Path

import tomli_w
import yaml

from benchmarking.files import atomic_write

from .contracts import HarnessMetadata, LaunchContext, ParticipantSelection

METADATA = HarnessMetadata('kimi', 'KIMI_CODE_HOME', '.kimi-code', None)

CAPABILITIES = {"resume_session": False, "capacity_resumes": False}


def resolve(model, effort, env):
    home = Path(env.get("KIMI_CODE_HOME", str(Path.home() / ".kimi-code")))
    config = tomllib.loads((home / "config.toml").read_text())
    model = model or config.get("default_model")
    entry = copy.deepcopy(config.get("models", {}).get(model))
    if not entry:
        raise ValueError("Kimi Code model alias is not configured: " + str(model))
    entry.update(entry.pop("overrides", {}))
    provider = entry["provider"]
    connection = copy.deepcopy(config.get("providers", {}).get(provider))
    if not connection:
        raise ValueError("Kimi Code model provider is not configured")
    resolved = effort or config.get("thinking", {}).get("effort") or entry.get("default_effort")
    if resolved not in entry.get("support_efforts", []):
        raise ValueError("Kimi Code effort must be explicitly supported by the selected model")
    entry["overrides"] = {"default_effort": resolved,
                          "support_efforts": entry["support_efforts"]}
    credentials = {}
    oauth = connection.get("oauth")
    if oauth:
        key = oauth.get("key", "")
        path = (home / key).resolve()
        if oauth.get("storage") != "file" or not key or not path.is_relative_to(home.resolve()):
            raise ValueError("Kimi Code adapter requires a home-relative file OAuth credential")
        credentials[key] = path.read_bytes()
    credential_fields = []
    for raw in credentials.values():
        try:
            credential_fields.append(json.loads(raw))
        except ValueError:
            try:
                credential_fields.append(tomllib.loads(raw.decode()))
            except (ValueError, UnicodeError):
                pass  # The native CLI owns opaque credential formats.
    settings = {"credential_fields": credential_fields, "config": {"default_model": model, "providers": {provider: connection},
                           "models": {model: entry}}, "credentials": credentials}
    condition = {"harness": "kimi-code", "model": model, "provider": provider,
            "effort_requested": effort, "effort_resolved": resolved,
            "effort_source": "experiment" if effort else "kimi configuration",
            "provider_effective_effort": None}
    return ParticipantSelection(condition, env, settings)


def prepare(context: LaunchContext) -> list[str]:
    condition = context.selection.condition
    env = context.selection.environment
    settings = context.selection.settings
    directory, mcp, prompt = context.directory, context.mcp, context.prompt
    from benchmarking.files import write_json as save

    home = directory.parent / "kimi-home"
    home.mkdir(mode=0o700, exist_ok=True)
    for key, raw in settings["credentials"].items():
        target = home / key
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        atomic_write(target, raw)
    # Host overrides must not change the frozen model, effort or tool environment.
    credential_env = {v["api_key_env"]: env[v["api_key_env"]]
                      for v in settings["config"]["providers"].values()
                      if v.get("api_key_env") in env}
    for key in list(env):
        if key.startswith(("KIMI_", "KIMI_CODE_")):
            del env[key]
    env.update(credential_env)
    env.update(KIMI_CODE_HOME=str(home.resolve()), KIMI_DISABLE_TELEMETRY="1")
    tools = ["mcp__" + name + "__*" for name in ["layout", *settings.get("mcp_servers", {})]]
    config = copy.deepcopy(settings["config"])
    config.update(thinking={"enabled": True, "effort": condition["effort_resolved"]},
                  telemetry=False, builtin_product_skills=False, merge_all_available_skills=False,
                  tools={"enabled": tools}, watch={"enabled": False},
                  permission={"rules": [{"decision": "allow", "pattern": name} for name in tools]})
    atomic_write(home / "config.toml", tomli_w.dumps(config).encode())
    atomic_write(home / "tui.toml", b'[upgrade]\nauto_install = false\n')
    servers = json.loads(mcp.read_text())
    for spec in servers["mcpServers"].values():
        spec["toolTimeoutMs"] = int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]) * 1000
    save(home / "mcp.json", servers)
    skills = home / "empty-skills"
    skills.mkdir(exist_ok=True)
    agent = directory / "participant.md"
    frontmatter = {"name": "layout-participant", "description": "ICLayout-Bench participant",
                   "tools": tools, "subagents": []}
    agent.write_text("---\n" + yaml.safe_dump(frontmatter) + "---\n"
                     "Use the supplied task contract and the evaluation MCP tools to complete the layout.\n")
    return ["kimi", "--model", condition["model"], "--agent-file", str(agent),
            "--skills-dir", str(skills), "--output-format", "stream-json", "--prompt", prompt]
