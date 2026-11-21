"""Same-session continuation after native failures, using real child processes."""

import copy
import json
import signal
import sys

import pytest
from helpers.harness import codex_tool_reply, native_session
from helpers.participant import (
    FakeClock,
    InFlightService,
    ServiceFixture,
    attempt_boundaries,
    case_run,
    host_probes,
    in_process,
    write_dataset,
)

from benchmarking.client import ClientError
from benchmarking.execution.process import execute as actual_execute
from benchmarking.participants.attempt.recovery import (
    DISABLED,
    capacity_delay,
    plan_capacity_resume,
    plan_network_resume,
    policy,
)
from benchmarking.participants.attempt.runner import (
    CONTINUE_PROMPT,
    continuation_kind,
    retain_session,
    run_one,
    run_participant,
)
from benchmarking.participants.cli import main
from benchmarking.participants.harnesses.contracts import ParticipantSelection

pytestmark = pytest.mark.unit


def within_jitter(delays, bases):
    """Documented waits: an exponential base with up to 20% positive jitter, within the cap."""
    return len(delays) == len(bases) and all(base <= delay <= base * 1.2 for delay, base in zip(delays, bases))


@pytest.mark.parametrize('kind', ['capacity', 'network'])
@pytest.mark.parametrize('scenario,expected', [
    ('ready', 'waiting'), ('limit', 'limit_reached'), ('disabled', 'limit_reached'),
    ('closed', 'deadline'), ('expired', 'deadline'), ('missing_native', 'native_session_missing'),
    ('retry_after', 'retry_after_exceeds_cap'), ('insufficient_budget', 'deadline'),
])
def test_resume_policy_bounds_waiting_without_changing_session(kind, scenario, expected):
    settings = policy({kind + '_resumes': 0 if scenario == 'disabled' else 2})
    status = {'state': 'complete' if scenario == 'closed' else 'active',
              'remaining_seconds': 0 if scenario == 'expired' else 20 if scenario == 'insufficient_budget' else 1000}
    problem = {'retry_after': 400} if scenario == 'retry_after' else {}
    native_id = None if scenario == 'missing_native' else 'original-native-thread'
    before = copy.deepcopy((settings, status, problem))
    plan = {'capacity': plan_capacity_resume, 'network': plan_network_resume}[kind]
    decision = plan(
        settings, 2 if scenario == 'limit' else 0, problem, status, native_id)
    assert decision.outcome == expected
    assert (settings, status, problem) == before
    if scenario == 'ready':
        assert decision.native_id == native_id and within_jitter([decision.delay_seconds], [30])


def test_capacity_delay_is_bounded_and_respects_exponential_intervals():
    settings = policy(DISABLED | {'capacity_resumes': 5})
    # Defaults: a 30-second initial wait doubles per resume and is capped at 300 seconds.
    for resumes, base in enumerate([30, 60, 120, 240, 300]):
        delays = [capacity_delay(settings, resumes) for _ in range(100)]
        assert within_jitter(delays, [base] * 100) and max(delays) <= 300


def event(category, source='harness_event', retryable=True):
    return {'category': category, 'source': source, 'retryable': retryable}


@pytest.mark.parametrize('settings,problem,exit_code,expected', [
    ({}, None, 1, None),
    ({}, event('provider_overloaded', 'harness_exit', False), 0, 'capacity'),
    ({'capacity_resumes': 0}, event('provider_overloaded'), 1, None),
    ({}, event('rate_limit'), 1, 'capacity'),
    ({'resume_session': False, 'network_resumes': 0}, event('rate_limit'), 1, None),
    ({}, event('rate_limit', retryable=False), 1, None),
    ({}, event('rate_limit', source='harness_exit'), 1, None),
    ({}, event('network_transient'), 1, 'network'),
    ({}, event('network_transient'), 0, None),
    ({}, event('network_transient'), -signal.SIGTERM, None),
    ({'network_resumes': 0}, event('network_transient'), 1, None),
    ({}, event('quota_exhausted', retryable=False), 1, None),
])
def test_only_recognized_transient_exits_continue_automatically(settings, problem, exit_code, expected):
    assert continuation_kind(policy(settings), problem, exit_code) == expected


@pytest.mark.parametrize('error,problem,exit_code,interrupted,resume,expected', [
    (None, None, 0, False, True, False),
    ('cli_exit_1', event('quota_exhausted', retryable=False), 1, False, True, True),
    ('cli_exit_1', event('quota_exhausted', retryable=False), 1, False, False, False),
    ('harness_timeout', None, None, False, True, False),
    ('harness_configuration', event('harness_configuration', retryable=False), 0, False, True, False),
    ('cli_exit_1', event('provider_overloaded'), 1, True, True, False),
    ('cli_exit_1', event('rate_limit'), 1, True, True, True),
    ('cli_exit_1', event('network_transient'), 1, True, True, True),
    ('cli_exit_-15', None, -signal.SIGTERM, True, True, True),
    ('cli_exit_143', None, 128 + signal.SIGTERM, True, True, True),
])
def test_failed_attempt_retains_session_only_for_explicit_continuation(
        error, problem, exit_code, interrupted, resume, expected):
    settings = policy({'resume_session': resume} | ({} if resume else {'network_resumes': 0}))
    assert retain_session(settings, error, problem, exit_code, capacity_interrupted=interrupted) is expected


@pytest.mark.parametrize('kind,harness,scenario', [
    *[('capacity', harness, 'success') for harness in ('codex', 'claude-code', 'zcode')],
    ('network', 'claude-code', 'success'),
    *[('capacity', 'codex', scenario) for scenario in (
        'limit', 'active_execution', 'active_after_wait', 'pending_tool', 'pending_after_wait',
        'delivered_tool', 'undelivered_tool', 'authentication', 'service_error', 'rotated_credentials')],
    *[('network', 'codex', scenario) for scenario in (
        'success', 'limit', 'active_execution', 'active_after_wait', 'pending_tool', 'pending_after_wait',
        'authentication', 'quota', 'mixed_failure', 'successful_exit', 'disabled', 'resume_disabled', 'deadline')],
])
def test_native_continuation_preserves_session_budget_and_evidence(tmp_path, kind, harness, scenario):
    """Shared recovery runs real child processes; adapters own native error variants."""
    active_execution = scenario in {'active_execution', 'active_after_wait'}
    delivery = scenario if scenario in {'delivered_tool', 'undelivered_tool'} else None
    stop = 'success' if active_execution or delivery or scenario in {
        'pending_tool', 'pending_after_wait', 'rotated_credentials'} else scenario
    fixture = InFlightService() if active_execution or (kind == 'network' and stop == 'limit') else ServiceFixture()
    if scenario == 'active_after_wait' or stop == 'limit':
        fixture.busy = False
    fixture.remaining = 1000
    output = tmp_path / 'participant'
    selected = {'harness': harness, 'model': 'fixture-model', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': harness, 'task': 'fixture'}
    if stop != 'success':
        row['recovery'] = {kind + '_resumes': 2}
        if kind == 'capacity':
            row['recovery'] |= DISABLED | {'resume_session': stop in {'limit', 'service_error'}}
    if stop == 'disabled':
        row['recovery'][kind + '_resumes'] = 0
    if stop == 'resume_disabled':
        row['recovery']['resume_session'] = False
    launches, prompts, timeouts = [], [], []
    manually_recovered = [False]

    def pending_tool():
        (output / 'tools.jsonl').write_text(json.dumps({'tool': 'execute', 'mutation': True,
            'key': 'unanswered', 'arguments': {'command': 'native tool'}}) + '\n')

    def launch(context):
        env = context.selection.environment
        assert fixture.active and context.selection.condition == selected
        if harness == 'zcode':
            env['ZCODE_DATA_BASE_DIR'] = str(output / '.private/native-home')
        launches.append(dict(env))
        native_id = ('sess_' if harness == 'zcode' else '') + env['ICLAYOUT_BENCH_NATIVE_ID']
        native_session(output, harness, native_id)
        if len(launches) > 1 and (active_execution or manually_recovered[0]):
            assert fixture.busy, 'Continuation must not drain the existing execution'
            assert not (output / 'finalization.json').exists()
        failing = not manually_recovered[0] and (len(launches) == 1 or stop == 'limit')
        events = [{'type': 'thread.started', 'thread_id': native_id}]
        if failing:
            if kind == 'network':
                event = {'type': 'turn.failed', 'error': {'code': 'connection_error'}}
            else:
                event = {
                    'codex': {'type': 'turn.failed', 'error': {'code': 'server_is_overloaded'}},
                    'claude-code': {'type': 'error', 'error': {'type': 'overloaded_error'}},
                    'zcode': {'type': 'turn.failed', 'payload': {'error': {
                        'code': '1312', 'attribution': {'source': 'provider'}}}},
                }[harness]
            events.append(event)
        elif stop in {'authentication', 'quota'}:
            events.append({'type': 'turn.failed', 'error': {
                'code': 'invalid_api_key' if stop == 'authentication' else 'insufficient_quota'}})
        else:
            events.append({'type': 'turn.completed'})
        if stop == 'mixed_failure':
            events.append({'type': 'error', 'error': {'code': 'unrecognized_failure'}})
        if len(launches) == 1:
            if scenario == 'pending_tool':
                pending_tool()
            if delivery:
                arguments = {'command': 'fixture-command', 'wait_seconds': 10}
                result = {'execution_id': 'fixture-execution', 'state': 'running', 'next_offset': 0}
                request = {'tool': 'execute', 'arguments': arguments, 'mutation': True, 'key': 'fixture-mutation'}
                reply = {'tool': 'execute', 'key': request['key'], 'result': result}
                (output / 'tools.jsonl').write_text(json.dumps(request) + '\n' + json.dumps(reply) + '\n')
                native = codex_tool_reply(native_id, 'execute', arguments, result)
                if delivery == 'undelivered_tool':
                    native.pop()
                history = next((output / '.private/native-home/sessions').rglob('*.jsonl'))
                with history.open('a') as stream:
                    stream.write(''.join(json.dumps(event) + '\n' for event in native))
        rotate = ''
        if scenario == 'rotated_credentials':
            secret = f'rotated-native-secret-{len(launches)}'
            credential = output / '.private/native-home/auth.json'
            rotate = f'Path({str(credential)!r}).write_text({json.dumps({"access_token": secret})!r}); print({secret!r}); '
        exit_code = 0 if stop == 'successful_exit' else int(failing or stop in {'authentication', 'quota'})
        raw = '\n'.join(json.dumps(event) for event in events)
        return [sys.executable, '-c',
                f'import sys; from pathlib import Path; {rotate}print({raw!r}); sys.exit({exit_code})']

    def execute(*args, **kwargs):
        prompts.append(kwargs['prompt'])
        timeouts.append(kwargs['timeout'])
        return actual_execute(*args, **kwargs)

    def waited(seconds):
        fixture.remaining = 0 if stop == 'deadline' else fixture.remaining - seconds
        if active_execution:
            fixture.busy = True
        if scenario == 'pending_after_wait':
            pending_tool()

    original_session = fixture.session
    service_error = []
    def session(sid):
        if stop == 'service_error' and prompts and not service_error:
            service_error.append(True)
            raise ClientError('transport_error', 'Connection interrupted')
        return original_session(sid)

    fixture.session = session
    clock = FakeClock(on_sleep=waited)
    delays = clock.delays
    boundaries = attempt_boundaries(fixture, native_command=launch, execute=execute, clock=clock)
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}), boundaries=boundaries)
    assert len(fixture.creations) == 1
    assert summary['session_id'] == 'fixture-session'
    assert len(launches) == (3 if stop == 'limit' else 2 if stop in {'success', 'authentication', 'quota'} else 1)
    for env in launches:
        assert env['ICLAYOUT_BENCH_SESSION'] == 'fixture-session'
    for env in launches[1:]:
        native_id = ('sess_' if harness == 'zcode' else '') + launches[0]['ICLAYOUT_BENCH_NATIVE_ID']
        assert env['ICLAYOUT_BENCH_RESUME_ID'] == native_id
        assert env['ICLAYOUT_BENCH_TOKEN'] == launches[0]['ICLAYOUT_BENCH_TOKEN']
        home = {'codex': 'CODEX_HOME', 'claude-code': 'CLAUDE_CONFIG_DIR', 'zcode': 'ZCODE_DATA_BASE_DIR'}[harness]
        assert env[home] == launches[0][home]
    assert all(prompt == CONTINUE_PROMPT for prompt in prompts[1:])
    # Each continuation consumes the original deadline by the preceding wait.
    assert timeouts == pytest.approx([1000 - sum(delays[:index]) for index in range(len(launches))])
    key = kind + '_recovery'
    if stop in {'disabled', 'resume_disabled', 'mixed_failure', 'successful_exit'}:
        assert key not in summary and not delays
    else:
        recovery = summary[key]
        assert recovery['outcome'] == {
            'success': 'recovered', 'limit': 'limit_reached', 'deadline': 'deadline',
            'authentication': 'stopped_on_other_error', 'quota': 'stopped_on_other_error',
            'service_error': 'stopped_on_other_error'}[stop]
        assert len(recovery['interruptions']) == (3 if stop == 'limit' else 1)
        assert all(entry.get('status') for entry in recovery['interruptions'])
    suspended = stop == 'service_error' or (kind == 'network' and stop not in {'success', 'resume_disabled'})
    assert summary['state'] == ('suspended' if suspended else 'finished')
    assert fixture.closed == ([] if suspended else ['fixture-session'])
    assert (output / 'launch-1-harness.jsonl').exists() == (len(launches) > 1)
    if active_execution:
        assert json.loads((output / 'finalization.json').read_text())['executions']['in-flight']['state'] == 'complete'
        assert not fixture.submitted
    if stop == 'success':
        assert summary['harness_error'] is None and within_jitter(delays, [30])
        assert summary['failure']['category'] == 'task_failure'
    if scenario == 'rotated_credentials':
        for path in (output / 'observation').rglob('*'):
            if path.is_file():
                assert b'rotated-native-secret-1' not in path.read_bytes()
                assert b'rotated-native-secret-2' not in path.read_bytes()
        assert b'rotated-native-secret-1' in (output / 'launch-1-harness.jsonl').read_bytes()
    if kind == 'network' and stop == 'limit':
        assert within_jitter(delays, [30, 60]) and summary[key]['resumes'] == 2
        assert (output / '.private/recovery.json').is_file()
        manually_recovered[0] = True
        fixture.remaining, fixture.busy = 30, True
        resumed = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}), boundaries=boundaries)
        assert len(fixture.creations) == 1 and resumed['state'] == 'finished'
        assert resumed[key]['outcome'] == 'recovered' and timeouts[-1] == 30


def test_local_capacity_recovery_exports_both_launches_before_removing_runtime(tmp_path):
    dataset = write_dataset(tmp_path / 'dataset', ['fixture'])
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture-model"\neffort="xhigh"\n'
                      'tasks=["fixture"]\nconcurrency=1\nrepetitions=1\n')
    fixture = ServiceFixture()
    launches = []
    selected = {'harness': 'codex', 'model': 'fixture-model', 'effort_resolved': 'xhigh', 'effort_requested': 'xhigh'}

    def launch(context):
        env = context.selection.environment
        launches.append(dict(env))
        native_session(context.output, 'codex', 'original-thread')
        event = ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}
                 if len(launches) == 1 else {'type': 'turn.completed'})
        thread = json.dumps({'type': 'thread.started', 'thread_id': 'original-thread'})
        return [sys.executable, '-c', f'import sys; print({thread!r}); print({json.dumps(event)!r}); sys.exit({int(len(launches) == 1)})']

    def waited(seconds):
        fixture.remaining -= seconds

    clock = FakeClock(on_sleep=waited)
    probes = host_probes(ParticipantSelection(selected, {'CODEX_HOME': str(tmp_path / 'caller-home')}, {}))
    attempt = attempt_boundaries(fixture, native_command=launch, clock=clock)
    batch = tmp_path / 'batch'
    assert main(['--config', str(config), '--dataset', str(dataset), '--output', str(batch)],
                probes=probes, boundaries=in_process(attempt=attempt)) == 0
    case = case_run(batch, 'fixture')
    result = json.loads((case / 'result.json').read_text())
    assert result['state'] == 'finished'
    assert result['execution']['capacity_recovery']['outcome'] == 'recovered'
    assert within_jitter(clock.delays, [30])
    assert result['execution']['elapsed_seconds'] == round(clock.delays[0], 3)
    assert result['execution']['failure'] is None
    assert not (case / '.runtime').exists()
    trace = [json.loads(line) for line in (case / 'agent.jsonl').read_text().splitlines()]
    assert [event['type'] for event in trace] == ['thread.started', 'error', 'thread.started', 'turn.completed']
    assert launches[1]['ICLAYOUT_BENCH_RESUME_ID'] == 'original-thread'
    assert fixture.closed == ['fixture-session']
    assert b'scoped-fixture-token' not in (case / 'agent.jsonl').read_bytes()


@pytest.mark.parametrize('harness,service_restarted', [
    ('codex', False), ('codex', True), ('claude-code', False),
])
def test_same_session_resume_preserves_budget_and_private_credentials(tmp_path, service_restarted, harness):
    fixture = ServiceFixture()
    selected = {'harness': harness, 'model': 'fixture-model', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': harness, 'task': 'fixture'}
    output = tmp_path / 'participant'
    events = json.dumps({'type': 'error', 'error': {'code': 'insufficient_quota'}})
    observed = []
    prompts = []
    def launch(context):
        env = context.selection.environment
        observed.append(dict(env))
        prompts.append(context.prompt)
        native_session(output, harness, env['ICLAYOUT_BENCH_NATIVE_ID'])
        if len(observed) == 1:
            thread = json.dumps({'type': 'thread.started', 'thread_id': env['ICLAYOUT_BENCH_NATIVE_ID']})
            return [sys.executable, '-c', f'import sys; print({thread!r}); print({events!r}); sys.exit(1)']
        return [sys.executable, '-c', 'import os; print(os.environ["ICLAYOUT_BENCH_TOKEN"]); print(os.environ["PROVIDER_API_KEY"])']
    boundaries = attempt_boundaries(fixture, native_command=launch)
    first = run_one(fixture, row, output, ParticipantSelection(selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}),
                    boundaries=boundaries)
    assert first['state'] == 'suspended'
    assert first['failure']['category'] == 'quota_exhausted'
    assert fixture.closed == []
    fixture.remaining = 30  # Human billing wait did not reset the service clock.
    if service_restarted:
        original_status = fixture.session
        fixture.session = lambda sid: dict(original_status(sid), recovery={
            'workspace_restored': True, 'interrupted_executions': ['interrupted-command']})
        (output / 'tools.jsonl').write_text(json.dumps({'tool': 'write', 'mutation': True,
            'key': 'interrupted-write', 'arguments': {'path': 'saved.py', 'content': 'content'}}) + '\n')
    second = run_one(fixture, row, output, ParticipantSelection(selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}),
                     boundaries=boundaries)
    assert len(fixture.creations) == 1
    assert second['state'] == 'finished'
    assert observed[1]['ICLAYOUT_BENCH_RESUME_ID'] == observed[0]['ICLAYOUT_BENCH_NATIVE_ID']
    if service_restarted:
        assert 'interrupted-write' in (output / 'tools.jsonl').read_text()
        assert 'interrupted-command' in prompts[1] and 'rolled back' in prompts[1]
    assert (output / 'launch-1-harness.jsonl').exists()
    # A repeated collection must not re-launch or overwrite finished exports.
    run_participant(fixture, row, output, ParticipantSelection(selected, {}, {}), boundaries=boundaries)
    assert len(observed) == 2
    for path in (output / 'observation').rglob('*'):
        if path.is_file():
            assert b'scoped-fixture-token' not in path.read_bytes()
            assert b'fixture-api-secret' not in path.read_bytes()
    assert b'fixture-api-secret' in (output / 'harness.jsonl').read_bytes()  # Original evidence is preserved.
    assert (output / '.private/recovery.json').stat().st_mode & 0o777 == 0o600
