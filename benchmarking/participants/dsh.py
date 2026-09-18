"""DSH headless profile adapter; invocation overlays never edit user settings."""
import os
import subprocess
import sys
from pathlib import Path

import yaml


class ConfigLoader(yaml.SafeLoader):
    """Read composed metadata without executing Cordis !!js expressions."""


ConfigLoader.add_multi_constructor(
    "tag:yaml.org,2002:js", lambda loader, tag, node: loader.construct_scalar(node)
)


def entries(tree):
    if isinstance(tree, list):
        for item in tree:
            yield from entries(item)
    elif isinstance(tree, dict):
        if "id" in tree:
            yield tree
        for key, value in tree.items():
            if key != "config":
                yield from entries(value)


def configuration():
    raw = subprocess.check_output(["dsh", "--profile", "headless", "--dump-config"], text=True, timeout=30)
    rows = list(entries(yaml.load(raw, Loader=ConfigLoader)))
    home = Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh")))
    path = home / "settings.yaml"
    settings = yaml.safe_load(path.read_text()) if path.exists() else {}
    base = next((r.get("config", {}) for r in rows if r["id"] == "agent-default-model"), {})
    selection = dict(base, **(settings or {}).get("agent-default-model", {}))
    return rows, settings or {}, selection


def resolve_dsh(model, effort):
    rows, settings, selected = configuration()
    model = model or selected.get("model")
    provider = selected.get("provider")
    resolved, source = effort, "experiment"
    if effort is None:
        resolved = selected.get("reasoningEffort")
        source = "dsh saved selection" if resolved else "dsh/provider default (unresolved)"
        if resolved is None and provider == "deepseek-official":
            adapter = next((r.get("config", {}) for r in rows if r["id"] == "llm-deepseek"), {})
            resolved = adapter.get("reasoningEffort")
            if resolved:
                source = "dsh adapter configuration"
    if provider == "deepseek-official" and resolved is not None and resolved not in {"off", "low", "high", "max"}:
        raise ValueError("Installed DSH DeepSeek adapter accepts off, low, high or max")
    if not provider or not model:
        raise ValueError("DSH needs a configured default provider and model")
    # Settings may contain credentials. Kept in memory and a protected temporary file only.
    return {"harness": "dsh", "provider": provider, "model": model, "effort_requested": effort,
            "effort_resolved": resolved, "effort_source": source, "provider_effective_effort": None}, {
                "rows": rows, "settings": settings,
            }


def prepare(condition, settings, env, directory, output, bridge, prompt):
    from .runner import save

    selection = {"provider": condition["provider"], "model": condition["model"]}
    if condition["effort_resolved"] is not None:
        selection["reasoningEffort"] = condition["effort_resolved"]
    saved = {k: v for k, v in settings["settings"].items() if k.startswith("llm-")}
    saved["agent-default-model"] = selection
    settings_path = directory / "dsh-settings.json"
    save(settings_path, saved)
    patch = []
    for row in settings["rows"]:
        name = row["id"]
        if name.startswith(("tool-", "mcp-")) or name in {
            "agent-instructions", "skill-filesystem", "session-title-llm", "session-log-deepseek",
        }:
            patch.append({"id": name, "disabled": True})
    patch += [
        {"id": "settings", "config": {"path": str(settings_path), "watch": False}},
        {"id": "tools", "config": {"mode": "native"}},
        {"id": "session-telemetry-otel", "config": {"mode": "DISABLED"}},
        {"id": "session-persistence-jsonl", "config": {"root": str(output / "dsh-sessions")}},
        {"insert": [{"id": "mcp-layout", "name": "@deepseek-ai/dsh-mcp-client", "config": {
            "serverName": "layout", "transport": "stdio", "command": sys.executable,
            "args": ["-I", str(bridge)], "toolCallTimeoutMs": int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]) * 1000, "failOnStartupError": True,
            "env": {k: v for k, v in env.items() if k.startswith("ICLAYOUT_BENCH_")},
        }}]},
    ]
    for name, spec in settings.get("mcp_servers", {}).items():
        patch.append({"insert": [{"id": "mcp-" + name, "name": "@deepseek-ai/dsh-mcp-client", "config": {
            "serverName": name, "transport": "stdio", **spec,
            "toolCallTimeoutMs": int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]) * 1000,
            "failOnStartupError": True,
        }}]})
    path = directory / "dsh.patch.json"
    save(path, patch)  # JSON is a YAML subset accepted by the Cordis patch loader.
    return ["dsh", "--profile", "headless", "--patch", str(path), prompt]
