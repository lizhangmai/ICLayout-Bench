"""Resolve experiment conditions without persisting provider credentials."""
import hashlib
import importlib.metadata
import json
import os
import re
import tomllib
from pathlib import Path

HARNESSES = ("codex", "claude-code", "dsh", "command")
EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
FIELDS = {"name", "harness", "model", "effort", "tasks", "concurrency", "repetitions", "recovery", "results_data", "scheme"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("ICLAYOUT_BENCH_", "LAYOUT_BENCH_")) and k != "PYTHONPATH"}


def resolve(harness, model=None, effort=None):
    if harness not in HARNESSES:
        raise ValueError("Unknown harness")
    env = clean_env()
    if harness == "command":
        return {"harness": harness, "model": model, "effort_requested": effort, "effort_resolved": effort}, env, {}
    if harness == "dsh":
        from .dsh import resolve_dsh
        condition, settings = resolve_dsh(model, effort)
        return condition, env, settings
    source = "experiment" if effort is not None else "harness default (unresolved)"
    settings = {}
    resolved_effort = effort
    if harness == "claude-code":
        path = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "settings.json"
        settings = json.loads(path.read_text()) if path.exists() else {}
        # Reuse provider configuration, not user hooks, plugins or host tools.
        provider_env = {k: v for k, v in settings.get("env", {}).items()
                        if k.startswith("ANTHROPIC_") or k in {
                            "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
                            "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "MAX_THINKING_TOKENS", "API_TIMEOUT_MS",
                        }}
        env.update(provider_env)
        model = model or env.get("ANTHROPIC_MODEL") or settings.get("model")
        if effort is None:
            resolved_effort = env.get("CLAUDE_CODE_EFFORT_LEVEL") or settings.get("effortLevel")
            if resolved_effort:
                source = "claude provider environment/settings"
        if resolved_effort:
            env["CLAUDE_CODE_EFFORT_LEVEL"] = resolved_effort
        cli_settings = {"disableAllHooks": True}
        if settings.get("apiKeyHelper"):
            cli_settings["apiKeyHelper"] = settings["apiKeyHelper"]
    else:
        path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
        settings = tomllib.loads(path.read_text()) if path.exists() else {}
        profile = settings.get("profile")
        effective = dict(settings)
        if profile:
            effective.update(settings.get("profiles", {}).get(profile, {}))
        model = model or effective.get("model")
        if effort is None:
            resolved_effort = effective.get("model_reasoning_effort")
            if resolved_effort:
                source = "codex user configuration"
        cli_settings = {}
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Supply --model or configure a default model in the selected harness")
    if resolved_effort is not None and resolved_effort not in EFFORTS:
        raise ValueError("Unsupported effort value; use an effort accepted by your CLI/model")
    return {"harness": harness, "model": model, "effort_requested": effort,
            "effort_resolved": resolved_effort, "effort_source": source,
            "provider_effective_effort": None}, env, cli_settings


def package_identity():
    dist = importlib.metadata.distribution("iclayout-bench")
    files = {}
    for file in dist.files or []:
        if str(file).startswith("benchmarking/") and file.suffix != ".pyc":
            files[str(file)] = hashlib.sha256(Path(dist.locate_file(file)).read_bytes()).hexdigest()
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    return {"name": dist.metadata["Name"], "version": dist.version, "installed_content_sha256": digest(files),
            "wheel_sha256": direct.get("archive_info", {}).get("hashes", {}).get("sha256")}


def validate(row):
    if set(row) - FIELDS:
        raise ValueError("Unknown experiment fields: " + ", ".join(sorted(set(row) - FIELDS)))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", row.get("name", "")):
        raise ValueError("Experiment name must be a short path-safe identifier")
    if row.get("harness") not in HARNESSES:
        raise ValueError("Each experiment needs a supported harness")
    tasks = row.get("tasks")
    if (not isinstance(tasks, list) or not tasks
            or any(not isinstance(task, str) or not task.strip() for task in tasks)
            or len(set(tasks)) != len(tasks)):
        raise ValueError("tasks must be an explicit nonempty list of distinct case IDs")
    if not isinstance(row.get("model"), str) or not row["model"].strip():
        raise ValueError("Each experiment must explicitly specify a model")
    if row.get("effort") not in (*EFFORTS, "off"):
        raise ValueError("Each experiment must explicitly specify effort (no default)")
    for key in ("repetitions", "concurrency"):
        if type(row.get(key)) is not int or row[key] <= 0:
            raise ValueError(key + " must be explicitly set to a positive integer")
    if "results_data" in row and (not isinstance(row["results_data"], str) or not row["results_data"].strip()):
        raise ValueError("results_data must be a nonempty archive directory")
    from .recovery import policy
    settings = policy(row.get("recovery"))
    if row["harness"] in {"dsh", "command"} and settings["resume_session"]:
        raise ValueError("This harness does not support resume_session")
    return row


def read_matrix(path):
    config = tomllib.loads(Path(path).read_text())
    if (set(config) - {"defaults", "runs"} or not isinstance(config.get("defaults", {}), dict)
            or not isinstance(config.get("runs"), list) or not config["runs"]
            or not all(isinstance(row, dict) for row in config["runs"])):
        raise ValueError("Expected [defaults] and one or more [[runs]] tables")
    rows = [validate(dict(config.get("defaults", {}), **row)) for row in config["runs"]]
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("Experiment names must be unique")
    return [_scheme(row, Path(path).resolve().parent) for row in rows]


def _scheme(row, base):
    from .scheme import resolve_scheme
    if "scheme" in row or row["harness"] == "command":
        row["scheme"] = resolve_scheme(row.get("scheme", {}), base, row["harness"])
    return row


def read_configs(paths):
    """Expand one harness/model per file into independent effort conditions."""
    rows = []
    for path in paths:
        path = Path(path)
        config = tomllib.loads(path.read_text())
        if set(config) - (FIELDS | {"efforts"}):
            raise ValueError("Unknown configuration fields in " + str(path))
        if not isinstance(config.get("model"), str) or not config["model"].strip():
            raise ValueError("Each configuration must specify a model")
        if "effort" in config and "efforts" in config:
            raise ValueError("Use effort or efforts, not both")
        efforts = config.pop("efforts", [config.pop("effort", None)])
        if (not isinstance(efforts, list) or not efforts
                or any(not isinstance(e, str) or e not in (*EFFORTS, "off") for e in efforts)
                or len(set(efforts)) != len(efforts)):
            raise ValueError("efforts must be a nonempty list of distinct effort names")
        name = config.pop("name", path.stem)
        for effort in efforts:
            rows.append(_scheme(validate({**config, "name": f"{name}-{effort}",
                                  "effort": effort}), path.resolve().parent))
    if len({row["name"] for row in rows}) != len(rows):
        raise ValueError("Configuration condition names must be unique")
    return rows
