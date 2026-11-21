"""Participant launch inputs: problem delivery, declared MCP tools and command participants."""

import json
import sys
from types import SimpleNamespace

import pytest
from helpers.participant import ServiceFixture, attempt_boundaries

from benchmarking.participants import command
from benchmarking.participants.attempt.runner import run_participant
from benchmarking.participants.batch.config import resolve
from benchmarking.participants.harnesses.contracts import (
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.harnesses.registry import cli_version, prepare
from benchmarking.participants.harnesses.scheme import resolve_scheme

pytestmark = pytest.mark.unit


def test_initial_prompt_contains_problem_verbatim_without_serializing_the_task_plan(tmp_path):
    problem = '# Layout task\n\nPreserve the declared circuit.\n中文要求。\n'
    fixture = ServiceFixture()
    create = fixture.create

    def created(*args, **kwargs):
        response = create(*args, **kwargs)
        response['task']['problem'] = problem
        response['task']['description']['evaluation'] = {
            'pre_layout': {'internal_measurements': 'evaluator-only-' + 'x' * 1_100_000}}
        return response

    fixture.create = created
    prompts = []

    def execute(argv, *, prompt, **kwargs):
        prompts.append(prompt)
        assert prompt == problem
        assert 'evaluator-only-' not in prompt
        assert len(prompt) < 10_000
        return 0, False

    selection = ParticipantSelection({'model': 'fixture', 'effort_resolved': 'low'}, {}, {})
    boundaries = attempt_boundaries(fixture, native_command=lambda context: ['fixture'], execute=execute)
    result, error = run_participant(fixture, {'harness': 'command', 'task': 'fixture'}, tmp_path, selection,
                                    boundaries=boundaries)
    assert error is None and result['outcome'] == 'no_submission'
    assert len(prompts) == 1


@pytest.mark.parametrize('layout_override', [False, True])
def test_command_participant_receives_problem_and_keeps_one_identity_across_tasks(tmp_path, layout_override):
    """Exercise the new launcher using a real subprocess and existing HTTP double.

    The problem, optional scheme instructions and scoped credential are separate inputs.
    Changing instructions must distinguish schemes; task/output paths must not.
    No provider or EDA claim is made by this Public-owned regression.
    """
    script = tmp_path / 'participant.py'
    wrapper = tmp_path / 'wrapper.py'
    wrapper.write_text('print("declared wrapper")\n')
    script.write_text('import json, os, sys\n'
                      'task = json.load(open(os.environ["ICLAYOUT_BENCH_TASK_FILE"]))\n'
                      'assert "session_token" not in task\n'
                      'assert os.environ["ICLAYOUT_BENCH_TOKEN"] == "scoped-fixture-token"\n'
                      'assert os.environ["ICLAYOUT_BENCH_MODEL"] == "fixture-model"\n'
                      'assert sys.stdin.read() == task["task"]["problem"]\n'
                      'scheme_instructions = open(os.environ["ICLAYOUT_BENCH_INSTRUCTIONS_FILE"]).read()\n'
                      'print(json.dumps({"scheme_instructions": scheme_instructions}))\n'
                      'assert "layout" in json.load(open(os.environ["ICLAYOUT_BENCH_MCP_CONFIG"]))["mcpServers"]\n'
                      'servers = json.load(open(os.environ["ICLAYOUT_BENCH_MCP_CONFIG"]))["mcpServers"]\n'
                      'assert servers["a"]["env"]["ICLAYOUT_BENCH_TOOL_ARTIFACTS"] == os.environ["ICLAYOUT_BENCH_TOOL_ARTIFACTS"]\n'
                      + ('server = json.load(open(os.environ["ICLAYOUT_BENCH_MCP_CONFIG"]))["mcpServers"]["layout"]\n'
                         'assert server["args"] == ' + repr([str(wrapper)]) + '\n'
                         'assert server["env"]["ICLAYOUT_BENCH_TOKEN"] == "scoped-fixture-token"\n'
                         'assert server["env"]["ICLAYOUT_BENCH_TOOL_ARTIFACTS"] == servers["a"]["env"]["ICLAYOUT_BENCH_TOOL_ARTIFACTS"]\n'
                         if layout_override else '') +
                      'print("contract received")\n')
    raw = {'version': 'test-1', 'launch': {'command': [sys.executable, 'participant.py'], 'files': ['participant.py']},
           'mcp': {'a': {'command': [sys.executable, 'wrapper.py'], 'files': ['wrapper.py']}}}
    if layout_override:
        raw['mcp']['layout'] = {'command': [sys.executable, 'wrapper.py'], 'files': ['wrapper.py']}
    identities = []
    for index, (task, instructions) in enumerate([('one', ''), ('two', ''), ('one', 'Use tool A')]):
        scheme = resolve_scheme(dict(raw, instructions=instructions), tmp_path, 'command')
        fixture = ServiceFixture()
        selection = resolve('command', 'fixture-model', 'medium')
        condition, env, settings = selection.condition, selection.environment, selection.settings
        output = tmp_path / str(index)
        # Command schemes declare their own version; only the HTTP service and isolation are synthetic.
        result, error = run_participant(fixture, {'harness': 'command', 'task': task, 'scheme': scheme}, output,
                                        ParticipantSelection(condition, env, settings),
                                        boundaries=attempt_boundaries(fixture, cli_version=cli_version))
        assert error is None
        assert result['outcome'] == 'no_submission'
        assert result['score'] is None
        assert 'contract received' in (output / 'harness.jsonl').read_text()
        assert json.loads((output / 'harness.jsonl').read_text().splitlines()[0]) == {'scheme_instructions': instructions}
        identities.append(fixture.condition['configuration_sha256'])
    assert identities[0] == identities[1]
    assert identities[0] != identities[2]


@pytest.mark.parametrize('harness', ['codex', 'claude-code'])
@pytest.mark.parametrize('server', ['a', 'layout'])
def test_declared_mcp_tool_is_enabled_without_putting_its_credentials_on_argv(tmp_path, harness, server):
    selected = {'harness': harness, 'model': 'fixture-model', 'effort_requested': 'medium', 'effort_resolved': 'medium'}
    settings = {'mcp_servers': {server: {'command': '/tools/a', 'args': ['serve'], 'env': {'A_API_KEY': 'private-key'}}}}
    env = {'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '60'}
    argv = prepare(LaunchContext(ParticipantSelection(selected, env, settings), tmp_path / 'mcp.json', tmp_path, tmp_path, tmp_path / 'bridge.py', 'task'))
    assert 'private-key' not in ' '.join(argv)
    if harness == 'codex':
        assert f'mcp_servers.{server}.command="/tools/a"' in argv
        assert f'mcp_servers.{server}.env_vars=["A_API_KEY"]' in argv
    else:
        assert 'mcp__' + server in argv[argv.index('--allowedTools') + 1]
        assert 'mcp_servers' not in json.loads(argv[argv.index('--settings') + 1])


@pytest.mark.parametrize('budgets,expected', [(None, 120), ({'solve_seconds': 120, 'command_seconds': 300, 'settlement_seconds': 60, 'evaluation_seconds': 600}, 480)])
def test_command_runner_uses_service_budget_and_retains_last_submission(tmp_path, monkeypatch, budgets, expected):
    calls = []
    created = {'session_id': 'session', 'session_token': 'secret',
               'remaining_seconds': 120, 'limits': {'phase_budgets': budgets} if budgets else {}}
    service = ServiceFixture()
    service.condition = {}
    terminal = service.result('session')
    client = SimpleNamespace(
        session=lambda sid: {'state': 'active', 'remaining_seconds': 120,
                             'budget': {}, 'last_submission': {'candidate': 'accepted'}},
        close=lambda sid, **kw: calls.append('close'), result=lambda sid: terminal,
        observations=service.observations)
    access = SimpleNamespace(endpoint='http://localhost', create=lambda *a, **kw: created)
    monkeypatch.setenv('LAYOUT_BENCH_SESSION', 'unrelated-session')
    monkeypatch.setenv('ICLAYOUT_BENCH_ACCESS_TOKEN', 'unrelated-access')
    monkeypatch.setenv('PYTHONPATH', '/unrelated/source')
    # The documented run_command signature has no seams: replace its HTTP client
    # and child process at the module boundary.
    monkeypatch.setattr(command, 'Client', lambda *a, **kw: client)
    def execute(*args, **kwargs):
        environment = kwargs['env']
        assert all(name not in environment for name in
                   ('LAYOUT_BENCH_SESSION', 'ICLAYOUT_BENCH_ACCESS_TOKEN', 'PYTHONPATH'))
        assert environment['ICLAYOUT_BENCH_SESSION'] == 'session'
        assert environment['ICLAYOUT_BENCH_TOKEN'] == 'secret'
        calls.append(kwargs['timeout'])
        return 0, False
    monkeypatch.setattr(command, 'execute', execute)
    output = tmp_path / 'attempt'
    result = command.run_command(access, 'task', {'command': ['unused'], 'cwd': str(tmp_path),
                                                'condition': {}}, output, creation_key='test')
    assert result == terminal and calls == [expected, 'close']
    record = json.loads((output / 'finalization.json').read_bytes())
    assert record['submission'] == 'retained' and record['receipt'] == {'candidate': 'accepted'}
    assert 'secret' not in (output / 'session.json').read_text()
    assert json.loads((output / 'analysis/result.json').read_text()) == terminal
    assert (output / 'observation/manifest.json').is_file()
