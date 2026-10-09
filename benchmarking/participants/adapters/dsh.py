"""DSH headless profile adapter; invocation overlays never edit user settings."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
import zstandard
from dotenv import dotenv_values

from benchmarking.files import atomic_write

from ..credentials import credential_values
from . import dsh_events
from .contracts import HarnessMetadata, LaunchContext, ParticipantSelection
from .native import confined_files

METADATA = HarnessMetadata('dsh', 'DSH_HOME', '.dsh', None)

CAPABILITIES = {"resume_session": True, "capacity_resumes": False}


def harness_failure(output, exit_code=None, timed_out=False):
    return dsh_events.harness_failure(output, exit_code, timed_out)


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


def configuration(env=None):
    env = os.environ if env is None else env
    help_text = subprocess.check_output(
        ['dsh', '--profile', 'headless', '--help'], text=True, timeout=30, env=env,
    )
    if '--json' not in help_text or '--session-id' not in help_text:
        raise ValueError('DSH adapter requires headless --json and --session-id support (0.2.0-rc.2 or newer)')
    raw = subprocess.check_output(
        ["dsh", "--profile", "headless", "--dump-config"],
        text=True,
        timeout=30,
        env=env,
    )
    rows = list(entries(yaml.load(raw, Loader=ConfigLoader)))
    home = Path(env.get("DSH_HOME", str(Path.home() / ".dsh")))
    path = home / "settings.yaml"
    settings = yaml.safe_load(path.read_text()) if path.exists() else {}
    base = next((r.get("config", {}) for r in rows if r["id"] == "agent-default-model"), {})
    selection = dict(base, **(settings or {}).get("agent-default-model", {}))
    return rows, settings or {}, selection


def _credential_values(path):
    if not path.is_file():
        return set()
    if path.name == '.env':
        return {value for value in dotenv_values(path, interpolate=False).values()
                if isinstance(value, str) and len(value) >= 4}
    try:
        data = yaml.safe_load(path.read_text())
    except (ValueError, UnicodeError, yaml.YAMLError):
        return set()
    refs = data.get('refs', {}) if isinstance(data, dict) else {}
    secrets = credential_values(data)
    if isinstance(refs, dict):
        secrets.update(value for value in refs.values() if isinstance(value, str) and len(value) >= 4)
    return secrets


def stage_credentials(private, env):
    original = METADATA.home(env)
    home = private / 'native-home'
    home.mkdir(mode=0o700, exist_ok=True)
    redactions = set()
    # These are DSH's native managed store and native credential fallback.
    # Preserve refreshed private copies on every continuation.
    for filename in ('.credentials.yaml', '.env'):
        source, target = original / filename, home / filename
        if source.is_file():
            redactions.update(_credential_values(source))
            if not target.exists():
                atomic_write(target, source.read_bytes())
        redactions.update(_credential_values(target))
    env['DSH_HOME'] = str(home.resolve())
    return redactions


def credential_redactions(output):
    home = Path(output) / '.private/native-home'
    return set().union(*(_credential_values(path) for path in
                         confined_files(home, '.credentials.yaml', '.env')))


def resolve(model, effort, env):
    rows, settings, selected = configuration(env)
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
    condition = {
        "harness": "dsh", "provider": provider, "model": model,
        "effort_requested": effort, "effort_resolved": resolved,
        "effort_source": source, "provider_effective_effort": None,
    }
    # Native API-key references need not contain "key" or "token" in their
    # environment names. Keep resolved values private for trace redaction.
    credentials = []
    for row in rows:
        if row['id'].startswith('llm-'):
            config = row.get('config', {})
            ref = config.get('apiKeyEnv') if isinstance(config, dict) else None
            if isinstance(ref, str) and ref in env:
                credentials.append({'api_key': env[ref]})
    return ParticipantSelection(condition, env, {"rows": rows, "settings": settings,
                                                'credential_fields': credentials})


def prepare(context: LaunchContext) -> list[str]:
    condition = context.selection.condition
    env = context.selection.environment
    settings = context.selection.settings
    directory, output, bridge, prompt = context.directory, context.output, context.bridge, context.prompt
    from benchmarking.files import write_json as save

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
            "plan-mode", "plugin-manager", "hmr", "config-editor", "subagent",
            "subagent-spawn-in-process", "subagent-fork-in-process",
        }:
            patch.append({"id": name, "disabled": True})
        elif name.startswith('llm-') and row.get('config'):
            # The private home composes a clean native profile. Provider
            # connections from the selected profile must survive that isolation;
            # some native providers explicitly opt out of settings-file overlays.
            patch.append({'id': name, 'config': row['config']})
    home = directory.parent / 'native-home'
    home.mkdir(mode=0o700, exist_ok=True)
    env['DSH_HOME'] = str(home.resolve())
    patch += [
        {"id": "settings", "config": {"path": str(settings_path), "watch": False}},
        {"id": "tools", "config": {"mode": "native"}},
        {"id": "session-telemetry-otel", "config": {"mode": "DISABLED"}},
        {"id": "credentials", "config": {"path": str(home / '.credentials.yaml'), "watch": False}},
        {"id": "session-persistence-jsonl", "config": {"root": str(home / 'sessions')}},
        {"id": "storage-json", "config": {"root": str(home / 'storages')}},
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
    args = ["dsh", "--profile", "headless", "--patch", str(path), '--json']
    if env.get('ICLAYOUT_BENCH_RESUME_ID'):
        native_id = env['ICLAYOUT_BENCH_RESUME_ID']
        root = _session(output)
        if root is None or root['id'] != native_id:
            raise ValueError('DSH native session is missing or ambiguous; refusing a new session')
        args += ['--session-id', native_id]
    return args + [prompt]


def _raw(path):
    if path.suffix == '.zstd':
        with path.open('rb') as stream, zstandard.ZstdDecompressor().stream_reader(stream) as reader:
            return reader.read()
    return path.read_bytes()


def _session(output):
    home = Path(output) / '.private/native-home'
    cwd = str((home.parent / 'workspace').resolve())
    found = []
    for path in confined_files(home, 'sessions/**/session.v*.jsonl', 'sessions/**/session.v*.jsonl.zstd'):
        try:
            header = json.loads(_raw(path).splitlines()[0])
        except (ValueError, UnicodeError, IndexError, zstandard.ZstdError):
            continue
        if (isinstance(header, dict) and header.get('type') == 'session'
                and isinstance(header.get('id'), str)
                and re.fullmatch(r'session-[A-Za-z0-9-]+', header['id'])
                and path.parent.name == header['id'] and header.get('cwd') == cwd
                and 'parentSession' not in header and 'agentPreset' not in header
                and header.get('origin') != 'subagent'):
            found.append(header)
    return found[0] if len(found) == 1 else None


def session_id(output, state):
    header = _session(output)
    return header['id'] if header else None


def native_traces(output):
    home = Path(output) / '.private/native-home'
    result = {}
    for path in confined_files(home, 'sessions/**/session.v*.jsonl', 'sessions/**/session.v*.jsonl.zstd'):
        name = path.relative_to(home).as_posix().removesuffix('.zstd')
        # JSON stdout bounds reasoning/tool deltas. Decode all native frames
        # before redaction so full records survive without compressed secrets.
        result['dsh/' + name] = _raw(path)
    return result
