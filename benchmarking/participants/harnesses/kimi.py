"""Kimi Code print-mode adapter with an isolated home and MCP-only tools."""

import copy
import json
import re
import tomllib
from pathlib import Path

import tomli_w
import yaml

from benchmarking.files import atomic_write
from benchmarking.participants.harnesses.contracts import (
    HarnessMetadata,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.credentials import credential_values
from benchmarking.participants.harnesses.events import (
    ErrorEvidence,
    classify_evidence,
    failure,
    structured_evidence,
)
from benchmarking.participants.harnesses.records import native_records, records
from benchmarking.results.usage import UsageEvidence, duration, number, request_record

METADATA = HarnessMetadata('kimi', 'KIMI_CODE_HOME', '.kimi-code', None, 'config.toml')

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}


def _credential_path(oauth):
    key = oauth.get('key', '')
    name = key.removeprefix('oauth/') if isinstance(key, str) else ''
    if (oauth.get('storage') != 'file' or not name or name.startswith('.')
            or '/' in name or '\\' in name):
        raise ValueError('Kimi Code adapter requires a valid file OAuth token key')
    return Path('credentials') / (name + '.json')


def resolve(model, effort, env, *, home=None):
    home = Path(env.get("KIMI_CODE_HOME", str(Path.home() / ".kimi-code")))
    config = tomllib.loads((home / "config.toml").read_text())
    loop_control = config.get("loop_control", {})
    if not isinstance(loop_control, dict):
        raise TypeError("Kimi Code loop_control must be a table")
    max_attempts = loop_control.get("max_attempts_per_step", 10)
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("Kimi Code max_attempts_per_step must be a positive integer including the initial attempt")
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
        relative = _credential_path(oauth)
        path = (home / relative).resolve()
        if not path.is_relative_to(home.resolve()):
            raise ValueError('Kimi Code OAuth credential must stay inside its home')
        # Native token files are UTF-8 JSON. Keep their exact text JSON-native
        # so coordinator and worker pipes never need a vendor-specific codec.
        credentials[relative.as_posix()] = path.read_text(encoding='utf-8')
    credential_fields = [json.loads(raw) for raw in credentials.values()]
    if connection.get('api_key_env') in env:
        credential_fields.append({'api_key': env[connection['api_key_env']]})
    settings = {"credential_fields": credential_fields, "config": {"default_model": model, "providers": {provider: connection},
                           "models": {model: entry},
                           "loop_control": {"max_attempts_per_step": max_attempts}}, "credentials": credentials,
                "credential_home": str(home.resolve())}
    condition = {"harness": "kimi-code", "model": model, "provider": provider,
            "effort_requested": effort, "effort_resolved": resolved,
            "effort_source": "experiment" if effort else "kimi configuration",
            "provider_effective_effort": None,
            "native_max_attempts_per_step": max_attempts}
    return ParticipantSelection(condition, env, settings)


def prepare(context: LaunchContext) -> list[str]:
    condition = context.selection.condition
    env = context.selection.environment
    settings = context.selection.settings
    directory, mcp, prompt = context.directory, context.mcp, context.prompt
    from benchmarking.files import write_json as save

    home = directory.parent / "kimi-home"
    home.mkdir(mode=0o700, exist_ok=True)
    if settings["credentials"]:
        original = Path(settings["credential_home"])
        # Native atomic token replacement and refresh locks must address the
        # same managed store across cases and other authenticated CLI sessions.
        # Configuration, conversations and tools still use the isolated home.
        for name in ('credentials', 'oauth'):
            source, target = original / name, home / name
            source.mkdir(parents=True, mode=0o700, exist_ok=True)
            if target.is_symlink():
                if target.resolve() != source.resolve():
                    raise ValueError('Kimi Code OAuth storage changed during continuation')
            elif target.exists():
                raise ValueError('Kimi Code OAuth storage must use the managed credential directory')
            else:
                target.symlink_to(source.resolve(), target_is_directory=True)
        (original / 'credentials').chmod(0o700)
        for key in settings["credentials"]:
            path = original / key
            if path.is_file():
                path.chmod(0o600)
    # Host overrides must not change the frozen model, effort or tool environment.
    credential_env = {v["api_key_env"]: env[v["api_key_env"]]
                      for v in settings["config"]["providers"].values()
                      if v.get("api_key_env") in env}
    for key in list(env):
        if key.startswith(("KIMI_", "KIMI_CODE_")):
            del env[key]
    env.update(credential_env)
    env.update(KIMI_CODE_HOME=str(home.resolve()), KIMI_DISABLE_TELEMETRY="1")
    tools = ["mcp__" + name + "__*" for name in dict.fromkeys(["layout", *settings.get("mcp_servers", {})])]
    config = copy.deepcopy(settings["config"])
    config.update(thinking={"enabled": True, "effort": condition["effort_resolved"]},
                  telemetry=False, auto_session_title=False,
                  builtin_product_skills=False, merge_all_available_skills=False,
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
                     "Solve the supplied problem document using the layout MCP tools.\n")
    args = ["kimi", "--model", condition["model"],
            "--skills-dir", str(skills), "--output-format", "stream-json", "--prompt", prompt]
    native_id = env.get('ICLAYOUT_BENCH_RESUME_ID')
    if native_id:
        root = _session_root(context.output)
        if root is None or root.name != native_id:
            raise ValueError('Kimi Code native session is missing or ambiguous; refusing a new session')
        binding = _binding(root)
        if (binding.get('profileName') != 'layout-participant'
                or binding.get('modelAlias') != condition['model']
                or binding.get('thinkingEffort') != condition['effort_resolved']
                or binding.get('activeToolNames') != tools or binding.get('subagents') != []):
            raise ValueError('Kimi Code saved binding differs from the frozen participant')
        return args + ['--session', native_id]
    return args + ['--agent-file', str(agent)]


def _session_root(output):
    home = Path(output) / '.private/kimi-home'
    sessions = home / 'sessions'
    roots = []
    for path in sessions.glob('*/*/state.json'):
        wire = path.parent / 'agents/main/wire.jsonl'
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', path.parent.name)
                or not path.resolve().is_relative_to(sessions.resolve())
                or not wire.is_file() or not wire.resolve().is_relative_to(sessions.resolve())):
            continue
        try:
            metadata = json.loads(path.read_bytes())
        except (ValueError, UnicodeError):
            continue
        if (isinstance(metadata, dict) and metadata.get('id') == path.parent.name
                and metadata.get('cwd') == str((home.parent / 'workspace').resolve())):
            roots.append(path.parent)
    return roots[0] if len(roots) == 1 else None


def _binding(root):
    result = {}
    for event in json_events(root / 'agents/main/wire.jsonl'):
        if event.get('type') == 'profile.bind' and event.get('agentId') == 'main':
            result = event
    return result


def session_id(output, state):
    # Failed print-mode turns omit resume_hint. The attempt's isolated home
    # still owns its persisted conversation; ambiguity never permits a launch.
    root = _session_root(output)
    return root.name if root is not None else None


def credential_redactions(output):
    home = Path(output) / '.private/kimi-home'
    secrets = set()
    for path in (home / 'credentials').glob('*.json'):
        if path.resolve().is_relative_to(home.resolve()):
            try:
                secrets.update(credential_values(json.loads(path.read_bytes())))
            except (ValueError, UnicodeError):
                pass
    return secrets


def native_traces(output):
    """Select native records, excluding configuration and credential stores."""
    home = Path(output) / '.private/kimi-home'
    paths = [home / 'logs/kimi-code.log', home / 'session_index.jsonl']
    sessions = home / 'sessions'
    paths.extend(sessions.glob('*/*/state.json'))
    paths.extend(sessions.glob('*/*/agents/*/wire.jsonl'))
    paths.extend(sessions.glob('*/*/logs/kimi-code.log'))
    traces = {}
    for path in sorted(paths):
        if path.is_file() and path.resolve().is_relative_to(home.resolve()):
            traces['kimi/' + path.relative_to(home).as_posix()] = path.read_bytes()
    return traces


def usage(agent, native):
    evidence = UsageEvidence()
    for name, events in native_records(native, "kimi"):
        if not name.endswith("/wire.jsonl"):
            continue
        pending, latest = {}, {}
        for index, event in enumerate(events):
            who = event.get("agentId", "main")
            kind = event.get("type")
            if kind == "llm.request":
                pending[who] = event
            elif kind == "usage.record":
                start = pending.pop(who, {})
                value = event.get("usage") or {}
                record = request_record(f"{name}:{index}", event.get("model") or start.get("modelAlias"),
                    uncached=value.get("inputOther"), cached=value.get("inputCacheRead", 0),
                    written=value.get("inputCacheCreation", 0), output=value.get("output"),
                    reasoning=value.get("reasoning"), seconds=duration(start.get("time"), event.get("time")),
                    started_at=start.get("time"), cost=value.get("cost"), source=name)
                evidence.requests.append(record)
                latest[who] = record
            elif kind == "context.append_loop_event" and (event.get("event") or {}).get("type") == "step.end":
                step = event["event"]
                if who in latest:
                    first, stream = number(step.get("llmFirstTokenLatencyMs")), number(step.get("llmStreamDurationMs"))
                    if first is not None and stream is not None:
                        latest.pop(who)["elapsed_seconds"] = (first + stream) / 1000
        for who, start in pending.items():
            evidence.requests.append(request_record(f"{name}:pending:{who}", start.get("modelAlias"),
                                                    started_at=start.get("time"), source=name))
    if not evidence.requests:
        for index, event in enumerate(records(agent)):
            payload = event.get("payload") or {}
            if event.get("type") != "StatusUpdate" or not isinstance(payload.get("token_usage"), dict):
                continue
            value = payload["token_usage"]
            evidence.requests.append(request_record(f"stdout:{index}", None,
                uncached=value.get("input_other"), cached=value.get("input_cache_read", 0),
                written=value.get("input_cache_creation", 0), output=value.get("output"), source="agent.jsonl"))
    return evidence

PREFIX = 'error: failed to run prompt: '
ERROR = re.compile(r'(?P<code>[a-z][a-z_.]+): (?:(?P<status>[0-9]{3}) )?(?P<message>.*)')
QUOTA_MESSAGES = ("you've reached your 5-hour usage limit", "you've reached your weekly (7-day) usage limit",
                  "you've reached your monthly usage limit")


def json_events(path):
    if Path(path).is_file():
        for line in Path(path).read_text(errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event


def _code(detail):
    if detail == 'The provided authorization grant is invalid':
        return 'authentication_error'
    match = ERROR.fullmatch(detail)
    if match is None:
        return None
    code, status, message = match['code'], match['status'], match['message'].casefold()
    if status in {'403', '429'} and message.startswith(QUOTA_MESSAGES):
        return 'insufficient_quota'
    if status == '403' and message.startswith("you've reached your concurrent request limit"):
        return 'rate_limit_error'
    if code == 'provider.overloaded' or (status == '429' and message.startswith('the engine is currently overloaded')):
        return 'server_overloaded'
    if code == 'provider.auth_error' or status == '401':
        return 'authentication_error'
    if code == 'provider.connection_error':
        return 'connection_error'
    if code == 'provider.rate_limit' or status == '429':
        return 'rate_limit_error'
    return None


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, timed_out)
    evidence = structured_evidence(output)
    if timed_out or not exit_code:
        return classify_evidence(evidence, exit_code, timed_out)
    codes = list(evidence.codes)
    configuration = False
    stderr = Path(output, 'harness.stderr')
    for line in stderr.read_text(errors='replace').splitlines() if stderr.is_file() else ():
        if line.startswith(PREFIX):
            detail = line.removeprefix(PREFIX)
            configuration |= detail.startswith('provider ') and detail.endswith(' has no credential configured')
            codes.append(_code(detail))
    result = classify_evidence(ErrorEvidence(tuple(codes), evidence.retry_after), exit_code, timed_out)
    if configuration and result['category'] == 'unknown':
        return failure('harness_configuration', 'harness_stderr', 'missing_provider_credential')
    return result
