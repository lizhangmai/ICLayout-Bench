"""Kimi Code print-mode adapter with an isolated home and MCP-only tools."""
import copy
import json
import re
import tomllib
from pathlib import Path

import tomli_w
import yaml

from benchmarking.files import atomic_write

from ..credentials import credential_values
from . import kimi_events
from .contracts import HarnessMetadata, LaunchContext, ParticipantSelection

METADATA = HarnessMetadata('kimi', 'KIMI_CODE_HOME', '.kimi-code', None)

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}


def harness_failure(output, exit_code=None, timed_out=False):
    return kimi_events.harness_failure(output, exit_code, timed_out)


def _credential_path(oauth):
    key = oauth.get('key', '')
    name = key.removeprefix('oauth/') if isinstance(key, str) else ''
    if (oauth.get('storage') != 'file' or not name or name.startswith('.')
            or '/' in name or '\\' in name):
        raise ValueError('Kimi Code adapter requires a valid file OAuth token key')
    return Path('credentials') / (name + '.json')


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
        if not target.exists():
            # Native refresh may rotate tokens. A continuation must retain the
            # private copy instead of reverting to the original host snapshot.
            atomic_write(target, raw.encode('utf-8'))
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
                     "Use the supplied task contract and the evaluation MCP tools to complete the layout.\n")
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
    for event in kimi_events.json_events(root / 'agents/main/wire.jsonl'):
        if event.get('type') == 'profile.bind' and event.get('agentId') == 'main':
            result = event
    return result


def session_id(output, state):
    # Failed print-mode turns omit resume_hint. The attempt's isolated home
    # still owns its persisted conversation; ambiguity never permits a launch.
    root = _session_root(output)
    return root.name if root is not None else None


def native_traces(output):
    """Select native records, excluding configuration and credential stores."""
    home = Path(output) / '.private/kimi-home'
    secrets = set()
    for path in (home / 'credentials').glob('*.json'):
        if path.resolve().is_relative_to(home.resolve()):
            try:
                secrets.update(credential_values(json.loads(path.read_bytes())))
            except (ValueError, UnicodeError):
                pass
    paths = [home / 'logs/kimi-code.log', home / 'session_index.jsonl']
    sessions = home / 'sessions'
    paths.extend(sessions.glob('*/*/state.json'))
    paths.extend(sessions.glob('*/*/agents/*/wire.jsonl'))
    paths.extend(sessions.glob('*/*/logs/kimi-code.log'))
    traces = {}
    for path in sorted(paths):
        if path.is_file() and path.resolve().is_relative_to(home.resolve()):
            raw = path.read_bytes()
            for secret in sorted(secrets, key=len, reverse=True):
                raw = raw.replace(secret.encode(), b'<REDACTED>')
            traces['kimi/' + path.relative_to(home).as_posix()] = raw
    return traces
