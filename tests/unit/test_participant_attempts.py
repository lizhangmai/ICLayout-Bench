"""One attempt's launch outcome, interruption and explicit collection; no model or EDA."""

import copy
import json
import subprocess
import sys
import time

import pytest
from helpers.participant import (
    InFlightService,
    ServiceFixture,
    attempt_boundaries,
    case_run,
    host_probes,
    in_process,
)

from benchmarking.client import ClientError
from benchmarking.execution.leases import BatchLeaseError, CaseLease
from benchmarking.files import write_json as save
from benchmarking.participants.attempt.recovery import DISABLED
from benchmarking.participants.attempt.runner import (
    attempt_summary,
    run_one,
    run_participant,
    session_mismatch,
)
from benchmarking.participants.attempt.worker import CollectRequest, collect_batch
from benchmarking.participants.cli import main
from benchmarking.participants.harnesses.contracts import ParticipantSelection
from benchmarking.participants.harnesses.scheme import resolve_scheme

pytestmark = pytest.mark.unit


def forbidden(*args, **kwargs):
    pytest.fail('Collection must not resolve, launch or contact a harness or service')


@pytest.mark.parametrize('collect_only', [False, True])
def test_checkpoint_failure_retains_case_recovery_until_explicit_collection(collect_only):
    result = {'state': 'error', 'session_id': 'session', 'failure_category': 'service_failure',
              'failure_reason': 'checkpoint_timeout', 'failure_scope': 'session', 'submission': None,
              'outcome': 'error', 'score': None, 'task_success': None, 'evaluation_mode': 'self_run'}
    summary = attempt_summary({'name': 'condition'}, {}, result, None, None, {}, collect_only=collect_only)
    assert summary['state'] == ('finished' if collect_only else 'suspended')
    assert summary['score'] is None
    assert summary['failure']['scope'] == 'session' and not summary['failure']['stop_dispatch']


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'command'])
def test_failed_harness_drains_execution_before_shared_finalization(tmp_path, harness):
    fixture = InFlightService()
    selected = {'harness': harness, 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': harness, 'task': 'fixture', 'recovery': DISABLED}
    argv = [sys.executable, '-c', 'import sys; print("participant interrupted"); sys.exit(7)']
    if harness == 'command':
        row['scheme'] = resolve_scheme({'version': 'fixture', 'launch': {'command': argv, 'files': []}}, tmp_path, harness)
    output = tmp_path / 'participant'
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}),
                      boundaries=attempt_boundaries(fixture, native_command=lambda context: argv))
    assert summary['state'] == 'finished'
    assert summary['harness_error'] == 'cli_exit_7'
    assert summary['failure']['source'] == 'harness_exit'
    assert not fixture.submitted
    assert fixture.closed == ['fixture-session']
    assert (output / 'analysis/manifest.json').exists()
    finalization = json.loads((output / 'finalization.json').read_text())
    assert finalization['executions']['in-flight']['state'] == 'complete'
    assert finalization['closed'] is True and finalization['error'] is None
    assert (output / 'finalization-in-flight.log').read_bytes() == b'execution finished scoped-fixture-token\n'
    assert all(b'scoped-fixture-token' not in path.read_bytes() for path in (output / 'observation').rglob('*') if path.is_file())


@pytest.mark.parametrize('code,seconds,expected', [
    ('import sys; sys.exit(3)', 90, 'cli_exit_3'),
    ('import time; time.sleep(20)', .1, 'harness_timeout'),
    ('import time; time.sleep(1.1); print("done")', 2, None),
], ids=['failed', 'timed-out', 'completed-without-candidate'])
def test_finished_cli_closes_session_and_exports_independent_result(tmp_path, code, seconds, expected):
    fixture = ServiceFixture()
    fixture.remaining = seconds
    selected = {'harness': 'claude-code', 'model': 'fixture-model', 'effort_resolved': 'xhigh',
                'effort_requested': None, 'effort_source': 'test', 'provider_effective_effort': None}
    output = tmp_path / 'run'
    boundaries = attempt_boundaries(fixture, native_command=lambda context: [sys.executable, '-c', code])
    result, error = run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture', 'recovery': DISABLED},
                                    output, ParticipantSelection(copy.deepcopy(selected), {}, {}), boundaries=boundaries)
    assert error == expected
    assert fixture.closed == ['fixture-session']
    assert result['outcome'] == 'no_submission'  # A completed CLI without a candidate is not a pass.
    assert (output / 'analysis/result.json').exists()
    manifest = json.loads((output / 'observation/manifest.json').read_text())
    assert manifest['participant']['provenance'] == 'participant_reported'
    assert manifest['service']['evaluation_mode'] == 'self_run'
    for name in ('session.json', 'conditions.json', 'harness-summary.json'):
        assert 'scoped-fixture-token' not in (output / name).read_text()


def test_remote_budget_mismatch_closes_before_launch(tmp_path):
    fixture = ServiceFixture()
    original_create = fixture.create
    def mismatched_create(*args, **kwargs):
        response = original_create(*args, **kwargs)
        response['limits']['wall_seconds'] += 1
        return response
    fixture.create = mismatched_create
    launches = []
    boundaries = attempt_boundaries(fixture, native_command=lambda context: launches.append(context) or ['unused'])
    with pytest.raises(ValueError, match='wall_seconds'):
        run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture'}, tmp_path / 'run',
                        ParticipantSelection({'model': 'fixture-model'}, {}, {}), boundaries=boundaries)
    assert not launches
    assert fixture.closed == ['fixture-session']


def created_session(image='pinned-image', hours=1, wall_seconds=3600):
    return {'tool_identity': {'image_id': image}, 'limits': {'wall_seconds': wall_seconds},
            'task': {'description': {'hours': hours}}}


@pytest.mark.parametrize('created,scheme,close_key', [
    (created_session(), {}, None),
    (created_session(), {'solver_image': 'pinned-image'}, None),
    (created_session(image='other-image'), {'solver_image': 'pinned-image'}, 'solver-image-mismatch-close'),
    (created_session(hours=.5), {}, 'budget-mismatch-close'),
    (created_session(hours=True, wall_seconds=3600), {}, 'budget-mismatch-close'),
    (created_session(hours=0, wall_seconds=0), {}, 'budget-mismatch-close'),
    (created_session(hours=float('inf')), {}, 'budget-mismatch-close'),
], ids=['matching', 'declared-image', 'other-image', 'other-budget', 'boolean-hours', 'zero-hours', 'infinite-hours'])
def test_created_session_must_match_frozen_image_and_task_hours(created, scheme, close_key):
    mismatch = session_mismatch(created, scheme)
    assert (mismatch[0] if mismatch else None) == close_key


def test_attempt_export_keeps_distinct_sessions_and_redacts_private_traces(tmp_path):
    from benchmarking.evidence.journal import RunRecorder
    from benchmarking.files import Asset, write_json
    from benchmarking.participants.attempt.evidence import read_attempt_evidence
    from benchmarking.results.package import export_attempts

    runtime = tmp_path / 'attempt'
    participant = runtime / 'participant'
    (participant / '.private').mkdir(parents=True)
    write_json(participant / '.private/recovery.json', {'redactions': ['scoped-secret']})
    (participant / 'harness.jsonl').write_text('{"message":"scoped-secret"}\n')
    for sid in ('first', 'second'):
        recorder = RunRecorder(runtime / 'service/service-store' / sid / 'run')
        candidate = recorder.archive(Asset(sid.encode(), 'gds'))
        check = {'sequence': 1, 'candidate': candidate}
        recorder.save({'candidate': candidate, 'process_feedback': {'checks': [check]}})
    evidence = read_attempt_evidence(runtime)
    original_checks = copy.deepcopy([run.checks[0].record for run in evidence.runs])
    root = tmp_path / 'export'
    files = []
    exported, = export_attempts(root, [evidence], files)
    assert {row['session_id'] for row in exported['sessions']} == {'first', 'second'}
    for row in exported['sessions']:
        assert (root / row['candidate']).read_bytes() == row['session_id'].encode()
        assert (root / row['checks'][0]['candidate']['path']).read_bytes() == row['session_id'].encode()
    assert b'scoped-secret' not in (root / 'attempts/attempt/agent.jsonl').read_bytes()
    assert (participant / 'harness.jsonl').read_bytes() == b'{"message":"scoped-secret"}\n'
    assert [run.checks[0].record for run in evidence.runs] == original_checks


def test_lost_close_reply_recovers_finalization_without_model_relaunch(tmp_path):
    fixture = ServiceFixture()
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'harness': 'claude-code', 'task': 'fixture'}
    output = tmp_path / 'participant'
    close = fixture.close
    def lost(sid, **kwargs):
        close(sid, **kwargs)
        raise ClientError('transport_error', 'response lost')
    launches = []
    boundaries = attempt_boundaries(fixture, native_command=lambda context: launches.append(context) or [
        sys.executable, '-c', 'print("done")'])
    fixture.close = lost
    with pytest.raises(ClientError):
        run_participant(fixture, row, output, ParticipantSelection(selected, {}, {}), boundaries=boundaries)
    fixture.close = close
    result, _ = run_participant(fixture, row, output, ParticipantSelection(selected, {}, {}), boundaries=boundaries)
    assert result['state'] == 'complete'
    assert len(launches) == 1


def test_runner_interruption_is_not_inferred_as_a_model_failure(tmp_path):
    fixture = ServiceFixture()
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': 'claude-code', 'task': 'fixture',
           'recovery': DISABLED | {'resume_session': True}}
    output = tmp_path / 'participant'
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt  # The operator stops the runner while the native process starts.
    with pytest.raises(KeyboardInterrupt):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}),
                boundaries=attempt_boundaries(fixture, execute=interrupted))
    fixture.active = False  # Service subsequently closes under its own deadline.
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}),
                      boundaries=attempt_boundaries(fixture, execute=forbidden))
    assert summary['failure']['category'] == 'unknown'
    assert summary['harness_error'] == 'runner_interrupted'
    assert summary['outcome'] == 'no_submission'  # Independent service evidence is retained.


def test_interrupted_runner_can_collect_without_native_continuation(tmp_path):
    """A command has delivered its candidate; its supervisor dies before cleanup."""
    fixture = InFlightService()
    selected = {'harness': 'command', 'model': 'fixture', 'effort_resolved': None}
    row = {'name': 'trial', 'harness': 'command', 'task': 'fixture',
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    output = tmp_path / 'participant'
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}),
                boundaries=attempt_boundaries(fixture, execute=interrupted))
    assert json.loads((output / '.private/recovery.json').read_text())['phase'] == 'running'
    collection = attempt_boundaries(fixture, execute=forbidden)
    with pytest.raises(ValueError, match='Session continuation was not enabled'):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}), boundaries=collection)
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}), collect_only=True,
                      boundaries=collection)
    assert summary['state'] == 'finished'
    assert summary['harness_error'] == 'runner_interrupted'
    assert fixture.closed == ['fixture-session']
    assert not fixture.submitted  # Keep the already accepted candidate, not mutable output.


@pytest.mark.parametrize('wrong_identity', [False, True])
def test_collect_only_cli_preserves_old_identity_and_never_resolves_harness(tmp_path, wrong_identity):
    fixture = InFlightService()
    selected = {'harness': 'command', 'model': 'fixture', 'effort_resolved': None}
    row = {'name': 'trial', 'harness': 'command', 'model': 'fixture', 'effort': None,
           'tasks': ['fixture'], 'repetitions': 1,
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    batch = tmp_path / 'batch'
    case = batch / 'fixture'
    output = case / '.runtime/participant'
    output.parent.mkdir(parents=True)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_participant(fixture, dict(row, task='fixture'), output, ParticipantSelection(selected, {}, {}),
                        boundaries=attempt_boundaries(fixture, execute=interrupted))
    identity = {'benchmark': {'version': 'old-release', 'commit': 'old-commit'},
                'endpoint': fixture.endpoint, 'plan': [row]}
    (case / 'result.json').write_text(json.dumps({'identity': identity, 'state': 'running'}))
    seams = {'probes': host_probes(resolve=forbidden, harness_version=forbidden),
             'boundaries': in_process(attempt=attempt_boundaries(
                 fixture, native_command=forbidden, execute=forbidden, cli_version=forbidden))}
    if wrong_identity:
        fixture.condition = dict(fixture.condition, model='different-model')
        with pytest.raises(SystemExit) as error:
            main(['--collect-only', '--output', str(batch), '--case', 'fixture'], **seams)
        assert error.value.code == 2
        assert not fixture.closed
        assert json.loads((case / 'result.json').read_text())['state'] == 'running'
    else:
        assert main(['--collect-only', '--output', str(batch), '--case', 'fixture'], **seams) == 1
        final = json.loads((case / 'result.json').read_text())
        assert final['identity'] == identity
        assert final['state'] == 'finished'
        assert final['summary']['harness_error'] == 'runner_interrupted'
        assert not (case / '.runtime').exists()
        assert main(['--collect-only', '--output', str(batch), '--case', 'fixture'], **seams) == 1
        assert fixture.closed == ['fixture-session']


def test_collect_only_commits_existing_terminal_export_without_contacting_service(tmp_path):
    fixture = ServiceFixture()
    row = {'name': 'trial', 'harness': 'command', 'model': 'fixture', 'effort': 'off',
           'tasks': ['fixture'], 'repetitions': 1,
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    case = tmp_path / 'batch/fixture'
    runtime = case / '.runtime'
    runtime.mkdir(parents=True)
    selection = ParticipantSelection({'harness': 'command', 'model': 'fixture', 'effort_resolved': 'off'}, {}, {})
    summary = run_one(fixture, dict(row, task='fixture'), runtime / 'participant', selection,
                      boundaries=attempt_boundaries(fixture))
    summary.update(result='participant/analysis/result.json', task='fixture', directory='fixture', repetition=1)
    identity = {'benchmark': {'version': 'old', 'commit': 'old'}, 'endpoint': None, 'plan': [row]}
    save(runtime / 'summary.json', summary)
    save(case / 'result.json', {'identity': identity, 'state': 'finalizing', 'summary': summary})
    # A committed terminal export needs neither a service nor a model.
    collection = attempt_boundaries(client=forbidden, local_service=forbidden, native_command=forbidden,
                                    execute=forbidden)
    assert main(['--collect-only', '--output', str(tmp_path / 'batch')],
                probes=host_probes(resolve=forbidden), boundaries=in_process(attempt=collection)) == 0
    final = json.loads((case / 'result.json').read_text())
    assert final['state'] == 'finished'
    assert final['identity'] == identity
    assert final['evaluation']['outcome'] == 'no_submission'
    assert not runtime.exists()


@pytest.mark.parametrize('repetitions', [1, 2])
def test_collect_only_waits_for_the_shared_case_lease(tmp_path, repetitions):
    """Collection locks the scheduler's case root, including repeated slots."""
    output = tmp_path / 'batch'
    case_root = output / 'fixture'
    slots = [case_root] if repetitions == 1 else [
        case_root / f'repetition-{index}' for index in range(1, repetitions + 1)]
    identity = {'plan': [{'tasks': ['fixture'], 'repetitions': repetitions}]}
    for slot in slots:
        slot.mkdir(parents=True)
        (slot / 'result.json').write_text(json.dumps({'identity': identity, 'state': 'pending'}))

    script = ('from pathlib import Path; import os, sys, time; '
              'os.fstat(int(sys.argv[3])); '
              'Path(sys.argv[1]).write_text("ready"); time.sleep(float(sys.argv[2]))')
    owners = []
    ready_files = []
    try:
        with CaseLease(case_root) as lease:
            for index in range(repetitions):
                ready = tmp_path / f'owner-{index}.ready'
                ready_files.append(ready)
                hold_seconds = 0.2 if repetitions > 1 and index == 0 else 60
                lease_fd = lease.fileno()
                owners.append(subprocess.Popen(
                    [sys.executable, '-c', script, str(ready), str(hold_seconds), str(lease_fd)],
                    pass_fds=(lease_fd,)))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not all(path.exists() for path in ready_files):
                time.sleep(0.01)
            assert all(path.exists() for path in ready_files)

        # With multiple repetitions, one owner exits while another still holds
        # the inherited scheduler lease. Collection must remain excluded.
        if repetitions > 1:
            assert owners[0].wait(timeout=5) == 0
        with pytest.raises(BatchLeaseError):
            collect_batch(CollectRequest(output, ['fixture']))
    finally:
        for owner in owners:
            if owner.poll() is None:
                owner.terminate()
                owner.wait(timeout=5)


def test_native_mcp_approval_failure_is_not_a_zero_score_and_stops_dispatch(tmp_path):
    """Replay the observed native event via a subprocess, with no model/EDA calls."""
    fixture = ServiceFixture()
    event = {'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'layout',
             'tool': 'read', 'status': 'failed',
             'error': {'message': 'MCP tool call requires approval, but approval policy is never'}}}
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["fixture"]\nconcurrency=1\nrepetitions=2\n')
    selected = {'harness': 'codex', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    launches = []
    attempt = attempt_boundaries(fixture, native_command=lambda context: launches.append(context) or [
        sys.executable, '-c', 'print(' + repr(json.dumps(event)) + ')'])
    seams = {'probes': host_probes(ParticipantSelection(selected, {}, {}),
                                   harness_version=lambda _: ('1.2.3', 'codex 1.2.3')),
             'boundaries': in_process(attempt=attempt)}
    args = ['--config', str(config), '--endpoint', fixture.endpoint, '--output', str(tmp_path / 'batch')]
    assert main(args, **seams) == 1
    records = [json.loads(p.read_text()) for p in sorted(case_run(tmp_path / 'batch', 'fixture').glob('repetition-*/result.json'))]
    summaries = [r['summary'] for r in records]
    first, second = summaries
    assert first['failure']['category'] == 'harness_configuration'
    assert first['failure']['code'] == 'mcp_approval_required'
    assert first['failure']['retryable'] is False
    assert first['outcome'] == 'error'
    assert first['score'] is None and first['task_success'] is None
    raw = records[0]['evaluation']
    assert raw['outcome'] == first['evaluation_result']['outcome'] == 'no_submission'
    assert second['state'] == 'blocked'
    assert main(args + ['--resume'], **seams) == 1
    assert len(launches) == 1
