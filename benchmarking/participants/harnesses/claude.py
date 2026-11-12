"""Claude Code configuration and isolated command construction."""

import json
import re
import uuid
from pathlib import Path

from benchmarking.participants.harnesses.contracts import (
    EFFORTS,
    HarnessMetadata,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.events import (
    ErrorEvidence,
    classify_evidence,
    structured_errors,
)
from benchmarking.participants.harnesses.records import (
    confined_files,
    json_events,
    native_records,
    records,
    traces,
)
from benchmarking.results.usage import UsageEvidence, number, request_record

METADATA = HarnessMetadata('claude', 'CLAUDE_CONFIG_DIR', '.claude', '.credentials.json', 'settings.json')

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}


def resolve(model, effort, env, *, home=None):
    path = Path(env.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "settings.json"
    settings = json.loads(path.read_text()) if path.exists() else {}
    provider_env = {
        key: value
        for key, value in settings.get("env", {}).items()
        if key.startswith("ANTHROPIC_")
        or key
        in {
            "CLAUDE_CODE_EFFORT_LEVEL",
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
            "MAX_THINKING_TOKENS",
            "API_TIMEOUT_MS",
        }
    }
    if home is not None:
        for key in list(env):
            if key.startswith(("ANTHROPIC_", "CLAUDE_")) and key != METADATA.home_environment:
                del env[key]
        if (not (home / METADATA.credential_file).is_file() and not settings.get("apiKeyHelper")
                and not any(provider_env.get(key) for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))):
            raise ValueError("Claude experiment home needs native credentials or configured API authentication")
    env.update(provider_env)
    _add_proxy_exceptions(settings.get("env", {}), env)
    model = model or env.get("ANTHROPIC_MODEL") or settings.get("model")
    resolved_effort = effort
    source = "experiment" if effort is not None else "harness default (unresolved)"
    if effort is None:
        resolved_effort = env.get("CLAUDE_CODE_EFFORT_LEVEL") or settings.get(
            "effortLevel"
        )
        if resolved_effort:
            source = "claude provider environment/settings"
    if resolved_effort:
        env["CLAUDE_CODE_EFFORT_LEVEL"] = resolved_effort
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Supply --model or configure a default model in the selected harness")
    if resolved_effort is not None and resolved_effort not in EFFORTS:
        raise ValueError("Unsupported effort value; use an effort accepted by your CLI/model")
    cli_settings = {"disableAllHooks": True}
    if settings.get("apiKeyHelper"):
        cli_settings["apiKeyHelper"] = settings["apiKeyHelper"]
    condition = {
        "harness": "claude-code",
        "model": model,
        "effort_requested": effort,
        "effort_resolved": resolved_effort,
        "effort_source": source,
        "provider_effective_effort": None,
    }
    if home is not None:
        condition["auth_method"] = "api" if settings.get("apiKeyHelper") or any(
            provider_env.get(key) for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")) else "subscription"
        cli_settings["credential_files"] = [METADATA.credential_file] if condition["auth_method"] == "subscription" else []
    return ParticipantSelection(condition, env, cli_settings)


def _add_proxy_exceptions(declared, env):
    """Add the profile's direct-connection hosts to the inherited proxy exceptions."""
    values = [declared[key] for key in ("NO_PROXY", "no_proxy") if key in declared]
    if not values:
        return
    if any(not isinstance(value, str) or not value.strip(" ,") for value in values):
        raise ValueError("Claude settings NO_PROXY must list at least one host")
    inherited = [env[key] for key in ("NO_PROXY", "no_proxy") if env.get(key)]
    entries = dict.fromkeys(entry.strip() for value in inherited + values
                            for entry in value.split(",") if entry.strip())
    env.update(NO_PROXY=",".join(entries), no_proxy=",".join(entries))


def prepare(context: LaunchContext) -> list[str]:
    condition = context.selection.condition
    env = context.selection.environment
    settings = context.selection.settings
    mcp = context.mcp
    debug = context.output / '.private/native-home/debug'
    debug.mkdir(parents=True, mode=0o700, exist_ok=True)
    args = [
        "claude",
        "-p",
        "--model",
        condition["model"],
        "--setting-sources",
        "",
        "--settings",
        json.dumps({key: settings[key] for key in ("disableAllHooks", "apiKeyHelper") if key in settings}),
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp),
        "--disable-slash-commands",
        "--tools",
        "",
        "--allowedTools",
        ",".join(
            "mcp__" + name for name in dict.fromkeys(["layout", *settings.get("mcp_servers", {})])
        ),
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "--debug-file",
        str(debug / (uuid.uuid4().hex + '.log')),
    ]
    # Omitting effort preserves the resolved user environment, not a common default.
    if condition["effort_requested"] is not None:
        args += ["--effort", condition["effort_resolved"]]
    if env.get("ICLAYOUT_BENCH_RESUME_ID"):
        if _session(context.output, env['ICLAYOUT_BENCH_RESUME_ID']) is None:
            raise ValueError('Claude Code native session is missing or ambiguous; refusing a new session')
        args += ["--resume", env["ICLAYOUT_BENCH_RESUME_ID"]]
    elif env.get("ICLAYOUT_BENCH_NATIVE_ID"):
        args += ["--session-id", env["ICLAYOUT_BENCH_NATIVE_ID"]]
    return args


def _session(output, native_id):
    if not isinstance(native_id, str) or not native_id or '/' in native_id or '\\' in native_id:
        return None
    home = Path(output) / '.private/native-home'
    cwd = str((home.parent / 'workspace').resolve())
    found = []
    for path in confined_files(home, 'projects/*/*.jsonl'):
        if path.stem != native_id:
            continue
        records = [e for e in json_events(path) if e.get('type') in {'user', 'assistant'}]
        if records and all(e.get('sessionId') == native_id and e.get('cwd') == cwd
                           and e.get('isSidechain') is False for e in records):
            found.append(path)
    return found[0] if len(found) == 1 else None


def session_id(output, state):
    return state.native_id if _session(output, state.native_id) is not None else None


def native_traces(output):
    return traces(Path(output) / '.private/native-home', 'claude',
                  'projects/*/*.jsonl', 'projects/*/*/subagents/*.jsonl', 'debug/*.log')


def usage(agent, native):
    evidence = UsageEvidence()
    # Since 2.1.277, resumed calls restore session totals. Read the latest
    # result per session rather than adding the restored spend repeatedly.
    results = {}
    for event in records(agent):
        if event.get("type") == "result":
            if event.get("subtype") == "error_during_execution" and not event.get("modelUsage"):
                continue
            results[event.get("session_id", "session")] = event
    costs = [number(e.get("total_cost_usd")) if all(v.get("costBasis") != "unknown"
             for v in (e.get("modelUsage") or {}).values()) else None for e in results.values()]
    times = [number(e.get("duration_api_ms")) for e in results.values()]
    if costs and all(v is not None for v in costs):
        evidence.reported_cost = sum(costs)
    if times and all(v is not None for v in times):
        evidence.api_seconds = sum(times) / 1000
    for session, event in results.items():
        for model, value in (event.get("modelUsage") or {}).items():
            record = request_record(f"{session}:{model}", model, uncached=value.get("inputTokens"),
                cached=value.get("cacheReadInputTokens", 0), written=value.get("cacheCreationInputTokens", 0),
                output=value.get("outputTokens"),
                reasoning=value.get("thinkingTokens"),
                cost=value.get("costUSD") if value.get("costBasis") != "unknown" else None,
                source="agent.jsonl:modelUsage", scope="session")
            record["cost_source"] = "harness_reported" if record["cost"] is not None else None
            evidence.requests.append(record)
    if evidence.requests:
        return evidence
    sources = list(native_records(native, "claude")) + [("agent.jsonl", records(agent))]
    for name, events in sources:
        for index, event in enumerate(events):
            if event.get("type") != "assistant" or event.get("error"):
                continue
            message = event.get("message") or {}
            value = message.get("usage") or {}
            # Split assistant content blocks repeat the same provider message ID.
            identifier = message.get("id") or event.get("requestId") or f"{name}:{index}"
            evidence.requests.append(request_record(identifier, message.get("model"),
                uncached=value.get("input_tokens"), cached=value.get("cache_read_input_tokens", 0),
                written=value.get("cache_creation_input_tokens", 0),
                reasoning=(value.get("output_tokens_details") or {}).get("reasoning_tokens"),
                cost=value.get("cost"), source=name))
    if results:
        evidence.requests.clear()
        for identifier, event in results.items():
            value = event.get("usage") or {}
            evidence.requests.append(request_record(identifier, event.get("model"),
                uncached=value.get("input_tokens"), cached=value.get("cache_read_input_tokens", 0),
                written=value.get("cache_creation_input_tokens", 0), output=value.get("output_tokens"),
                source="agent.jsonl", scope="session"))
    return evidence


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, True)
    events = list(json_events(output / 'harness.jsonl'))
    # Native retries and errors recovered within a successful turn are diagnostic.
    results = [e for e in events if e.get('type') == 'result']
    if not exit_code and results and results[-1].get('is_error') is False:
        return classify_evidence(structured_errors(events), exit_code)
    codes = []
    native_messages = []
    for event in events:
        if event.get('type') != 'assistant' or 'error' not in event:
            continue
        native_code = event['error']
        code = {'authentication_failed': 'authentication_error',
                'billing_error': 'billing_error', 'rate_limit': 'rate_limit_error'}.get(native_code) if isinstance(native_code, str) else None
        message = event.get('message')
        content = message.get('content', []) if isinstance(message, dict) else []
        text = ''.join(item.get('text', '') for item in content
                       if isinstance(item, dict) and item.get('type') == 'text'
                       and isinstance(item.get('text'), str)) if isinstance(content, list) else ''
        native_messages.append(text)
        if (event['error'] == 'server_error' and isinstance(content, list)
                and any(isinstance(item, dict) and item.get('type') == 'text'
                        and isinstance(item.get('text'), str)
                        and re.match(r'^API Error: 529(?:\s|$)', item['text']) for item in content)):
            code = 'server_overloaded'
        codes.append(code)
    # The result repeats the assistant error without a code. Preserve unknown
    # structured failures, but don't let that redundant marker hide HTTP 529.
    redundant = (results[-1] if native_messages and results
                 and results[-1].get('subtype') == 'success'
                 and results[-1].get('is_error') is True
                 and results[-1].get('result') == native_messages[-1] else None)
    evidence = structured_errors(event for event in events if event is not redundant)
    return classify_evidence(ErrorEvidence(tuple(codes) + evidence.codes, evidence.retry_after), exit_code)
