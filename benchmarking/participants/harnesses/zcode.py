"""ZCode API/OAuth connections and isolated native print-mode launches."""

import copy
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from benchmarking.files import text, write_json
from benchmarking.participants.harnesses import zcode_subscription
from benchmarking.participants.harnesses.contracts import (
    HarnessMetadata,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.credentials import credential_values
from benchmarking.participants.harnesses.events import (
    ErrorEvidence,
    classify_evidence,
    read_events,
    structured_errors,
)
from benchmarking.participants.harnesses.records import native_records, records, traces
from benchmarking.results.usage import UsageEvidence, number, request_record

METADATA = HarnessMetadata('zcode', 'ZCODE_DATA_BASE_DIR', '.zcode/cli', None, 'config.json')

CAPABILITIES = {"resume_session": True, "capacity_resumes": True}


WIRE_APIS = {'anthropic': 'anthropic-messages', 'openai': 'openai-responses',
             'openai-compatible': 'openai-chat-completions'}

# ZCode 0.16.9 removes these tools from the provider-visible registry through
# --disallowed-tools. permission.allowedTools alone only changes approvals.
HOST_TOOLS = (
    'Read', 'Write', 'Edit', 'ApplyPatch', 'Bash', 'Glob', 'Grep', 'WebFetch', 'WebSearch',
    'TodoRead', 'TodoWrite', 'CronCreate', 'CronList', 'CronUpdate', 'CronDelete',
    'OffPeakCreate', 'OffPeakList', 'EnterPlanMode', 'ExitPlanMode', 'AskUserQuestion',
    'SendMessage', 'RespondToCoordinator', 'SubmitResult', 'Escalate', 'TaskOutput', 'TaskStop',
    'ReadSessionContext', 'ReplyToChannel', 'Agent', 'Task', 'Skill', 'js', 'GoalRead',
    'CreateWorkflow', 'AmendWorkflow', 'SaveWorkflow', 'EvalWorkflowSnippet', 'ListWorkflowRuns',
    'GetWorkflowRun', 'ResumeWorkflowRun', 'ResolveWorkflowQuestion', 'FillWorkflowHole',
    'ListSavedWorkflows', 'ListModels', 'Workflow',
)


def resolve(model, effort, env, *, home=None):
    if home is None:
        home = (Path(env[METADATA.home_environment]) / '.zcode/cli'
                if env.get(METADATA.home_environment) else Path.home() / '.zcode/cli')
    config = json.loads((home / METADATA.configuration_file).read_text())
    if not isinstance(config, dict) or set(config) - {'model', 'provider', 'network', 'auth_method'}:
        raise ValueError('ZCode experiment home accepts model connections only')
    auth_method = config.get('auth_method', 'api')
    if auth_method not in {'api', 'subscription'}:
        raise ValueError('ZCode auth_method must be api or subscription')
    network = config.get('network', {})
    if (not isinstance(network, dict) or set(network) - {'httpProxy', 'noProxy'}
            or any(not isinstance(value, str) or not value.strip() for value in network.values())):
        raise ValueError('ZCode network accepts nonempty httpProxy/noProxy connection settings only')
    if 'httpProxy' in network:
        proxy = urlsplit(network['httpProxy'])
        if (proxy.scheme not in {'http', 'https'} or not proxy.hostname or proxy.username or proxy.password
                or proxy.query or proxy.fragment):
            raise ValueError('ZCode httpProxy must be HTTP(S) without credentials, query or fragment')
    configured = config.get('model', {})
    default = configured.get('main') if isinstance(configured, dict) else configured
    target = model or default
    if not isinstance(target, str) or '/' not in target:
        raise ValueError('ZCode model must use the configured provider/model reference')
    provider, model_id = target.split('/', 1)
    if (not model_id.strip() or (auth_method == 'api'
            and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', provider))):
        raise ValueError('Invalid ZCode provider/model reference')
    providers = config.get('provider', {})
    if not isinstance(providers, dict) or not providers:
        raise ValueError('ZCode API providers must be configured in the selected profile')
    spec = copy.deepcopy(providers.get(provider))
    if not isinstance(spec, dict) or set(spec) - {'kind', 'name', 'options', 'models'}:
        raise ValueError('ZCode model provider is missing or has unsupported connection fields')
    kind = spec.get('kind')
    if kind not in WIRE_APIS:
        raise ValueError('ZCode API provider must use anthropic, openai or openai-compatible')
    options = spec.get('options', {})
    if not isinstance(options, dict) or set(options) - {'apiKey', 'apiKeyEnv', 'apiKeyRequired', 'baseURL'}:
        raise ValueError('Unsupported ZCode API connection options')
    endpoint = text(options.get('baseURL'), 'ZCode baseURL')
    url = urlsplit(endpoint)
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('ZCode baseURL must be HTTP(S) without credentials, query or fragment')
    models = spec.get('models', {})
    if not isinstance(models, dict) or not models:
        raise ValueError('ZCode API models must be configured in the selected profile')
    entry = models.get(model_id)
    if entry is None or not isinstance(entry, dict):
        raise ValueError('ZCode model is not configured in the selected profile')
    reasoning = entry.get('reasoning', {})
    if not isinstance(reasoning, dict):
        raise TypeError('ZCode model must declare reasoning levels')
    resolved = effort or reasoning.get('defaultLevel')
    levels = reasoning.get('levels', [])
    if (not isinstance(levels, list) or not levels
            or any(not isinstance(level, str) or not level.strip() for level in levels)
            or resolved is None or resolved not in levels):
        raise ValueError('ZCode effort must be explicitly supported by the selected model')
    auth, fields = None, {}
    ref = options.get('apiKeyEnv') if auth_method == 'api' else None
    if auth_method == 'subscription':
        auth, fields = zcode_subscription.resolve(home, provider, kind, options, env)
        key = None
    elif ref is not None:
        if not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', ref):
            raise ValueError('ZCode apiKeyEnv must name an environment variable')
        if options.get('apiKey'):
            raise ValueError('Select either ZCode apiKey or apiKeyEnv authentication')
        key = env.get(ref)
    else:
        key = options.get('apiKey')
    if auth_method == 'api' and (not isinstance(key, str) or not key.strip()):
        raise ValueError('ZCode experiment home needs configured API authentication')
    env = env.copy()
    for name in list(env):
        if name.startswith(('ZCODE_', 'ZAI_', 'ANTHROPIC_', 'OPENAI_', 'BIGMODEL_')):
            del env[name]
    if ref:
        env[ref] = key
    env[METADATA.home_environment] = str(home.resolve())
    if auth_method == 'api':
        connection = {'providerId': provider, 'config': {'group': 'standard-personal',
                      'access': {'type': 'api-key', 'apiKey': key},
                      'api': {'type': WIRE_APIS[kind], 'baseUrl': endpoint},
                      'personalModelIds': [model_id], 'modelOrder': [model_id]}}
    condition = {'harness': 'zcode', 'provider': provider, 'model': target, 'auth_method': auth_method,
                 'wire_api': WIRE_APIS[kind], 'base_url': endpoint,
                 'effort_requested': effort, 'effort_resolved': resolved,
                 'effort_source': 'experiment' if effort else 'zcode configuration',
                 'provider_effective_effort': None}
    if ref:
        condition['api_key_env'] = ref
    if network:
        condition['network'] = copy.deepcopy(network)
    settings = {'provider_config': {'schemaVersion': 1, 'config': {
        # Native account providers belong to ZCode's built-in catalog. Defining
        # them as personal providers invalidates the config and silently falls
        # back to the CLI's default model/effort (observed with ZCode 0.17).
        'providerOrder': [provider],
        'providerConfigRules': {'providerRules': [connection] if auth_method == 'api' else []},
        'modelConfigRules': {'providerModelRules': [], 'manualProviderModelRules': []},
        'defaultModelSelection': {'providerId': provider, 'modelId': model_id,
                                 'options': {'reasoningLevel': resolved}}}}}
    settings['network'] = copy.deepcopy(network)
    if auth is not None:
        settings.update(subscription=auth, credential_fields=fields)
    return ParticipantSelection(condition, env, settings)


def prepare(context: LaunchContext) -> list[str]:
    env = context.selection.environment
    native_id = env.get('ICLAYOUT_BENCH_RESUME_ID')
    home = (context.directory.parent / 'native-home').resolve()
    native = home / '.zcode'
    cli = native / 'cli'
    home.mkdir(mode=0o700, exist_ok=True)
    native.mkdir(mode=0o700, exist_ok=True)
    cli.mkdir(mode=0o700, exist_ok=True)
    if 'subscription' in context.selection.settings:
        zcode_subscription.prepare(home.parent, context.selection.settings['subscription'], env)
        personal = home.parent / 'zcode-provider-config.json'
    else:
        (native / 'v2').mkdir(mode=0o700, exist_ok=True)
        personal = native / 'v2/provider_config.json'
    servers = json.loads(context.mcp.read_text())['mcpServers']
    timeout = int(env['ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS']) * 1000
    config = {'network': context.selection.settings['network'],
              'storage': {'dir': str(native), 'sessionDbPath': str(cli / 'db/db.sqlite')},
              'features': {'mcp': True, 'subagent': False, 'skill': False, 'memory': False},
              'memory': {'use': False}, 'plugins': {'enabled': False},
              'skills': {'enabled': False, 'includeInstructions': False, 'roots': []},
              'hooks': {'enabled': False}, 'permission': {'mode': 'yolo'},
              'mcp': {'servers': {name: dict(spec, type='stdio', enabled=True, timeoutMs=timeout)
                                  for name, spec in servers.items()}}}
    if native_id:
        validate_resume(context, config, native_id)
    write_json(personal, context.selection.settings['provider_config'])
    write_json(cli / 'config.json', config)
    # Only this child process receives the isolated OS home. The native CLI
    # otherwise reads ~/.zcode/cli/config.json independently of its data root.
    env.update(HOME=str(home), ZCODE_HOME=str(native), ZCODE_DATA_BASE_DIR=str(home),
               ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=str(personal), ZCODE_STORAGE_DIR=str(native),
               ZCODE_SESSION_DB_PATH=str(cli / 'db/db.sqlite'),
               ZCODE_MODEL_TELEMETRY_ENABLED='false', OTEL_SDK_DISABLED='true')
    return ['zcode', '--cwd', str(context.directory.resolve()), '--mode', 'yolo',
            '--workflow-mode', 'disabled', '--disallowed-tools', ','.join(HOST_TOOLS),
            '--output-format', 'stream-json', '--no-color',
            *(['--resume', native_id] if native_id else []), '--prompt', context.prompt]


def credential_redactions(output):
    path = Path(output) / '.private/native-home/.zcode/v2/provider_config.json'
    if (Path(output) / '.private/zcode-subscription.json').exists():
        return zcode_subscription.redactions(output)
    return credential_values(json.loads(path.read_text())) if path.is_file() else set()


def native_traces(output):
    return traces(Path(output) / '.private/native-home/.zcode/cli', 'zcode',
                  'rollout/*.jsonl', 'log/*.jsonl')


def provider_code(attribution, fallback):
    if attribution.get('reason') == 'auth_failed' and attribution.get('statusCode') in {401, 403}:
        return 'authentication_error'
    code = attribution.get('providerErrorCode') or fallback
    # BigModel subscription usage-window exhaustion is a provider quota block,
    # even though native attribution calls it rate_limited with HTTP 429.
    if code == '1308':
        return 'insufficient_quota'
    # Explicit policy throttling shares the bounded capacity recovery budget.
    # Preserve its identity separately from transient request-rate throttling.
    code = {'1313': 'account_policy_rate_limit', '1312': 'server_overloaded',
            'engine_overloaded_error': 'server_overloaded',
            'rate_limit_reached_error': 'rate_limit_error'}.get(code, code)
    if not attribution.get('providerErrorCode') and attribution.get('retryable') is True:
        code = {'rate_limited': 'rate_limit_error', 'provider_overloaded': 'server_overloaded'}.get(
            attribution.get('reason'), code)
    return code


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, True)
    normalized = []
    failed_result = False
    for event in read_events(output):
        payload = event.get('payload', {})
        if event.get('type') == 'turn.failed' and isinstance(payload, dict) and isinstance(payload.get('error'), dict):
            detail = payload['error']
            attribution = detail.get('attribution', {})
            if not isinstance(attribution, dict):
                attribution = {}
            code = detail.get('code')
            if isinstance(attribution, dict):
                if attribution.get('source') == 'provider':
                    code = provider_code(attribution, code)
                elif (attribution.get('source') == 'network' and attribution.get('exceptionKind') == 'transport'
                      and attribution.get('retryable') is True
                      and attribution.get('reason') in {'timeout', 'stream_idle_timeout', 'network_error', 'proxy_error'}):
                    code = 'connection_error'
            normalized.append({'type': 'turn.failed', 'code': code,
                               'retry_after': detail.get('retry_after', attribution.get('retry_after'))})
        else:
            normalized.append(event)
        if event.get('type') == 'result' and isinstance(event.get('projection'), dict):
            failed_result = failed_result or event['projection'].get('status') == 'error'
    if failed_result and not any(event.get('type') in {'error', 'turn.failed'} for event in normalized):
        normalized.append({'type': 'error'})
    return classify_evidence(structured_errors(normalized), exit_code)


def usage(agent, native):
    evidence = UsageEvidence()
    for name, events in native_records(native, "zcode"):
        if "/rollout/" not in name:
            continue
        for index, event in enumerate(events):
            if event.get("type") != "model_io":
                continue
            response = event.get("response") or {}
            value = response.get("usage") or {}
            model = event.get("model") or {}
            ms = number(event.get("durationMs"))
            # ZCode's normalized inputTokens includes the cached subsets.
            evidence.requests.append(request_record(f"{event.get('requestId', name + ':' + str(index))}:{event.get('attempt', 1)}",
                model.get("modelId"), input_tokens=value.get("inputTokens"), cached=value.get("cacheReadTokens", 0),
                written=value.get("cacheWriteTokens", 0), output=value.get("outputTokens"),
                reasoning=value.get("reasoningTokens"), seconds=ms / 1000 if ms is not None else None,
                started_at=event.get("startedAt"), cost=value.get("cost"), source=name))
    if not evidence.requests:
        for index, event in enumerate(records(agent)):
            if event.get("type") != "result" or not isinstance(event.get("usage"), dict):
                continue
            value = event["usage"]
            evidence.requests.append(request_record(f"stdout:{index}", event.get("model"),
                input_tokens=value.get("inputTokens"), cached=value.get("cacheReadTokens", 0),
                written=value.get("cacheWriteTokens", 0), output=value.get("outputTokens"),
                cost=value.get("cost"), source="agent.jsonl", scope="session"))
    return evidence


def _session(output):
    home = Path(output) / '.private/native-home'
    db = home / '.zcode/cli/db/db.sqlite'
    if not db.is_file() or not db.resolve().is_relative_to(home.resolve()):
        raise ValueError('ZCode persisted session database is missing')
    with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        # Read one consistent snapshot after the native process has exited.
        connection.execute('BEGIN')
        roots = connection.execute(
            'SELECT id, directory, path, revert FROM session WHERE parent_id IS NULL AND time_archived IS NULL'
        ).fetchall()
        if len(roots) != 1:
            raise ValueError('ZCode persisted main session is missing or ambiguous')
        native_id, directory, path, revert = roots[0]
        cwd = str((home.parent / 'workspace').resolve())
        if (not isinstance(native_id, str) or not re.fullmatch(r'sess_[A-Za-z0-9-]+', native_id)
                or directory != cwd or path != cwd or revert is not None):
            raise ValueError('ZCode persisted workspace differs from the participant')
        selections = connection.execute(
            "SELECT data FROM session_entry WHERE session_id = ? AND type = 'runtime/model_selection'",
            (native_id,),
        ).fetchall()
        if len(selections) != 1:
            raise ValueError('ZCode persisted model selection is missing or ambiguous')
        selection = json.loads(selections[0][0])['modelSelection']
        messages = connection.execute(
            'SELECT id, data FROM message WHERE session_id = ? ORDER BY sequence', (native_id,)
        ).fetchall()
        if not messages:
            raise ValueError('ZCode persisted conversation is missing')
    return native_id, selection, {key: json.loads(data) for key, data in messages}


def session_id(output, state):
    try:
        native_id, _, _ = _session(output)
        return native_id
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, AttributeError):
        return None


def _tool_binding(config):
    config = copy.deepcopy(config)
    # These runtime values may rotate after a service/worker restart. Session,
    # model, effort, tool commands and arguments must still match exactly.
    for server in config['mcp']['servers'].values():
        for key in ('ICLAYOUT_BENCH_ENDPOINT', 'ICLAYOUT_BENCH_TOKEN', 'ICLAYOUT_BENCH_RESUME_ID',
                    'ICLAYOUT_BENCH_LEASE_FD', 'ICLAYOUT_BENCH_RECOVERY'):
            server.get('env', {}).pop(key, None)
    return config


def validate_resume(context, config, native_id):
    try:
        saved_id, selection, messages = _session(context.output)
        expected = context.selection.settings['provider_config']['config']['defaultModelSelection']
        if saved_id != native_id or session_id(context.output, None) != native_id:
            raise ValueError('ZCode persisted session is missing or ambiguous')
        if selection != expected or not any(
            message.get('role') == 'user' and message.get('modelSelection') == expected for message in messages.values()
        ):
            raise ValueError('ZCode saved model/effort differs from the frozen participant')
        home = Path(context.output) / '.private/native-home/.zcode'
        previous = json.loads((home / 'cli/config.json').read_bytes())
        if _tool_binding(previous) != _tool_binding(config):
            raise ValueError('ZCode saved tool binding differs from the frozen participant')
    except (OSError, sqlite3.Error, KeyError, TypeError, AttributeError) as error:
        raise ValueError('ZCode persisted continuation binding is missing or invalid') from error
