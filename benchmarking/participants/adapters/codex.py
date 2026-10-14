"""Codex configuration and isolated command construction."""

import json
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from . import codex_events
from .contracts import EFFORTS, HarnessMetadata, LaunchContext, ParticipantSelection
from .native import confined_files, json_events, traces

METADATA = HarnessMetadata('codex', 'CODEX_HOME', '.codex', 'auth.json', 'config.toml')

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}

CONNECTION_FIELDS = {"model_provider", "model_providers", "cli_auth_credentials_store",
                     "forced_login_method", "forced_chatgpt_workspace_id", "chatgpt_base_url"}
PROVIDER_FIELDS = {"name", "base_url", "env_key", "wire_api", "requires_openai_auth",
                   "env_http_headers", "request_max_retries", "stream_max_retries",
                   "stream_idle_timeout_ms", "supports_websockets"}
AUTH_ENVIRONMENT = {"CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                    "OPENAI_ORG_ID", "OPENAI_PROJECT_ID", "OPENAI_FEDERATION_RULE_ID",
                    "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT"}


def _connection(config, env, home):
    unknown = config.keys() - CONNECTION_FIELDS
    if unknown:
        raise ValueError("Codex experiment config accepts connection settings only; unsupported fields: "
                         + ", ".join(sorted(unknown)))
    if config.get("cli_auth_credentials_store", "file") != "file":
        raise ValueError("Codex experiment homes require file credential storage")
    config = dict(config, cli_auth_credentials_store="file")
    provider = config.get("model_provider", "openai")
    definitions = config.get("model_providers", {})
    if not isinstance(definitions, dict) or not isinstance(provider, str):
        raise TypeError("Codex model_provider and model_providers are malformed")
    spec = definitions.get(provider, {})
    if provider not in {"openai", "ollama", "lmstudio"} and not spec:
        raise ValueError("Selected Codex model provider is not configured")
    if definitions:
        if not isinstance(spec, dict) or spec.keys() - PROVIDER_FIELDS:
            raise ValueError("Codex provider accepts declared connection settings only")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", provider):
            raise ValueError("Codex provider ID must use letters, digits, underscores or hyphens")
        config["model_providers"] = {provider: spec}
    for url in (config.get("chatgpt_base_url"), spec.get("base_url")):
        if url is not None:
            if not isinstance(url, str):
                raise ValueError("Codex endpoint must be an HTTP(S) URL")
            parsed = urlsplit(url)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ValueError("Codex endpoint must be an HTTP(S) URL without credentials, query or fragment")
    native_auth = spec.get("requires_openai_auth", provider == "openai")
    if not isinstance(native_auth, bool):
        raise TypeError("Codex requires_openai_auth must be a boolean")
    headers = spec.get("env_http_headers", {})
    if not isinstance(headers, dict) or any(not isinstance(value, str) for value in headers.values()):
        raise TypeError("Codex env_http_headers must map header names to environment variable names")
    refs = set(headers.values())
    if not native_auth and spec.get("env_key"):
        refs.add(spec["env_key"])
    if any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in refs):
        raise ValueError("Codex provider credential references must name environment variables")
    if any(key.startswith(("ICLAYOUT_BENCH_", "LAYOUT_BENCH_")) or key in {"CODEX_HOME", "PYTHONPATH"} for key in refs):
        raise ValueError("Codex provider cannot use session controls as credential references")
    if missing := refs - env.keys():
        raise ValueError("Missing declared Codex provider environment variables: " + ", ".join(sorted(missing)))
    declared = {key: env[key] for key in refs}
    for key in AUTH_ENVIRONMENT:
        env.pop(key, None)
    env.update(declared)
    credentials = [{"api_key": value} for value in declared.values()]
    files = []
    if native_auth:
        path = home / "auth.json"
        if not path.is_file() or path.is_symlink():
            raise ValueError("Codex authentication file is missing or not regular: " + str(path))
        try:
            auth = json.loads(path.read_bytes())
        except (ValueError, UnicodeError):
            raise ValueError("Codex authentication file must contain valid JSON") from None
        if not isinstance(auth, dict):
            raise ValueError("Codex authentication file must contain an object")
        native_mode = auth.get("auth_mode")
        if native_mode == "chatgpt":
            method = "chatgpt" if auth.get("tokens") else None
        elif native_mode in {"apikey", "api_key"}:
            method = "api" if auth.get("OPENAI_API_KEY") else None
        elif native_mode is None:
            method = "api" if auth.get("OPENAI_API_KEY") else "chatgpt" if auth.get("tokens") else None
        else:
            raise ValueError("Codex experiment home supports ChatGPT or API-key native authentication")
        if method is None:
            raise ValueError("Codex authentication file needs an API key or ChatGPT tokens")
        if config.get("forced_login_method", method) != method:
            raise ValueError("Codex authentication does not match forced_login_method")
        credentials.append(auth)
        files = ["auth.json"]
    else:
        method = "api" if spec.get("env_key") else "none"
    return config, provider, method, credentials, files


def _connection_values(config):
    for key, value in config.items():
        if key != "model_providers":
            yield key, value
            continue
        for provider, spec in value.items():
            for field, item in spec.items():
                prefix = "model_providers." + provider + "." + field
                if isinstance(item, dict):
                    for name, ref in item.items():
                        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                            raise ValueError("Codex provider header name is unsupported")
                        yield prefix + "." + name, ref
                else:
                    yield prefix, item


def harness_failure(output, exit_code=None, timed_out=False):
    return codex_events.harness_failure(output, exit_code, timed_out)


def resolve(model, effort, env, *, home=None):
    path = Path(env.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    try:
        settings = tomllib.loads(path.read_text()) if path.exists() else {}
    except (ValueError, UnicodeError):
        raise ValueError("Codex config.toml is malformed") from None
    launch_settings = {}
    if home is not None:
        settings, provider, method, credentials, files = _connection(settings, env, home)
        launch_settings = {"codex_connection": settings, "credential_fields": credentials,
                           "credential_files": files}
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
    if home is not None:
        condition.update(provider=provider, auth_method=method, connection=settings)
    return ParticipantSelection(condition, env, launch_settings)


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
    values = dict(_connection_values(settings.get("codex_connection", {})))
    values.update({
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
    })
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
        if _session(context.output, env['ICLAYOUT_BENCH_RESUME_ID']) is None:
            raise ValueError('Codex native session is missing or ambiguous; refusing a new session')
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
                native_id = event.get('thread_id')
                return native_id if _session(output, native_id) is not None else None
    return None


def _session(output, native_id):
    home = Path(output) / '.private/native-home'
    cwd = str((home.parent / 'workspace').resolve())
    found = []
    for path in confined_files(home, 'sessions/**/*.jsonl'):
        event = next(json_events(path), {})
        payload = event.get('payload')
        if (event.get('type') == 'session_meta' and isinstance(payload, dict)
                and isinstance(native_id, str) and payload.get('id') == native_id
                and payload.get('cwd') == cwd):
            found.append(path)
    return found[0] if len(found) == 1 else None


def native_traces(output):
    return traces(Path(output) / '.private/native-home', 'codex',
                  'sessions/**/*.jsonl', 'log/*.log')
