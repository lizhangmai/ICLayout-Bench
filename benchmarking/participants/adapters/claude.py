"""Claude Code configuration and isolated command construction."""

import json
import uuid
from pathlib import Path

from . import claude_events
from .contracts import EFFORTS, HarnessMetadata, LaunchContext, ParticipantSelection
from .native import confined_files, json_events, traces

METADATA = HarnessMetadata('claude', 'CLAUDE_CONFIG_DIR', '.claude', '.credentials.json')

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}


def harness_failure(output, exit_code=None, timed_out=False):
    return claude_events.harness_failure(output, exit_code, timed_out)


def resolve(model, effort, env):
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
    env.update(provider_env)
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
    return ParticipantSelection(condition, env, cli_settings)


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
        json.dumps({key: value for key, value in settings.items() if key != "mcp_servers"}),
        "--strict-mcp-config",
        "--mcp-config",
        str(mcp),
        "--disable-slash-commands",
        "--tools",
        "",
        "--allowedTools",
        ",".join(
            "mcp__" + name for name in ["layout", *settings.get("mcp_servers", {})]
        ),
        "--permission-mode",
        "dontAsk",
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
