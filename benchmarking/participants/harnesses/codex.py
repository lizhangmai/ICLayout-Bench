"""Codex configuration and isolated command construction."""

import json
import math
import re
import sys
import threading
import tomllib
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from benchmarking.participants.harnesses.contracts import (
    EFFORTS,
    HarnessMetadata,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.events import (
    CAPACITY_CODES,
    ErrorEvidence,
    classify_evidence,
    failure,
    read_events,
)
from benchmarking.participants.harnesses.records import (
    confined_files,
    json_events,
    native_records,
    records,
    traces,
)
from benchmarking.results.usage import UsageEvidence, number, request_record

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
        "workspace-write",
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
            "ICLAYOUT_BENCH_INSTRUCTIONS_FILE",
        ],
        "mcp_servers.layout.tool_timeout_sec": int(
            env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]
        ),
        "features.skip_host_skill_discovery": True,
        "suppress_unstable_features_warning": True,
    })
    if env.get("ICLAYOUT_BENCH_USAGE_ENDPOINT"):
        values.update({"otel.exporter.otlp-http.endpoint": env["ICLAYOUT_BENCH_USAGE_ENDPOINT"],
                       "otel.exporter.otlp-http.protocol": "json",
                       "otel.log_user_prompt": False, "otel.metrics_exporter": "none"})
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
    result = traces(Path(output) / '.private/native-home', 'codex', 'sessions/**/*.jsonl', 'log/*.log')
    timing = Path(output) / "codex-telemetry.jsonl"
    if timing.is_file():
        result["codex/telemetry.jsonl"] = timing.read_bytes()
    return result


CAPACITY_MESSAGE = "Selected model is at capacity. Please try a different model."

RECONNECT_MESSAGE = re.compile(
    r"Reconnecting\.\.\. (?:[1-9][0-9]*/[1-9][0-9]* \("
    r"(?:stream disconnected before completion: [^\r\n]+|request timed out|"
    r"workspace routing discovery timed out|unexpected status 503 Service Unavailable: "
    r"upstream connect error[^\r\n]*)\)|"
    r"waiting for network \(Connection failed: error sending request\))")


def usage(agent, native):
    evidence = UsageEvidence()
    for name, events in native_records(native, "codex"):
        model = None
        precise = any(e.get("type") == "token_usage_record" for e in events)
        events = records(native[name])
        previous_total = None
        for index, event in enumerate(events):
            payload = event.get("payload") or {}
            if event.get("type") == "turn_context":
                model = payload.get("model")
            if precise:
                if event.get("type") != "token_usage_record":
                    continue
                value = payload.get("usage") or {}
                identifier = payload.get("response_id") or f"{name}:{index}"
            else:
                info = payload.get("info") or {}
                if payload.get("type") != "token_count" or not info.get("last_token_usage"):
                    continue
                total = info.get("total_token_usage")
                if total == previous_total:
                    continue
                previous_total = total
                value = info["last_token_usage"]
                identifier = f"{name}:{index}"
            ms = number(payload.get("duration_ms"))
            evidence.requests.append(request_record(identifier, payload.get("model", model),
                input_tokens=value.get("input_tokens"), cached=value.get("cached_input_tokens", 0),
                written=value.get("cache_write_input_tokens", 0), output=value.get("output_tokens"),
                reasoning=value.get("reasoning_output_tokens"), seconds=ms / 1000 if ms is not None else None,
                cost=value.get("cost"), source=name))
    if not evidence.requests:
        for index, event in enumerate(records(agent)):
            if event.get("type") != "turn.completed" or not isinstance(event.get("usage"), dict):
                continue
            value = event["usage"]
            evidence.requests.append(request_record(f"stdout:{index}", event.get("model"),
                input_tokens=value.get("input_tokens"), cached=value.get("cached_input_tokens", 0),
                written=value.get("cache_write_input_tokens", 0), output=value.get("output_tokens"),
                reasoning=value.get("reasoning_output_tokens"), cost=value.get("cost"),
                source="agent.jsonl", scope="session"))
    timings = list(records(native.get("codex/telemetry.jsonl", b"")))
    values = []
    for event in timings:
        if event.get("event") in {"codex.api_request", "codex.sse_event", "codex.websocket_request", "codex.websocket_event"}:
            try:
                value = number(float(event.get("duration_ms")))
            except (TypeError, ValueError):
                value = None
            if value is not None:
                values.append(value)
    if values:
        evidence.api_seconds = sum(values) / 1000
    return evidence


def native_error(event):
    detail = event.get("error", {})
    explicit = [event.get("code")]
    if isinstance(detail, dict):
        explicit.append(detail.get("code") or detail.get("type"))
    explicit = [code for code in explicit if code is not None]
    message = event.get("message") or (detail.get("message") if isinstance(detail, dict) else None)
    codes = explicit or [None]
    if event.get("type") in {"error", "turn.failed"} and not explicit and message == CAPACITY_MESSAGE:
        codes = ["model_at_capacity"]
    if (event.get('type') in {'error', 'turn.failed'} and not explicit
            and isinstance(message, str)
            and re.fullmatch(r'unexpected status 401 Unauthorized: [^\r\n]+, url: https?://[^\s]+', message)):
        codes = ['authentication_error']
    return codes, explicit, message, detail


def harness_failure(output, exit_code=None, timed_out=False):
    """Only structured error events count; free-form model text is not evidence."""
    if timed_out:
        return failure("budget_exhausted", "deadline")
    codes = []
    reconnect_codes = []
    in_turn = False
    tool_errors = {}
    retry_after = None
    for event in read_events(output):
        kind = event.get("type")
        event_codes, explicit, message, detail = native_error(event)
        if kind in {"thread.started", "turn.started", "turn.failed", "turn.completed"}:
            # Recovery belongs only to this turn, never to a later successful one.
            completed = kind == "turn.completed" and in_turn and exit_code == 0
            # A definitive capacity response ends this same native reconnect loop.
            # Earlier turns, unknown errors, fatal codes and MCP failures stay intact.
            capacity_terminal = (kind == "turn.failed" and in_turn and exit_code is not None
                                 and exit_code > 0 and all(isinstance(code, str) and code in CAPACITY_CODES
                                                          for code in event_codes))
            if not (completed or capacity_terminal):
                codes.extend(reconnect_codes)
            reconnect_codes.clear()
            in_turn = kind == "turn.started"
        item = event.get("item")
        if (event.get("type") == "item.completed" and isinstance(item, dict)
                and item.get("type") == "mcp_tool_call" and item.get("server") == "layout"):
            tool = item.get("tool")
            detail = item.get("error")
            if isinstance(tool, str):
                if item.get("status") == "completed":
                    tool_errors.pop(tool, None)
                elif item.get("status") == "failed" and isinstance(detail, dict):
                    tool_errors[tool] = detail.get("message")
        if kind in {"error", "turn.failed"} or event.get("is_error") is True:
            hint = event.get("retry_after", detail.get("retry_after") if isinstance(detail, dict) else None)
            if type(hint) in (int, float) and math.isfinite(hint) and hint >= 0:
                retry_after = max(retry_after or 0, hint)
            # Codex emits these native error events during its own reconnect loop.
            # Never infer recovery from assistant text or arbitrary error messages.
            connection = (all(code == "connection_error" for code in explicit) if explicit else
                          isinstance(message, str) and RECONNECT_MESSAGE.fullmatch(message) is not None)
            capacity = all(isinstance(code, str) and code in CAPACITY_CODES for code in event_codes)
            target = reconnect_codes if kind == "error" and in_turn and (connection or capacity) and event.get("is_error") is not True else codes
            target.extend(event_codes)
    codes.extend(reconnect_codes)
    tool_failure = None
    # These native layout MCP error fields belong to Codex's event protocol.
    if any(message == "MCP tool call requires approval, but approval policy is never"
           for message in tool_errors.values()):
        tool_failure = failure("harness_configuration", "harness_tool_event", "mcp_approval_required")
    elif tool_errors:
        tool_failure = failure("unknown", "harness_tool_event", "mcp_tool_call_failed")
    return classify_evidence(ErrorEvidence(tuple(codes), retry_after, tool_failure), exit_code, timed_out)


IDENTIFIERS = {"event.name", "event_name", "event.kind", "event_kind", "model", "model_name",
               "response_id", "response.id", "request_id", "request.id"}


def _value(value):
    if not isinstance(value, dict):
        return None
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    return None


def timing_records(payload):
    for resource in payload.get("resourceLogs", []):
        for scope in resource.get("scopeLogs", []):
            for record in scope.get("logRecords", []):
                attributes = {a["key"]: _value(a.get("value")) for a in record.get("attributes", []) if "key" in a}
                name = attributes.get("event.name") or attributes.get("event_name") or _value(record.get("body"))
                if name not in {"codex.api_request", "codex.sse_event", "codex.websocket_request", "codex.websocket_event"}:
                    continue
                # The upstream exporter may include prompt text and provider errors.
                # Only known identifiers and numeric timing/counter fields survive.
                fields = {key: value for key, value in attributes.items() if key in IDENTIFIERS
                          or (key.endswith(("duration_ms", "latency_ms", "tokens"))
                              and isinstance(value, (int, float, str))
                              and str(value).replace(".", "", 1).isdigit())}
                yield {"event": name, "time_unix_nano": record.get("timeUnixNano"),
                       "observed_time_unix_nano": record.get("observedTimeUnixNano"), **fields}


@contextmanager
def observe(output, env):
    path = output / "codex-telemetry.jsonl"
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= 8 * 1024 * 1024:
                    raise ValueError("Oversized telemetry")
                payload = json.loads(self.rfile.read(length))
                rows = list(timing_records(payload))
                with lock, path.open("a", encoding="utf-8") as stream:
                    for row in rows:
                        stream.write(json.dumps(row) + "\n")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
            except (ValueError, TypeError, KeyError):
                self.send_error(400)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env["ICLAYOUT_BENCH_USAGE_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v1/logs"
    original = {key: env.get(key) for key in ('NO_PROXY', 'no_proxy')}
    bypass = dict.fromkeys([entry.strip() for value in original.values() if value
                           for entry in value.split(',') if entry.strip()] + ['127.0.0.1', 'localhost'])
    env.update(NO_PROXY=','.join(bypass), no_proxy=','.join(bypass))
    try:
        yield
    finally:
        env.pop("ICLAYOUT_BENCH_USAGE_ENDPOINT", None)
        for key, value in original.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

observe_usage = observe
