"""ZCode API connections and isolated native print-mode launches."""

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from benchmarking.files import text, write_json

from ..credentials import credential_values
from . import zcode_events
from .contracts import HarnessMetadata, LaunchContext, ParticipantSelection
from .native import traces

METADATA = HarnessMetadata('zcode', 'ZCODE_DATA_BASE_DIR', '.zcode/cli', None, 'config.json')

# Native resume exists, but continuation stays disabled until persisted model,
# workspace and tool bindings can be verified independently of announced IDs.
CAPABILITIES = {"resume_session": False, "capacity_resumes": False}

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


def harness_failure(output, exit_code=None, timed_out=False):
    return zcode_events.harness_failure(output, exit_code, timed_out)


def resolve(model, effort, env, *, home=None):
    if home is None:
        home = (Path(env[METADATA.home_environment]) / '.zcode/cli'
                if env.get(METADATA.home_environment) else Path.home() / '.zcode/cli')
    config = json.loads((home / METADATA.configuration_file).read_text())
    if not isinstance(config, dict) or set(config) - {'model', 'provider', 'network'}:
        raise ValueError('ZCode experiment home accepts model connections only')
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
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', provider) or not model_id.strip():
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
    ref = options.get('apiKeyEnv')
    if ref is not None:
        if not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', ref):
            raise ValueError('ZCode apiKeyEnv must name an environment variable')
        if options.get('apiKey'):
            raise ValueError('Select either ZCode apiKey or apiKeyEnv authentication')
        key = env.get(ref)
    else:
        key = options.get('apiKey')
    if not isinstance(key, str) or not key.strip():
        raise ValueError('ZCode experiment home needs configured API authentication')
    env = env.copy()
    for name in list(env):
        if name.startswith(('ZCODE_', 'ZAI_', 'ANTHROPIC_', 'OPENAI_', 'BIGMODEL_')):
            del env[name]
    if ref:
        env[ref] = key
    env[METADATA.home_environment] = str(home.resolve())
    connection = {'providerId': provider, 'config': {'group': 'standard-personal',
                  'access': {'type': 'api-key', 'apiKey': key},
                  'api': {'type': WIRE_APIS[kind], 'baseUrl': endpoint},
                  'personalModelIds': [model_id], 'modelOrder': [model_id]}}
    condition = {'harness': 'zcode', 'provider': provider, 'model': target, 'auth_method': 'api',
                 'wire_api': WIRE_APIS[kind], 'base_url': endpoint,
                 'effort_requested': effort, 'effort_resolved': resolved,
                 'effort_source': 'experiment' if effort else 'zcode configuration',
                 'provider_effective_effort': None}
    if ref:
        condition['api_key_env'] = ref
    if network:
        condition['network'] = copy.deepcopy(network)
    settings = {'provider_config': {'schemaVersion': 1, 'config': {
        'providerOrder': [provider], 'providerConfigRules': {'providerRules': [connection]},
        'modelConfigRules': {'providerModelRules': [], 'manualProviderModelRules': []},
        'defaultModelSelection': {'providerId': provider, 'modelId': model_id,
                                 'options': {'reasoningLevel': resolved}}}}}
    settings['network'] = copy.deepcopy(network)
    return ParticipantSelection(condition, env, settings)


def prepare(context: LaunchContext) -> list[str]:
    env = context.selection.environment
    if env.get('ICLAYOUT_BENCH_RESUME_ID'):
        raise ValueError('ZCode continuation is not supported by this adapter')
    home = (context.directory.parent / 'native-home').resolve()
    native = home / '.zcode'
    cli = native / 'cli'
    home.mkdir(mode=0o700, exist_ok=True)
    native.mkdir(mode=0o700, exist_ok=True)
    cli.mkdir(mode=0o700, exist_ok=True)
    (native / 'v2').mkdir(mode=0o700, exist_ok=True)
    personal = native / 'v2/provider_config.json'
    write_json(personal, context.selection.settings['provider_config'])
    servers = json.loads(context.mcp.read_text())['mcpServers']
    timeout = int(env['ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS']) * 1000
    config = {'network': context.selection.settings['network'],
              'storage': {'dir': str(native), 'sessionDbPath': str(cli / 'db/sessions.sqlite')},
              'features': {'mcp': True, 'subagent': False, 'skill': False, 'memory': False},
              'memory': {'use': False}, 'plugins': {'enabled': False},
              'skills': {'enabled': False, 'includeInstructions': False, 'roots': []},
              'hooks': {'enabled': False}, 'permission': {'mode': 'yolo'},
              'mcp': {'servers': {name: dict(spec, type='stdio', enabled=True, timeoutMs=timeout)
                                  for name, spec in servers.items()}}}
    write_json(cli / 'config.json', config)
    # Only this child process receives the isolated OS home. The native CLI
    # otherwise reads ~/.zcode/cli/config.json independently of its data root.
    env.update(HOME=str(home), ZCODE_HOME=str(native), ZCODE_DATA_BASE_DIR=str(home),
               ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=str(personal), ZCODE_STORAGE_DIR=str(native),
               ZCODE_MODEL_TELEMETRY_ENABLED='false', OTEL_SDK_DISABLED='true')
    return ['zcode', '--cwd', str(context.directory.resolve()), '--mode', 'yolo',
            '--workflow-mode', 'disabled', '--disallowed-tools', ','.join(HOST_TOOLS),
            '--output-format', 'stream-json', '--no-color', '--prompt', context.prompt]


def credential_redactions(output):
    path = Path(output) / '.private/native-home/.zcode/v2/provider_config.json'
    return credential_values(json.loads(path.read_text())) if path.is_file() else set()


def native_traces(output):
    return traces(Path(output) / '.private/native-home/.zcode/cli', 'zcode',
                  'rollout/*.jsonl', 'log/*.jsonl')
