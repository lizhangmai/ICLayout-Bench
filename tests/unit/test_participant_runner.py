"""Native runner lifecycle tests use subprocess fixtures, never a model provider."""
import copy
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarking.client import ClientError
from benchmarking.participants.adapters.contracts import (
    HARNESSES,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.runner import run_participant
from benchmarking.protocol import PROTOCOL, USAGE_FIELDS

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def external_runtime_boundaries(monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.case import execute_owned_slot
    monkeypatch.setattr("benchmarking.participants.worker.supervise_slot", execute_owned_slot)
    monkeypatch.setattr("benchmarking.participants.planning.DockerSession", lambda image: SimpleNamespace(image_id=image))
    monkeypatch.setattr("benchmarking.participants.planning.harness_version", lambda _: ("1.2.3", "fixture-cli 1.2.3"))


def write_dataset(root, names):
    from helpers.protocol import write_protocol_task
    for name in names:
        config = write_protocol_task(root / 'tasks' / name.split('.')[0] / 'fixture/cases' / name)
        (config.parent / 'case.toml').write_text(config.read_text().replace('protocol-test', name))
        process = root / 'tasks' / name.split('.')[0]
        process.mkdir(parents=True, exist_ok=True)
        (process / 'pdk.toml').write_text('id="fixture"\n')
    return root


class ServiceFixture:
    endpoint = 'http://127.0.0.1:8765'

    def __init__(self):
        self.remaining = 120
        self.active = True
        self.closed = []
        self.condition = None

    def create(self, task, condition, *, key):
        self.condition = condition
        return {'session_id': 'fixture-session', 'session_token': 'scoped-fixture-token',
                'limits': {'wall_seconds': self.remaining, 'max_command_seconds': self.remaining},
                'task': {'description': {'hours': self.remaining / 3600, 'output': {'path': '/workspace/output/final.gds'}}}}

    def session(self, sid):
        return {'state': 'active' if self.active else 'complete', 'remaining_seconds': self.remaining}

    def submit(self, *args, **kwargs):
        raise ClientError('invalid_request', 'No candidate', status=400)

    def close(self, sid, *, key):
        self.closed.append(sid)
        self.active = False

    def observations(self, sid, *, offset=0):
        return {'session_id': sid, 'provenance': 'server_observed', 'available': True,
                'events': [], 'next_offset': 0, 'has_more': False}

    def result(self, sid):
        return {
            'protocol': PROTOCOL, 'state': 'complete', 'session_id': sid,
            'task_id': 'fixture', 'task_sha256': '0' * 64,
            'condition': self.condition, 'submission': None,
            'outcome': 'no_submission', 'task_success': False, 'failure_reason': None,
            'score': None, 'metrics': {}, 'usage': dict.fromkeys(USAGE_FIELDS),
            'tool_identity': {}, 'limits': {}, 'provenance': {},
            'evaluation_mode': 'self_run',
        }


def terminal_files(output, outcome='no_submission'):
    (output / 'analysis').mkdir(parents=True, exist_ok=True)
    result = ServiceFixture().result('fixture-session')
    result['outcome'] = outcome
    (output / 'analysis/result.json').write_text(json.dumps(result))
    return {'outcome': outcome, 'result': 'analysis/result.json'}


class InFlightService(ServiceFixture):
    """A protocol execution survives the participant; enforce the real service guard."""
    def __init__(self, *, race=False, conflict=False):
        super().__init__()
        self.busy = not race and not conflict
        self.race, self.conflict = race, conflict
        self.submitted = []

    def session(self, sid):
        return dict(super().session(sid), active_execution_id='in-flight' if self.busy else None)

    def poll(self, sid, eid, *, offset=0):
        import base64
        assert eid == 'in-flight'
        self.busy = False
        raw = b'execution finished scoped-fixture-token\n' if offset == 0 else b''
        return {'execution_id': eid, 'state': 'complete', 'exit_code': 0,
                'log_base64': base64.b64encode(raw).decode(), 'next_offset': offset + len(raw), 'truncated': False}

    def submit(self, sid, path, *, key):
        import time

        from benchmarking.service.contracts import APIError
        from benchmarking.service.controller import SessionController
        self.submitted.append((path, key))
        if self.race:
            self.busy, self.race = True, False
        if self.conflict:
            raise ClientError('conflict', 'Idempotency key conflict', status=409)
        service = object.__new__(SessionController)
        service._status = lambda _: self.session(sid)
        try:
            service._active({'deadline_epoch': time.time() + 60}, idle=True)
        except APIError as exc:
            raise ClientError(exc.code, str(exc), status=exc.status) from exc
        return {'submission_id': 'accepted', 'sequence': 1, 'size_bytes': 10}


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'command'])
def test_failed_harness_drains_execution_before_shared_finalization(tmp_path, monkeypatch, harness):
    import sys

    from benchmarking.participants.runner import run_one
    from benchmarking.participants.scheme import resolve_scheme

    fixture = InFlightService()
    selected = {'harness': harness, 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': harness, 'task': 'fixture'}
    argv = [sys.executable, '-c', 'import sys; print("participant interrupted"); sys.exit(7)']
    if harness == 'command':
        row['scheme'] = resolve_scheme({'version': 'fixture', 'launch': {'command': argv, 'files': []}}, tmp_path, harness)
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.adapters.prepare', lambda *a: argv)
    output = tmp_path / 'participant'
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    assert summary['state'] == 'finished'
    assert summary['harness_error'] == 'cli_exit_7'
    assert summary['failure']['source'] == 'harness_exit'
    assert fixture.submitted == [('output/final.gds', 'runner-final-submit')]
    assert fixture.closed == ['fixture-session']
    assert (output / 'analysis/manifest.json').exists()
    finalization = json.loads((output / 'finalization.json').read_text())
    assert finalization['executions']['in-flight']['state'] == 'complete'
    assert finalization['closed'] is True and finalization['error'] is None
    assert (output / 'finalization-in-flight.log').read_bytes() == b'execution finished scoped-fixture-token\n'
    assert all(b'scoped-fixture-token' not in path.read_bytes() for path in (output / 'observation').rglob('*') if path.is_file())


def test_finalization_reconciles_execution_race_with_same_submission_key(tmp_path):
    from benchmarking.participants.runner import finalize_session
    fixture = InFlightService(race=True)
    fixture.condition = {}
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    created = {'task': {'description': {'output': {'path': '/workspace/output/final.gds'}}}}
    result = finalize_session(fixture, 'fixture-session', created, tmp_path)
    assert result['state'] == 'complete'
    assert fixture.submitted == [('output/final.gds', 'runner-final-submit')] * 2
    assert fixture.closed == ['fixture-session']


def test_finalization_wait_obeys_deadline_and_retains_accepted_candidate(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.runner import finalize_session
    fixture = InFlightService()
    fixture.condition = {}
    fixture.remaining = 1
    receipt = {'submission_id': 'earlier', 'sequence': 1, 'candidate_sha256': 'a' * 64}
    original_result = fixture.result
    fixture.result = lambda sid: dict(original_result(sid), submission=receipt, outcome='pass', score={'value': 83, 'method': 'layout', 'maximum': 100, 'reference': 100})
    fixture.poll = lambda sid, eid, offset=0: {'execution_id': eid, 'state': 'running', 'exit_code': None,
                                            'log_base64': '', 'next_offset': offset, 'truncated': False}
    clock = [0]
    def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr('benchmarking.participants.lifecycle.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    created = {'task': {'description': {'output': {'path': '/workspace/output/final.gds'}}}}
    result = finalize_session(fixture, 'fixture-session', created, tmp_path)
    assert clock[0] == 1
    assert not fixture.submitted
    assert fixture.closed == ['fixture-session']
    assert result['submission'] == receipt and result['score']['value'] == 83
    assert json.loads((tmp_path / 'finalization.json').read_text())['submission'] == 'deadline'


def test_finalization_keeps_primary_error_when_close_also_fails(tmp_path, monkeypatch):
    from benchmarking.participants.runner import finalize_session
    fixture = InFlightService(conflict=True)
    def close(*a, **kw):
        raise ClientError('transport_error', 'response lost')
    monkeypatch.setattr(fixture, 'close', close)
    created = {'task': {'description': {'output': {'path': '/workspace/output/final.gds'}}}}
    with pytest.raises(ClientError) as caught:
        finalize_session(fixture, 'fixture-session', created, tmp_path)
    assert caught.value.code == 'conflict'
    evidence = json.loads((tmp_path / 'finalization.json').read_text())
    assert evidence['error']['code'] == 'conflict'
    assert evidence['close_error']['code'] == 'transport_error'
    assert not evidence['closed']


@pytest.mark.parametrize('failure_code', ['conflict', 'infrastructure_error', 'result_transport'])
def test_unrelated_finalization_conflict_retains_original_harness_failure(tmp_path, monkeypatch, failure_code):
    import sys

    from benchmarking.run import main
    fixture = InFlightService(conflict=failure_code != 'result_transport')
    tasks = ['fixture', 'untouched'] if failure_code == 'infrastructure_error' else ['fixture']
    if failure_code == 'infrastructure_error':
        def submit(sid, path, *, key):
            fixture.submitted.append((path, key))
            raise ClientError(failure_code, 'service unavailable', status=500)
        monkeypatch.setattr(fixture, 'submit', submit)
    if failure_code == 'result_transport':
        def result(sid):
            raise ClientError('transport_error', 'response lost')
        monkeypatch.setattr(fixture, 'result', result)
    config = tmp_path / 'trial.toml'
    config.write_text('harness="claude-code"\nmodel="fixture"\neffort="high"\n'
                      f'tasks={json.dumps(tasks)}\nconcurrency=1\nrepetitions=1\n')
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *a: ParticipantSelection(selected, {}, {}))
    monkeypatch.setattr('benchmarking.participants.local_service.service', lambda *a: nullcontext(fixture))
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.adapters.prepare', lambda *a: [sys.executable, '-c', 'import sys; sys.exit(7)'])
    dataset = write_dataset(tmp_path / 'dataset', tasks)
    output = tmp_path / 'batch'
    assert main(['--config', str(config), '--dataset', str(dataset), '--output', str(output)]) == 1
    result = json.loads((output / 'fixture/fixture/cases/fixture/result.json').read_text())
    assert result['summary']['harness_error'] == 'cli_exit_7'
    assert result['summary']['failure']['source'] == 'harness_exit'
    assert result['summary']['finalization_error']['failure']['code'] == ('transport_error' if failure_code == 'result_transport' else failure_code)
    assert len(fixture.submitted) == 1
    assert fixture.closed == ['fixture-session']
    if len(tasks) > 1:
        assert json.loads((output / 'untouched/fixture/cases/untouched/result.json').read_text())['state'] == 'blocked'


class LifecycleTests(unittest.TestCase):
    def exercise(self, code, seconds):
        import sys
        fixture = ServiceFixture()
        fixture.remaining = seconds
        selected = {'harness': 'claude-code', 'model': 'fixture-model', 'effort_resolved': 'xhigh',
                    'effort_requested': None, 'effort_source': 'test', 'provider_effective_effort': None}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            with patch('benchmarking.participants.runner.Client', return_value=fixture), \
                    patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'), \
                    patch('benchmarking.participants.adapters.prepare', return_value=[sys.executable, '-c', code]):
                result, error = run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture'}, output, ParticipantSelection(copy.deepcopy(selected), {}, {}))
            self.assertEqual(fixture.closed, ['fixture-session'])
            self.assertEqual(result['outcome'], 'no_submission')
            self.assertTrue((output / 'analysis/result.json').exists())
            manifest = json.loads((output / 'observation/manifest.json').read_text())
            self.assertEqual(manifest['participant']['provenance'], 'participant_reported')
            self.assertEqual(manifest['service']['evaluation_mode'], 'self_run')
            for name in ('session.json', 'conditions.json', 'harness-summary.json'):
                self.assertNotIn('scoped-fixture-token', (output / name).read_text())
            return error

    def test_failed_cli_still_closes_and_exports_result(self):
        self.assertEqual(self.exercise('import sys; sys.exit(3)', 90), 'cli_exit_3')

    def test_timed_out_cli_still_closes_and_exports_result(self):
        self.assertEqual(self.exercise('import time; time.sleep(20)', .1), 'harness_timeout')

    def test_completed_cli_without_candidate_is_not_a_pass(self):
        self.assertIsNone(self.exercise('import time; time.sleep(1.1); print("done")', 2))

    def test_remote_budget_mismatch_closes_before_launch(self):
        fixture = ServiceFixture()
        original_create = fixture.create
        def mismatched_create(*args, **kwargs):
            response = original_create(*args, **kwargs)
            response['limits']['wall_seconds'] += 1
            return response
        fixture.create = mismatched_create
        with tempfile.TemporaryDirectory() as directory, \
                patch('benchmarking.participants.runner.Client', return_value=fixture), \
                patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'), \
                patch('benchmarking.participants.adapters.prepare') as launch:
            with self.assertRaisesRegex(ValueError, 'wall_seconds'):
                run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture'}, Path(directory) / 'run', ParticipantSelection({'model': 'fixture-model'}, {}, {}))
            launch.assert_not_called()
            self.assertEqual(fixture.closed, ['fixture-session'])

    def test_default_batch_groups_local_and_remote_outputs_per_run(self):
        import sys

        from benchmarking.run import main
        for local in (False, True):
            with self.subTest(local=local), tempfile.TemporaryDirectory() as directory:
                batch = Path(directory) / 'results/generated'
                write_dataset(Path(directory), ["fixture"])
                config = Path(directory) / 'trial.toml'
                config.write_text('harness="claude-code"\nmodel="fixture-model"\ntasks=["fixture"]\nconcurrency=1\neffort="high"\nrepetitions=1\n')
                case_path = 'fixture/fixture/cases/fixture' if local else 'fixture'
                fixture = ServiceFixture()
                fixture.remaining = 3 * 3600
                selected = ParticipantSelection({'harness': 'claude-code', 'model': 'fixture-model',
                             'effort_resolved': 'high', 'effort_requested': None}, {}, {})

                def local_service(prepared, output, image, batch=batch, fixture=fixture, case_path=case_path):
                    self.assertEqual(output, batch / case_path / '.runtime/service')
                    (output / 'service.log').write_text('fixture service')
                    return nullcontext(fixture)

                with patch('benchmarking.participants.planning.default_output', return_value=batch), \
                        patch('benchmarking.participants.planning.resolve', return_value=selected), \
                        patch('benchmarking.participants.case.Client', return_value=fixture), \
                        patch('benchmarking.participants.local_service.service', side_effect=local_service), \
                        patch('benchmarking.participants.runner.Client', return_value=fixture), \
                        patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli 1.2.3'), \
                        patch('benchmarking.participants.adapters.prepare', return_value=[sys.executable, '-c', 'print("done")']), \
                        patch.dict('os.environ', {'ICLAYOUT_BENCH_ENDPOINT': ''}), \
                        patch('builtins.print'):
                    mode = ['--dataset', directory] if local else ['--endpoint', fixture.endpoint]
                    code = main(['--config', str(config), *mode])
                self.assertEqual(code, 0)
                result = json.loads((batch / case_path / 'result.json').read_text())
                self.assertEqual(result['summary']['directory'], case_path)
                self.assertEqual(result['evaluation']['outcome'], 'no_submission')
                self.assertTrue((batch / case_path / 'agent.jsonl').exists())
                self.assertFalse((batch / case_path / '.runtime').exists())
                self.assertFalse((batch / 'fixture-local').exists())

    def test_remote_rejects_local_budget_override(self):
        from benchmarking.run import main
        with patch('sys.stderr'), self.assertRaises(SystemExit) as raised:
            main(['--harness', 'codex', '--model', 'fixture', '--seconds', '60', '--dry-run'])
        self.assertEqual(raised.exception.code, 2)

    def test_matrix_keeps_failure_and_runs_next_combination(self):
        from benchmarking.run import main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix = root / 'matrix.toml'
            matrix.write_text('[defaults]\ntasks=["test"]\nconcurrency=1\nharness="claude-code"\nmodel="test"\neffort="high"\nrepetitions=1\n'
                              '[[runs]]\nname="first"\nmodel="first"\n[[runs]]\nname="second"\nmodel="second"\n')
            selection = ParticipantSelection({'harness': 'claude-code', 'model': 'test', 'effort_resolved': None}, {}, {})
            def run(access, row, out, selected):
                if row['name'].startswith('first'):
                    raise RuntimeError('fixture failure')
                return terminal_files(out)
            with patch('benchmarking.participants.planning.default_output', side_effect=lambda group: root / Path(group).name), \
                    patch('benchmarking.participants.planning.harness_version', return_value=('1.2.3', 'fixture 1.2.3')), \
                    patch('benchmarking.participants.planning.resolve', return_value=selection), \
                    patch('benchmarking.participants.runner.run_one', side_effect=run), \
                    patch.dict('os.environ', {'ICLAYOUT_BENCH_TOKEN': 'fixture-token'}), \
                    patch('builtins.print'):
                code = main(['--matrix', str(matrix), '--endpoint', 'http://127.0.0.1:8765'])
            self.assertEqual(code, 1)
            summary = [json.loads(p.read_text())['summary'] for p in sorted(root.glob('*/test/result.json'))]
            self.assertEqual(len(summary), 2)
            self.assertEqual(summary[0]['harness_error'], 'RuntimeError')
            self.assertEqual(summary[1]['outcome'], 'no_submission')


def test_environment_defaults_and_explicit_runner_overrides(tmp_path, monkeypatch):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture-model"\neffort="medium"\n'
                      'tasks=["library.cell"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    monkeypatch.setenv('ICLAYOUT_BENCH_ENDPOINT', 'https://example.invalid/evaluation')
    monkeypatch.setenv('ICLAYOUT_BENCH_IMAGE', 'tools:configured')
    monkeypatch.setenv('ICLAYOUT_BENCH_OUTPUT', 'results/from-env')
    with patch('benchmarking.participants.batch.execute_condition', return_value=0) as execute:
        assert main(['--config', str(config)]) == 0
        assert execute.call_args.args[0].image == 'tools:configured'
        assert execute.call_args.args[3] == tmp_path / 'results/from-env'
        assert main(['--config', str(config), '--image', 'tools:explicit', '--output', 'results/explicit']) == 0
        assert execute.call_args.args[0].image == 'tools:explicit'
        assert execute.call_args.args[3] == tmp_path / 'results/explicit'
        monkeypatch.setenv('ICLAYOUT_BENCH_OUTPUT', '')
        assert main(['--config', str(config)]) == 0
        first = execute.call_args.args[3]
        assert first.parent == tmp_path / 'results/trial'
        from datetime import datetime
        datetime.strptime(first.name, '%Y%m%d-%H%M%S-%f').astimezone()
        assert main(['--config', str(config)]) == 0
        assert execute.call_args.args[3] != first
        with pytest.raises(SystemExit):
            main(['--config', str(config), '--resume'])


def test_cli_case_selection_and_scale_overrides(tmp_path, capsys, monkeypatch):
    """A small invocation must not dispatch the rest of a saved batch."""
    from benchmarking.run import main

    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    tasks = ['process.library.small', 'process.library.large', 'other.library.small']
    config = tmp_path / 'batch.toml'
    source = ('harness="codex"\nmodel="fixture-model"\neffort="medium"\n'
              f'tasks={json.dumps(tasks)}\nconcurrency=4\nrepetitions=3\n')
    config.write_text(source)
    base = ['--config', str(config), '--dry-run']
    assert main(base + ['--case', 'large', '--repetitions', '1', '--concurrency', '1']) == 0
    row, = json.loads(capsys.readouterr().out)
    assert row['tasks'] == [tasks[1]]
    assert row['repetitions'] == row['concurrency'] == 1
    assert main(base + ['--case', tasks[0], '--case', 'large', '--case', tasks[0]]) == 0
    row, = json.loads(capsys.readouterr().out)
    assert row['tasks'] == tasks[:2]
    assert main(base) == 0
    row, = json.loads(capsys.readouterr().out)
    assert row['tasks'] == tasks
    assert row['repetitions'] == 3 and row['concurrency'] == 4
    assert config.read_text() == source
    for flags, error in [(['--case', 'small'], 'Ambiguous case'),
                         (['--case', 'missing'], 'Unknown case'),
                         (['--repetitions', '0'], 'positive integer')]:
        with pytest.raises(SystemExit) as raised:
            main(base + flags)
        assert raised.value.code == 2
        assert error in capsys.readouterr().err


if __name__ == '__main__':
    unittest.main()


@pytest.mark.parametrize('event,exit_code,category', [
    ({'type': 'error', 'error': {'code': 'insufficient_quota'}}, 1, 'quota_exhausted'),
    ({'type': 'error', 'error': {'type': 'authentication_error'}}, 1, 'authentication'),
    ({'type': 'turn.failed', 'error': {'code': 'rate_limit_exceeded'}}, 1, 'rate_limit'),
    ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}, 1, 'provider_overloaded'),
    ({'type': 'turn.failed', 'error': {'message': 'Selected model is at capacity. Please try a different model.'}}, 1, 'provider_overloaded'),
    ({'type': 'turn.failed', 'error': {'code': 'server_is_overloaded', 'retry_after': 45}}, 1, 'provider_overloaded'),
    ({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Selected model is at capacity. Please try a different model.'}}, 1, 'unknown'),
    ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.',
      'error': {'code': 'invalid_api_key'}}, 1, 'authentication'),
    ({'type': 'assistant', 'text': 'insufficient_quota'}, 3, 'unknown'),
    ({}, -9, 'harness_crash'),
])
def test_failure_uses_evidence_not_exit_code_or_assistant_text(tmp_path, event, exit_code, category):
    from benchmarking.participants.adapters.codex import harness_failure
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event) + '\n')
    assert harness_failure(tmp_path, exit_code)['category'] == category


@pytest.mark.parametrize('harness,stop', [
    *[('codex', stop) for stop in ('success', 'limit', 'deadline', 'insufficient_budget', 'pending_tool', 'pending_after_wait',
                                 'missing_thread', 'authentication', 'retry_after', 'service_error', 'disabled')],
    ('claude-code', 'success'),
    ('codex', 'reconnect_then_capacity'),
])
def test_capacity_continuation_keeps_original_session_and_evidence(tmp_path, monkeypatch, harness, stop):
    """Run real child processes emitting native events; only the service/provider boundaries are fixtures."""
    import sys
    from types import SimpleNamespace

    from benchmarking.participants.recovery import DISABLED
    from benchmarking.participants.runner import CONTINUE_PROMPT, run_one

    reconnect_then_capacity = stop == 'reconnect_then_capacity'
    if reconnect_then_capacity:
        stop = 'success'

    fixture = ServiceFixture()
    fixture.remaining = 20 if stop == 'insufficient_budget' else 1000
    output = tmp_path / 'participant'
    selected = {'harness': harness, 'model': 'fixture-model', 'effort_resolved': 'xhigh', 'effort_requested': 'xhigh'}
    row = {'name': 'trial', 'harness': harness, 'task': 'fixture',
           'recovery': DISABLED | {'resume_session': stop == 'limit', 'capacity_resumes': 2, 'capacity_backoff_seconds': 30,
                                   'capacity_max_backoff_seconds': 300}}
    if stop == 'success':
        del row['recovery']  # Capacity continuation must work without opting in.
    elif stop == 'disabled':
        row['recovery']['capacity_resumes'] = 0
    launches, prompts, delays, timeouts = [], [], [], []
    clock = [0]
    native_id = 'original-native-thread'
    capacity = {'type': 'turn.failed', 'error': {'message': 'Selected model is at capacity. Please try a different model.'}}
    if harness == 'claude-code':
        capacity = {'type': 'error', 'error': {'type': 'overloaded_error'}}
    if stop == 'retry_after':
        capacity['error']['retry_after'] = 400

    def launch(context):
        condition, env = context.selection.condition, context.selection.environment
        nonlocal native_id
        assert fixture.active
        assert condition == selected
        launches.append(dict(env))
        if harness == 'claude-code':
            native_id = env['ICLAYOUT_BENCH_NATIVE_ID']
        events = [] if stop == 'missing_thread' else [{'type': 'thread.started', 'thread_id': native_id}]
        if len(launches) == 1 or stop == 'limit':
            if reconnect_then_capacity:
                events.extend([{'type': 'turn.started'},
                               {'type': 'error', 'message': 'Reconnecting... 2/5 (request timed out)'},
                               {'type': 'error', 'message': 'Reconnecting... waiting for network (Connection failed: error sending request)'},
                               {'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}])
            events.append(capacity)
            exit_code = 1
            if stop == 'pending_tool':
                (output / 'tools.delivery.json').write_text('{}')
        elif stop == 'authentication':
            events.append({'type': 'error', 'error': {'code': 'invalid_api_key'}})
            exit_code = 1
        else:
            events.append({'type': 'turn.completed'})
            exit_code = 0
        raw = '\n'.join(json.dumps(e) for e in events)
        return [sys.executable, '-c',
                f'import sys; from pathlib import Path; Path("prompt.txt").write_text(sys.stdin.read()); print({raw!r}); sys.exit({exit_code})']

    from benchmarking.participants.process import execute as actual_execute

    def execute(*args, **kwargs):
        prompts.append(kwargs['prompt'])
        timeouts.append(kwargs['timeout'])
        return actual_execute(*args, **kwargs)

    def sleep(seconds):
        delays.append(seconds)
        clock[0] += seconds
        fixture.remaining = 0 if stop == 'deadline' else fixture.remaining - seconds
        if stop == 'pending_after_wait':
            (output / 'tools.pending.json').write_text('{}')

    original_session = fixture.session
    service_error = []
    def session(sid):
        if stop == 'service_error' and prompts and not service_error:
            service_error.append(True)
            raise ClientError('transport_error', 'Connection interrupted')
        return original_session(sid)

    monkeypatch.setattr(fixture, 'session', session)
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.adapters.prepare', launch)
    monkeypatch.setattr('benchmarking.participants.runner.execute', execute)
    monkeypatch.setattr('benchmarking.participants.recovery.capacity_delay', lambda settings, attempt: min(300, 30 * 2 ** attempt))
    monkeypatch.setattr('benchmarking.participants.runner.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    with patch.object(fixture, 'create', wraps=fixture.create) as create:
        summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    assert create.call_count == 1
    assert fixture.closed == ['fixture-session']
    assert summary['state'] == 'finished'
    assert summary['session_id'] == 'fixture-session'
    if stop == 'success':
        frozen = json.loads((output / 'conditions.json').read_text())
        assert frozen['recovery']['capacity_resumes'] == 5
    if stop == 'disabled':
        assert len(launches) == 1
        assert not delays
        assert summary['failure']['category'] == 'provider_overloaded'
        assert summary['harness_error'] == 'cli_exit_1'
        assert 'capacity_recovery' not in summary
        return
    assert len(launches) == (3 if stop == 'limit' else 2 if stop in {'success', 'authentication'} else 1)
    for env in launches[1:]:
        assert env['ICLAYOUT_BENCH_RESUME_ID'] == native_id
        home = 'CODEX_HOME' if harness == 'codex' else 'CLAUDE_CONFIG_DIR'
        assert env[home] == launches[0][home]
        assert env['ICLAYOUT_BENCH_SESSION'] == launches[0]['ICLAYOUT_BENCH_SESSION']
    assert all(prompt == CONTINUE_PROMPT for prompt in prompts[1:])
    assert 'Check status' in CONTINUE_PROMPT and 'original deadline' in CONTINUE_PROMPT.lower()
    assert all(ord(c) < 128 for c in CONTINUE_PROMPT)
    recovery = json.loads((output / 'harness-summary.json').read_text())['capacity_recovery']
    assert json.loads((output / 'harness-summary.json').read_text())['elapsed_seconds'] == sum(delays)
    assert timeouts == ([1000, 970, 910] if stop == 'limit' else [1000, 970] if stop in {'success', 'authentication'}
                        else [20] if stop == 'insufficient_budget' else [1000])
    assert recovery['outcome'] == {'success': 'recovered', 'limit': 'limit_reached', 'deadline': 'deadline', 'insufficient_budget': 'deadline',
                                   'pending_tool': 'unsafe_to_resume', 'pending_after_wait': 'unsafe_to_resume', 'missing_thread': 'unsafe_to_resume',
                                   'authentication': 'stopped_on_other_error', 'retry_after': 'retry_after_exceeds_cap',
                                   'service_error': 'stopped_on_other_error'}[stop]
    assert len(recovery['interruptions']) == (3 if stop == 'limit' else 1)
    assert all(entry.get('status') for entry in recovery['interruptions'])
    assert (output / 'launch-1-harness.jsonl').exists() == (len(launches) > 1)
    if stop == 'success':
        assert summary['harness_error'] is None
        assert summary['failure']['category'] == 'task_failure'  # No submission, independently of recovery.
        assert delays == [30]
    else:
        assert summary['failure']['category'] == {'authentication': 'authentication', 'service_error': 'network_transient'}.get(stop, 'provider_overloaded')
    if stop in {'pending_tool', 'missing_thread', 'retry_after', 'service_error', 'insufficient_budget'}:
        assert not delays


def test_local_capacity_recovery_exports_both_launches_before_removing_runtime(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from benchmarking.run import main

    dataset = write_dataset(tmp_path / 'dataset', ['fixture'])
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture-model"\neffort="xhigh"\n'
                      'tasks=["fixture"]\nconcurrency=1\nrepetitions=1\n')
    fixture = ServiceFixture()
    clock, launches = [0], []
    selected = {'harness': 'codex', 'model': 'fixture-model', 'effort_resolved': 'xhigh', 'effort_requested': 'xhigh'}
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *a: ParticipantSelection(selected, {'CODEX_HOME': str(tmp_path / 'caller-home')}, {}))
    monkeypatch.setattr('benchmarking.participants.local_service.service', lambda *a: nullcontext(fixture))
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')

    def launch(context):
        env = context.selection.environment
        launches.append(dict(env))
        event = ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}
                 if len(launches) == 1 else {'type': 'turn.completed'})
        thread = json.dumps({'type': 'thread.started', 'thread_id': 'original-thread'})
        return [sys.executable, '-c', f'import sys; print({thread!r}); print({json.dumps(event)!r}); sys.exit({int(len(launches) == 1)})']

    def sleep(seconds):
        clock[0] += seconds
        fixture.remaining -= seconds

    monkeypatch.setattr('benchmarking.participants.adapters.prepare', launch)
    monkeypatch.setattr('benchmarking.participants.recovery.capacity_delay', lambda *a: 30)
    monkeypatch.setattr('benchmarking.participants.runner.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    batch = tmp_path / 'batch'
    assert main(['--config', str(config), '--dataset', str(dataset), '--output', str(batch)]) == 0
    case = batch / 'fixture/fixture/cases/fixture'
    result = json.loads((case / 'result.json').read_text())
    assert result['state'] == 'finished'
    assert result['execution']['capacity_recovery']['outcome'] == 'recovered'
    assert result['execution']['elapsed_seconds'] == 30
    assert result['execution']['failure'] is None
    assert not (case / '.runtime').exists()
    trace = [json.loads(line) for line in (case / 'agent.jsonl').read_text().splitlines()]
    assert [event['type'] for event in trace] == ['thread.started', 'error', 'thread.started', 'turn.completed']
    assert launches[1]['ICLAYOUT_BENCH_RESUME_ID'] == 'original-thread'
    assert fixture.closed == ['fixture-session']
    assert b'scoped-fixture-token' not in (case / 'agent.jsonl').read_bytes()


@pytest.mark.parametrize('third_case', [False, True])
def test_repeated_capacity_interruptions_cool_only_related_new_dispatch(tmp_path, monkeypatch, third_case):
    from types import SimpleNamespace

    from benchmarking.run import main

    tasks = ['a', 'b', 'c'] if third_case else ['a', 'b']
    matrix = tmp_path / 'trial.toml'
    matrix.write_text('[defaults]\nharness="codex"\neffort="high"\nconcurrency=1\nrepetitions=1\n'
                      f'tasks={json.dumps(tasks)}\n'
                      '[[runs]]\nname="first"\nmodel="first"\n'
                      '[[runs]]\nname="second"\nmodel="second"\ntasks=["a"]\n')
    clock, calls = [0], []
    def sleep(seconds):
        clock[0] += seconds
    def run(access, row, output, selection):
        calls.append((row['model'], row['task'], clock[0]))
        result = terminal_files(output)
        if row['model'] == 'first' and row['task'] in {'a', 'b'}:
            result['capacity_recovery'] = {'interruptions': [{'failure': {'category': 'provider_overloaded'}}]}
        return result
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda harness, model, effort: ParticipantSelection({'harness': harness, 'model': model}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.planning.default_output', lambda group: tmp_path / Path(group).name)
    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    monkeypatch.setattr('benchmarking.participants.batch.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    assert main(['--matrix', str(matrix), '--endpoint', 'https://fixture']) == 0
    expected_clock = 300 if third_case else 0
    assert calls[:2] == [('first', 'a', 0), ('first', 'b', 0)]
    assert calls[-1] == ('second', 'a', expected_clock)
    if third_case:
        assert calls[2] == ('first', 'c', 300)


def test_same_session_resume_preserves_budget_and_private_credentials(tmp_path):
    import sys

    from benchmarking.participants.recovery import DISABLED
    from benchmarking.participants.runner import run_one
    fixture = ServiceFixture()
    selected = {'harness': 'claude-code', 'model': 'fixture-model', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': 'claude-code', 'task': 'fixture',
           'recovery': DISABLED | {'resume_session': True}}
    output = tmp_path / 'participant'
    events = json.dumps({'type': 'error', 'error': {'code': 'insufficient_quota'}})
    observed = []
    def launch(context):
        env = context.selection.environment
        observed.append(dict(env))
        if len(observed) == 1:
            return [sys.executable, '-c', f'import sys; print({events!r}); sys.exit(1)']
        return [sys.executable, '-c', 'import os; print(os.environ["ICLAYOUT_BENCH_TOKEN"]); print(os.environ["PROVIDER_API_KEY"])']
    with patch('benchmarking.participants.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.adapters.prepare', side_effect=launch), \
            patch.object(fixture, 'create', wraps=fixture.create) as create:
        first = run_one(fixture, row, output, ParticipantSelection(selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}))
        assert first['state'] == 'suspended'
        assert first['failure']['category'] == 'quota_exhausted'
        assert fixture.closed == []
        fixture.remaining = 30  # Human billing wait did not reset the service clock.
        second = run_one(fixture, row, output, ParticipantSelection(selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}))
        assert create.call_count == 1
        assert second['state'] == 'finished'
        assert observed[1]['ICLAYOUT_BENCH_RESUME_ID'] == observed[0]['ICLAYOUT_BENCH_NATIVE_ID']
        assert (output / 'launch-1-harness.jsonl').exists()
        # A repeated collection must not re-launch or overwrite finished exports.
        run_participant(fixture, row, output, ParticipantSelection(selected, {}, {}))
        assert len(observed) == 2
    for path in (output / 'observation').rglob('*'):
        if path.is_file():
            assert b'scoped-fixture-token' not in path.read_bytes()
            assert b'fixture-api-secret' not in path.read_bytes()
    assert b'fixture-api-secret' in (output / 'harness.jsonl').read_bytes()  # Original evidence is preserved.
    assert (output / '.private/recovery.json').stat().st_mode & 0o777 == 0o600


def test_batch_resume_skips_completed_and_rejects_config_change(tmp_path, monkeypatch):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=2\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'secret')
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    calls = []
    def run(*args):
        calls.append(args)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return terminal_files(args[2]) | {'state': 'finished', 'harness_error': None}
    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    args = ['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(tmp_path / 'batch')]
    with pytest.raises(KeyboardInterrupt):
        main(args)
    assert main(args + ['--resume']) == 0
    assert len(calls) == 3
    assert main(args + ['--resume']) == 0
    assert len(calls) == 3
    config.write_text(config.read_text().replace('effort="high"', 'effort="low"'))
    with pytest.raises(SystemExit):
        main(args + ['--resume'])
    assert len(calls) == 3


def test_concurrent_batch_resume_cannot_launch(tmp_path, monkeypatch):
    from benchmarking.participants.storage import CaseLease
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    batch = tmp_path / 'batch'
    batch.mkdir()
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    (batch / 'test').mkdir()
    with CaseLease(batch / 'test'), patch('benchmarking.participants.runner.run_one') as launch, pytest.raises(SystemExit):
        main(['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(batch), '--resume'])
    launch.assert_not_called()


def test_attempt_export_keeps_distinct_sessions_and_redacts_private_traces(tmp_path):
    from benchmarking.engine.sessions.recorder import RunRecorder
    from benchmarking.files import Asset, write_json
    from benchmarking.participants.evidence import read_attempt_evidence
    from benchmarking.results.participant_export import export_attempts

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


def test_explicit_replacement_keeps_failed_attempt_and_pending_plan_in_same_batch(tmp_path, monkeypatch):
    from benchmarking.files import write_json as save
    from benchmarking.run import main

    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["interrupted", "finished", "pending"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *a: ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.planning.package_version', lambda: {'version': 'old', 'commit': 'old'})
    batch = tmp_path / 'batch'
    calls = []
    closed = ServiceFixture()
    closed.active = False
    monkeypatch.setattr('benchmarking.participants.replacement.Client', lambda *a, **kw: closed)
    def run(access, row, output, selection):
        calls.append(row['task'])
        if row['task'] == 'interrupted' and len(calls) == 1:
            (output / '.private').mkdir(parents=True)
            (output.parent / 'service/service-store').mkdir(parents=True)
            save(output / '.private/recovery.json', {'redactions': ['old-scoped-token'],
                                                     'created': {'session_id': 'old', 'session_token': 'old-scoped-token'}})
            save(output / 'conditions.json', {'framework': 'old'})
            save(output / 'harness-summary.json', {'error': 'capacity_failure', 'exit_code': 1})
            (output / 'harness.jsonl').write_text('{"message":"capacity_failure old-scoped-token"}\n')
            raise RuntimeError('interrupted')
        return terminal_files(output)
    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(batch)]
    assert main(args + ['--case', 'interrupted', '--case', 'finished']) == 1
    failed = json.loads((batch / 'interrupted/result.json').read_text())
    original_finished = (batch / 'finished/result.json').read_bytes()
    pending = copy.deepcopy(failed)
    pending.pop('summary')
    pending['state'] = 'pending'
    pending['identity']['plan'][0]['tasks'] = ['pending']
    (batch / 'pending').mkdir()
    save(batch / 'pending/result.json', pending)
    monkeypatch.setattr('benchmarking.participants.planning.package_version', lambda: {'version': 'repaired', 'commit': 'repaired'})
    selected = args + ['--case', 'interrupted', '--case', 'pending']
    with pytest.raises(SystemExit):
        main(args + ['--case', 'interrupted', '--case', 'finished', '--replace-unfinished'])
    assert json.loads((batch / 'interrupted/result.json').read_text()) == failed
    with pytest.raises(SystemExit):
        main(selected + ['--resume'])
    assert main(selected + ['--replace-unfinished']) == 0
    assert calls == ['interrupted', 'finished', 'interrupted', 'pending']
    result = json.loads((batch / 'interrupted/result.json').read_text())
    assert result['identity']['benchmark']['commit'] == 'repaired'
    attempt, = result['attempts']
    assert attempt['record'] == failed
    assert attempt['conditions'] == {'framework': 'old'}
    assert attempt['execution']['error'] == 'capacity_failure'
    assert b'old-scoped-token' not in (batch / 'interrupted' / next(f for f in result['files'] if f.startswith('attempts/') and f.endswith('agent.jsonl'))).read_bytes()
    assert json.loads((batch / 'pending/result.json').read_text())['prior_plans'] == [pending]
    assert (batch / 'finished/result.json').read_bytes() == original_finished
    assert not (batch / 'interrupted/.runtime').exists()
    with pytest.raises(SystemExit):
        main(selected + ['--replace-unfinished'])
    assert calls == ['interrupted', 'finished', 'interrupted', 'pending']


@pytest.mark.parametrize('changed', ['model', 'effort', 'image', 'inputs', 'endpoint', 'repetitions'])
def test_replacement_rejects_changed_solve_conditions(tmp_path, changed):
    from benchmarking.files import write_json as save
    from benchmarking.participants.replacement import validate_replacement
    identity = {'benchmark': {'commit': 'old'}, 'cli_version': 'old', 'endpoint': None,
                'image': 'image-id', 'inputs': {'case': {'case_sha256': 'original'}},
                'plan': [{'model': 'fixture', 'effort': 'high', 'repetitions': 1, 'tasks': ['case']}]}
    record = {'identity': identity, 'state': 'suspended'}
    save(tmp_path / 'result.json', record)
    changed_identity = copy.deepcopy(identity)
    if changed in {'model', 'effort', 'repetitions'}:
        changed_identity['plan'][0][changed] = 'changed'
    else:
        changed_identity[changed] = 'changed'
    with pytest.raises(ValueError, match='cannot change'):
        validate_replacement(tmp_path, changed_identity)
    assert json.loads((tmp_path / 'result.json').read_text()) == record


@pytest.mark.parametrize('fault', ['move', 'record', 'commit'])
def test_interrupted_replacement_preserves_evidence_and_completes_same_transaction(tmp_path, monkeypatch, fault):
    from benchmarking.files import write_json as save
    from benchmarking.participants import replacement, storage
    old = {'identity': {'plan': [{'model': 'fixture'}], 'benchmark': {'commit': 'old'}}, 'state': 'suspended'}
    save(tmp_path / 'result.json', old)
    runtime = tmp_path / '.runtime'
    runtime.mkdir()
    (runtime / 'evidence.txt').write_text('original evidence')
    current = dict(old['identity'], benchmark={'commit': 'repaired'})
    transaction = replacement.validate_replacement(tmp_path, current)
    real_save, real_rename = replacement.save, Path.rename
    def interrupted_save(path, value):
        if (fault == 'record' and path.name == 'record.json') or (fault == 'commit' and path == tmp_path / 'result.json'):
            raise OSError('disk interrupted')
        return real_save(path, value)
    def interrupted_move(path, target):
        result = real_rename(path, target)
        if fault == 'move' and path == runtime:
            raise OSError('move interrupted')
        return result
    with monkeypatch.context() as m:
        m.setattr(replacement, 'save', interrupted_save)
        m.setattr(storage, 'write_json', interrupted_save)
        m.setattr(Path, 'rename', interrupted_move)
        with pytest.raises(OSError):
            replacement.replace_unfinished(tmp_path, transaction)
    recovered = replacement.validate_replacement(tmp_path, current)
    assert recovered == transaction
    replacement.replace_unfinished(tmp_path, recovered)
    evidence, = runtime.glob('attempts/*/evidence.txt')
    assert evidence.read_text() == 'original evidence'
    assert json.loads((evidence.parent / 'record.json').read_text()) == old
    assert json.loads((tmp_path / 'result.json').read_text()) == {'identity': current, 'state': 'pending'}
    assert not (tmp_path / '.replacement.json').exists()


def test_replacement_rejects_live_local_service(tmp_path):
    from contextlib import ExitStack

    from benchmarking.locking import BatchLease
    from benchmarking.participants.replacement import lease_replacement
    store = tmp_path / '.runtime/service/service-store'
    store.mkdir(parents=True)
    with BatchLease(store), ExitStack() as stack, pytest.raises(OSError):
        lease_replacement(tmp_path, stack)


def test_finished_case_cleanup_waits_for_live_evidence_store(tmp_path):
    from benchmarking.locking import BatchLease
    from benchmarking.participants.storage import CaseRecord
    from benchmarking.participants.terminal import finish_case

    record = CaseRecord(tmp_path)
    record.initialize({'endpoint': 'https://fixture', 'plan': [{'model': 'fixture', 'effort': 'off'}]})
    record.begin()
    summary = terminal_files(record.participant)
    summary.update(state='finished', task='fixture', score=None)
    record.record_summary(summary)
    finish_case(tmp_path)
    committed = record.manifest.read_bytes()
    store = record.service / 'service-store'
    store.mkdir(parents=True)
    evidence = store / 'retained.json'
    evidence.write_text('private evidence pending cleanup')
    with BatchLease(store), pytest.raises(OSError):
        finish_case(tmp_path)
    assert evidence.read_text() == 'private evidence pending cleanup'
    assert record.manifest.read_bytes() == committed
    finish_case(tmp_path)
    assert not record.runtime.exists()
    assert record.manifest.read_bytes() == committed


def test_replacement_rejects_active_remote_session(tmp_path, monkeypatch):
    from benchmarking.files import write_json as save
    from benchmarking.participants.replacement import validate_replacement
    identity = {'endpoint': 'https://fixture', 'plan': [{'model': 'fixture'}]}
    save(tmp_path / 'result.json', {'identity': identity, 'state': 'suspended'})
    (tmp_path / '.runtime/participant/.private').mkdir(parents=True)
    save(tmp_path / '.runtime/participant/.private/recovery.json',
         {'created': {'session_id': 'old', 'session_token': 'scoped-token'}})
    fixture = ServiceFixture()
    monkeypatch.setattr('benchmarking.participants.replacement.Client', lambda *a, **kw: fixture)
    with pytest.raises(ValueError, match='Collect the existing remote'):
        validate_replacement(tmp_path, identity)


def test_quota_halts_related_dispatch_without_creating_extra_repetitions(tmp_path, monkeypatch):
    from benchmarking.participants.recovery import failure
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=3\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'secret')
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    with patch('benchmarking.participants.runner.run_one', return_value={'state': 'suspended', 'harness_error': 'billing',
               'failure': failure('quota_exhausted', 'harness_event')}) as run:
        assert main(['--config', str(config), '--endpoint', 'http://localhost:1',
                     '--output', str(tmp_path / 'batch')]) == 1
    assert run.call_count == 1
    records = [json.loads(p.read_text()) for p in sorted((tmp_path / 'batch').rglob('result.json'))]
    assert len(records) == 3
    assert [r['state'] for r in records] == ['suspended', 'blocked', 'blocked']


def test_service_restart_terminates_lost_execution_and_preserves_receipt(tmp_path, executable_case):
    """Durable HTTP metadata after abrupt loss; no Docker or model is started."""
    import time

    from benchmarking.service.server import APIError, LocalService
    from benchmarking.tasks import load_task
    root = tmp_path / 'service'
    sid = 'interrupted'
    (root / sid).mkdir(parents=True)
    receipt = {'submission_id': 'accepted', 'sequence': 1, 'candidate_sha256': 'a' * 64}
    data = {'session_id': sid, 'token': 'scoped', 'created_at': 'original-start', 'deadline': 'original-deadline',
            'deadline_epoch': time.time() + 60, 'retained_epoch': time.time() + 600,
            'task_id': 'fixture', 'task_sha256': 'b' * 64, 'condition': {}, 'tool_identity': {}, 'limits': {'wall_seconds': 60},
            'creation_key': 'create', 'creation_body': {'task_id': 'fixture', 'condition': {}},
            'submissions': {'accepted': receipt}, 'executions': {'e': {'execution_id': 'e', 'state': 'running',
            'exit_code': None, 'truncated': False, 'log_size': 0}},
            'requests': {'submissions:same': {'body': {'path': 'answer.gds'}, 'status': 200, 'response': receipt}}}
    (root / sid / 'http.json').write_text(json.dumps(data))
    service = LocalService(root, load_task(executable_case), {}, {}, 'unused', 'access', seconds=60)
    try:
        _, status = service.handle('GET', f'/sessions/{sid}', {}, 'scoped', None, None)
        assert status['state'] == 'error'
        assert status['active_execution_id'] is None
        assert status['deadline'] == data['deadline']
        _, replay = service.handle('POST', f'/sessions/{sid}/submissions', {}, 'scoped', {'path': 'answer.gds'}, 'same')
        assert replay == receipt
        with pytest.raises(APIError):
            service.handle('POST', f'/sessions/{sid}/executions', {}, 'scoped', {'command': 'increment'}, 'new')
        _, result = service.handle('GET', f'/sessions/{sid}/result', {}, 'scoped', None, None)
        assert result['failure_category'] == 'service_failure'
        assert result['score'] is None
        # Unacknowledged creation after restart must never create a replacement.
        with pytest.raises(APIError):
            service.handle('POST', '/sessions', {}, 'access', data['creation_body'], 'create')
    finally:
        service.shutdown()


def test_lost_close_reply_recovers_finalization_without_model_relaunch(tmp_path):
    import sys
    fixture = ServiceFixture()
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'harness': 'claude-code', 'task': 'fixture'}
    output = tmp_path / 'participant'
    close = fixture.close
    def lost(sid, **kwargs):
        close(sid, **kwargs)
        raise ClientError('transport_error', 'response lost')
    with patch('benchmarking.participants.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.adapters.prepare', return_value=[sys.executable, '-c', 'print("done")']) as launch:
        with patch.object(fixture, 'close', side_effect=lost), pytest.raises(ClientError):
            run_participant(fixture, row, output, ParticipantSelection(selected, {}, {}))
        result, _ = run_participant(fixture, row, output, ParticipantSelection(selected, {}, {}))
        assert result['state'] == 'complete'
        assert launch.call_count == 1


@pytest.mark.parametrize('resource_binding', [False, True])
def test_batch_resume_rejects_changed_dataset_input(tmp_path, monkeypatch, resource_binding):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    dataset = write_dataset(tmp_path / 'dataset', ['test'])
    asset = dataset / ('tasks/test/pdk.toml' if resource_binding else 'tasks/test/fixture/cases/test/input.spice')
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.local_service.service', lambda *args: nullcontext(ServiceFixture()))
    with patch('benchmarking.participants.runner.run_one', side_effect=lambda a, r, out, s: terminal_files(out)) as launch:
        args = ['--config', str(config), '--dataset', str(dataset), '--output', str(tmp_path / 'batch')]
        assert main(args) == 0
        asset.write_text('different input')
        with pytest.raises(SystemExit):
            main(args + ['--resume'])
    assert launch.call_count == 1


def test_runner_interruption_is_not_inferred_as_a_model_failure(tmp_path):
    from benchmarking.participants.recovery import DISABLED
    from benchmarking.participants.runner import run_one
    fixture = ServiceFixture()
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': 'claude-code', 'task': 'fixture',
           'recovery': DISABLED | {'resume_session': True}}
    output = tmp_path / 'participant'
    with patch('benchmarking.participants.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.runner.subprocess.Popen', side_effect=KeyboardInterrupt), \
            pytest.raises(KeyboardInterrupt):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    fixture.active = False  # Service subsequently closes under its own deadline.
    with patch('benchmarking.participants.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'):
        summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    assert summary['failure']['category'] == 'unknown'
    assert summary['harness_error'] == 'runner_interrupted'
    assert summary['outcome'] == 'no_submission'  # Independent service evidence is retained.


def test_interrupted_runner_can_collect_without_native_continuation(tmp_path, monkeypatch):
    """A command has delivered its candidate; its supervisor dies before cleanup."""
    import sys

    from benchmarking.participants.runner import run_one
    from benchmarking.participants.scheme import resolve_scheme

    fixture = InFlightService()
    selected = {'harness': 'command', 'model': 'fixture', 'effort_resolved': None}
    row = {'name': 'trial', 'harness': 'command', 'task': 'fixture',
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    output = tmp_path / 'participant'
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr('benchmarking.participants.runner.execute', interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    assert json.loads((output / '.private/recovery.json').read_text())['phase'] == 'running'
    with pytest.raises(ValueError, match='Session continuation was not enabled'):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    def forbidden(*args, **kwargs):
        pytest.fail('Collection must never relaunch a participant')
    monkeypatch.setattr('benchmarking.participants.runner.execute', forbidden)
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}), collect_only=True)
    assert summary['state'] == 'finished'
    assert summary['harness_error'] == 'runner_interrupted'
    assert fixture.closed == ['fixture-session']
    assert not fixture.submitted  # Keep the already accepted candidate, not mutable output.


@pytest.mark.parametrize('wrong_identity', [False, True])
def test_collect_only_cli_preserves_old_identity_and_never_resolves_harness(tmp_path, monkeypatch, wrong_identity):
    import sys

    from benchmarking.participants.scheme import resolve_scheme
    from benchmarking.run import main

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
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr('benchmarking.participants.runner.execute', interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_participant(fixture, dict(row, task='fixture'), output, ParticipantSelection(selected, {}, {}))
    identity = {'benchmark': {'version': 'old-release', 'commit': 'old-commit'},
                'endpoint': fixture.endpoint, 'plan': [row]}
    (case / 'result.json').write_text(json.dumps({'identity': identity, 'state': 'running'}))
    def forbidden(*args, **kwargs):
        pytest.fail('Collection must not resolve or launch a harness')
    monkeypatch.setattr('benchmarking.participants.planning.resolve', forbidden)
    monkeypatch.setattr('benchmarking.participants.planning.harness_version', forbidden)
    monkeypatch.setattr('benchmarking.participants.runner.execute', forbidden)
    if wrong_identity:
        fixture.condition = dict(fixture.condition, model='different-model')
        with pytest.raises(SystemExit) as error:
            main(['--collect-only', '--output', str(batch), '--case', 'fixture'])
        assert error.value.code == 2
        assert not fixture.closed
        assert json.loads((case / 'result.json').read_text())['state'] == 'running'
    else:
        assert main(['--collect-only', '--output', str(batch), '--case', 'fixture']) == 1
        final = json.loads((case / 'result.json').read_text())
        assert final['identity'] == identity
        assert final['state'] == 'finished'
        assert final['summary']['harness_error'] == 'runner_interrupted'
        assert not (case / '.runtime').exists()
        assert main(['--collect-only', '--output', str(batch), '--case', 'fixture']) == 1
        assert fixture.closed == ['fixture-session']


def test_case_lease_remains_exclusive_after_scheduler_closes_its_descriptor(tmp_path):
    import subprocess
    import sys

    from benchmarking.locking import BatchLeaseError
    from benchmarking.participants.storage import CaseLease

    child = None
    try:
        with CaseLease(tmp_path) as lease:
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                     pass_fds=(lease.fileno(),))
        with pytest.raises(BatchLeaseError), CaseLease(tmp_path):
            pytest.fail('A child still owns the case')
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=10)
    with CaseLease(tmp_path):
        pass


def test_collect_only_commits_existing_terminal_export_without_contacting_service(tmp_path, monkeypatch):
    import sys

    from benchmarking.participants.runner import run_one, save
    from benchmarking.participants.scheme import resolve_scheme
    from benchmarking.run import main

    fixture = ServiceFixture()
    row = {'name': 'trial', 'harness': 'command', 'model': 'fixture', 'effort': 'off',
           'tasks': ['fixture'], 'repetitions': 1,
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    case = tmp_path / 'batch/fixture'
    runtime = case / '.runtime'
    runtime.mkdir(parents=True)
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    selection = ParticipantSelection({'harness': 'command', 'model': 'fixture', 'effort_resolved': 'off'}, {}, {})
    summary = run_one(fixture, dict(row, task='fixture'), runtime / 'participant', selection)
    summary.update(result='participant/analysis/result.json', task='fixture', directory='fixture', repetition=1)
    identity = {'benchmark': {'version': 'old', 'commit': 'old'}, 'endpoint': None, 'plan': [row]}
    save(runtime / 'summary.json', summary)
    save(case / 'result.json', {'identity': identity, 'state': 'finalizing', 'summary': summary})
    def forbidden(*args, **kwargs):
        pytest.fail('A committed terminal export needs neither service nor model')
    monkeypatch.setattr('benchmarking.participants.local_service.local_service_client', forbidden)
    monkeypatch.setattr('benchmarking.participants.planning.resolve', forbidden)
    assert main(['--collect-only', '--output', str(tmp_path / 'batch')]) == 0
    final = json.loads((case / 'result.json').read_text())
    assert final['state'] == 'finished'
    assert final['identity'] == identity
    assert final['evaluation']['outcome'] == 'no_submission'
    assert not runtime.exists()


@pytest.mark.parametrize('concurrency', [1, 2])
def test_case_list_bounds_independent_sessions_and_prints_completed_results(tmp_path, monkeypatch, capsys, concurrency):
    """Public scheduling contract; harness I/O is simulated, with a barrier proving overlap."""
    import threading

    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    tasks = ['case-a', 'case-b', 'case-c', 'case-d']
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      f'tasks={json.dumps(tasks)}\nconcurrency={concurrency}\nrepetitions=2\n')
    barrier = threading.Barrier(concurrency)
    lock = threading.Lock()
    active, peak = 0, 0
    calls = []
    def run(access, row, output, selection):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append((row['task'], output))
        barrier.wait(timeout=5)
        summary = terminal_files(output)
        with lock:
            active -= 1
        return summary
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(tmp_path / 'batch')]
    assert main(args) == 0
    assert peak == concurrency
    assert sorted(task for task, _ in calls) == sorted(tasks * 2)
    assert len({output for _, output in calls}) == len(calls)
    capsys.readouterr()
    assert main(args + ['--resume']) == 0
    printed = capsys.readouterr().out
    assert len(calls) == len(tasks) * 2
    for task, output in calls:
        assert f'SKIP case={task} ' in printed
        assert str(output.parent.parent / 'result.json') in printed
    # A missing archived result must fail closed, not silently skip or rerun it.
    (calls[0][1].parent.parent / 'result.json').unlink()
    with pytest.raises(SystemExit):
        main(args + ['--resume'])
    assert len(calls) == len(tasks) * 2


def test_local_case_list_routes_dataset_inputs_and_rejects_missing_cases(tmp_path, monkeypatch):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["a", "b"]\nconcurrency=2\nrepetitions=1\n')
    dataset = write_dataset(tmp_path / 'dataset', ['a'])
    routed = []
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.local_service.service', lambda path, *args: nullcontext(path))
    def run(access, row, output, selection):
        assert access['case'] == row['task']
        assert access['dataset'] == str(dataset)
        routed.append(row['task'])
        return terminal_files(output)
    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    args = ['--config', str(config), '--output', str(tmp_path / 'batch'), '--dataset', str(dataset)]
    with pytest.raises(SystemExit):
        main(args)
    assert not routed
    assert not (tmp_path / 'batch').exists()
    write_dataset(dataset, ['a', 'b'])
    assert main(args) == 0
    assert sorted(routed) == ['a', 'b']


def test_native_mcp_approval_failure_is_not_a_zero_score_and_stops_dispatch(tmp_path, monkeypatch):
    """Replay the observed native event via a subprocess, with no model/EDA calls."""
    import sys

    from benchmarking.run import main
    fixture = ServiceFixture()
    event = {'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'layout',
             'tool': 'read', 'status': 'failed',
             'error': {'message': 'MCP tool call requires approval, but approval policy is never'}}}
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["fixture"]\nconcurrency=1\nrepetitions=2\n')
    selected = {'harness': 'codex', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection(selected, {}, {}))
    monkeypatch.setattr('benchmarking.participants.case.Client', lambda *args, **kwargs: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *args, **kwargs: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.subprocess.check_output', lambda *args, **kwargs: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.planning.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    with patch('benchmarking.participants.adapters.prepare', return_value=[sys.executable, '-c',
               'print(' + repr(json.dumps(event)) + ')']) as launch:
        args = ['--config', str(config), '--endpoint', fixture.endpoint, '--output', str(tmp_path / 'batch')]
        assert main(args) == 1
        records = [json.loads(p.read_text()) for p in sorted((tmp_path / 'batch/fixture').glob('repetition-*/result.json'))]
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
        assert main(args + ['--resume']) == 1
        assert launch.call_count == 1


@pytest.mark.parametrize('mode,category', [('prose', None), ('unknown', 'unknown'), ('recovered', None)])
def test_mcp_failure_requires_structured_unrecovered_evidence(tmp_path, mode, category):
    from benchmarking.participants.adapters.codex import harness_failure
    message = 'MCP tool call requires approval, but approval policy is never'
    item = {'type': 'mcp_tool_call', 'server': 'layout', 'tool': 'read', 'status': 'failed',
            'error': {'message': message}}
    if mode == 'prose':
        events = [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': message}}]
    elif mode == 'unknown':
        events = [{'type': 'item.completed', 'item': dict(item, error={'message': 'unrecognized transport failure'})}]
    else:
        events = [{'type': 'item.completed', 'item': item},
                  {'type': 'item.completed', 'item': dict(item, status='completed', error=None)}]
    (tmp_path / 'harness.jsonl').write_text('\n'.join(json.dumps(event) for event in events))
    problem = harness_failure(tmp_path, exit_code=0)
    assert (problem['category'] if problem else None) == category


@pytest.mark.parametrize('repetitions', [1, 2])
def test_timestamped_results_and_explicit_case_reuse(tmp_path, monkeypatch, capsys, repetitions):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="gpt-6-astra"\neffort="medium"\n'
                      f'tasks=["library.cell", "other.cell"]\nconcurrency=1\nrepetitions={repetitions}\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    monkeypatch.setattr('benchmarking.participants.planning.harness_version', lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    args = ['--config', str(config), '--endpoint', 'http://localhost:1']
    with patch('benchmarking.participants.runner.run_one', side_effect=lambda a, r, out, s: terminal_files(out)) as launch:
        assert main(args) == 0
        root, = (tmp_path / 'results/trial').iterdir()
        args += ['--output', str(root)]
        for task in ['library.cell', 'other.cell']:
            directory = root / task
            for repetition in range(1, repetitions + 1):
                slot = directory if repetitions == 1 else directory / f'repetition-{repetition}'
                assert json.loads((slot / 'result.json').read_text())['summary']['task'] == task
        assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'library.cell', 'other.cell'}
        from benchmarking.participants.storage import CaseLease
        count = launch.call_count
        with CaseLease(root / 'library.cell'), pytest.raises(SystemExit):
            main(args)
        assert launch.call_count == count
        capsys.readouterr()
        assert main(args) == 0
        assert launch.call_count == count
        assert 'SKIP case=library.cell' in capsys.readouterr().out
        # A different benchmark version cannot silently reuse this case.
        manifest = root / 'library.cell' / ('result.json' if repetitions == 1 else 'repetition-1/result.json')
        original_record = manifest.read_text()
        recorded = json.loads(original_record)
        assert 'inputs' not in recorded['identity']
        recorded['identity']['benchmark']['commit'] = 'different-release'
        manifest.write_text(json.dumps(recorded))
        with pytest.raises(SystemExit):
            main(args)
        assert json.loads(manifest.read_text()) == recorded
        assert launch.call_count == count
        manifest.write_text(original_record)
        slot = root / 'library.cell'
        if repetitions > 1:
            slot /= 'repetition-1'
        summary_path = slot / 'result.json'
        original = summary_path.read_text()
        suspended = json.loads(original)
        suspended['state'] = 'suspended'
        suspended['identity']['benchmark']['commit'] = 'different-release'
        summary_path.write_text(json.dumps(suspended))
        for flags in ([], ['--resume']):
            with pytest.raises(SystemExit):
                main(args + flags)
        assert launch.call_count == count
        summary_path.write_text(original)
        config.write_text(config.read_text().replace('repetitions='+str(repetitions), 'repetitions='+str(repetitions + 1)))
        with pytest.raises(SystemExit):
            main(args)
        assert launch.call_count == count


def test_append_cases_skips_original_and_runs_new_cases_concurrently(tmp_path, monkeypatch, capsys):
    """Public behavior: grow a completed plan, without touching its original evidence."""
    import threading

    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    def configure(tasks, concurrency):
        config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                          f'tasks={json.dumps(tasks)}\nconcurrency={concurrency}\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    monkeypatch.setattr('benchmarking.participants.planning.harness_version', lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.local_service.service', lambda *args: nullcontext(None))
    dataset = write_dataset(tmp_path / 'dataset', ['old', 'new-a', 'new-b'])
    barrier = threading.Barrier(2)
    calls = []
    def run(access, row, output, selection):
        calls.append(row['task'])
        if row['task'] != 'old':
            barrier.wait(timeout=5)  # Cannot pass if the two new sessions are serialized.
        return terminal_files(output, 'pass')
    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    configure(['old'], 1)
    args = ['--config', str(config), '--dataset', str(dataset)]
    assert main(args) == 0
    root, = (tmp_path / 'results/trial').iterdir()
    args += ['--output', str(root)]
    original = {str(p.relative_to(root / 'old/fixture/cases/old')): p.read_bytes() for p in (root / 'old/fixture/cases/old').rglob('*') if p.is_file()}
    manifest = (root / 'old/fixture/cases/old/result.json').read_bytes()
    configure(['old', 'new-a', 'new-b'], 2)
    capsys.readouterr()
    assert main(args) == 0
    printed = capsys.readouterr().out
    assert 'SKIP case=old ' in printed
    assert str(root / 'old/fixture/cases/old/result.json') in printed
    assert sorted(calls) == ['new-a', 'new-b', 'old']
    assert original == {str(p.relative_to(root / 'old/fixture/cases/old')): p.read_bytes() for p in (root / 'old/fixture/cases/old').rglob('*') if p.is_file()}
    assert (root / 'old/fixture/cases/old/result.json').read_bytes() == manifest
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'old', 'new-a', 'new-b'}
    assert main(args) == 0
    assert len(calls) == 3
    import shutil
    relocated = tmp_path / 'relocated'
    copied = relocated / 'results' / root.name / 'old/fixture/cases/old'
    shutil.copytree(root / 'old/fixture/cases/old', copied)
    configure(['old'], 1)
    monkeypatch.chdir(relocated)
    assert main(args) == 0
    assert len(calls) == 3
    assert {p.name for p in copied.parent.iterdir()} == {'old'}
    monkeypatch.chdir(tmp_path)
    configure(['old', 'new-a', 'new-b'], 2)
    # Inputs are version-owned: changing the benchmark release rejects all dispatch.
    monkeypatch.setattr('benchmarking.participants.planning.package_version', lambda: {"version": "different", "commit": None})
    with pytest.raises(SystemExit):
        main(args)
    assert len(calls) == 3


def test_startup_failure_is_durable_and_same_key_never_starts_another_worker(tmp_path, executable_case, monkeypatch):
    from benchmarking.service.server import APIError, LocalService
    from benchmarking.tasks import load_task
    task = load_task(executable_case)
    attempts = []
    def broken_startup(*args, **kwargs):
        attempts.append(1)
        raise OSError('resource archive unavailable')
    monkeypatch.setattr('benchmarking.engine.sessions.control.run_session', broken_startup)
    monkeypatch.setattr('benchmarking.engine.sessions.control.AttachedSession', lambda *args, **kwargs: object())
    body = {'task_id': task.id, 'condition': {'harness_kind': 'agent', 'harness_id': 'startup-test',
            'harness_version': '1', 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}}
    root = tmp_path / 'service'
    for _ in range(2):
        service = LocalService(root, task, {}, {}, 'unused', 'access', seconds=60)
        try:
            for _ in range(2):
                with pytest.raises(APIError):
                    service.handle('POST', '/sessions', {}, 'access', body, 'same-create')
            assert len(attempts) == 1
            metadata = list(root.glob('*/http.json'))
            assert len(metadata) == 1
            data = json.loads(metadata[0].read_text())
            assert data['interrupted'] is True
            assert data['creation_key'] == 'same-create'
            assert (metadata[0].parent / 'startup.json').is_file()
        finally:
            service.shutdown()


def test_slow_resource_provisioning_has_separate_startup_and_solve_budgets(tmp_path, executable_case, monkeypatch):
    import threading
    from types import SimpleNamespace

    import benchmarking.service.server as server_module
    from benchmarking.engine.sessions import control as session_control
    from benchmarking.tasks import load_task
    task = load_task(executable_case)
    release = threading.Event()
    observed = []
    class ProvisioningEvent(threading.Event):
        def wait(self, timeout=None):
            observed.append(timeout)
            # Simulate 90 seconds of durable resource staging without a slow test.
            # The former 45-second window abandons this otherwise healthy startup.
            if timeout is not None and timeout < 90:
                return False
            release.set()
            return super().wait(2)
    events = iter([ProvisioningEvent(), threading.Event()])
    monkeypatch.setattr(session_control, 'AttachedSession', lambda image, callback, **kwargs:
                        SimpleNamespace(image_id='fixture-image', ready=callback))
    def provision(task, config, resources, backends, destination, *, session, **kwargs):
        assert release.wait(2)
        destination.mkdir()
        (destination / 'events.jsonl').write_text('')
        session.ready(SimpleNamespace(remaining=lambda: config.wall_seconds, active=False), None)
        return {'outcome': 'no_submission'}
    monkeypatch.setattr(session_control, 'run_session', provision)
    service = server_module.LocalService(tmp_path / 'service', task, {}, {}, 'unused', 'access', seconds=60)
    monkeypatch.setattr(session_control, 'threading', SimpleNamespace(
        Event=lambda: next(events), Lock=threading.Lock, Thread=threading.Thread))
    body = {'task_id': task.id, 'condition': {'harness_kind': 'agent', 'harness_id': 'startup-test',
            'harness_version': '1', 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}}
    try:
        status, created = service.handle('POST', '/sessions', {}, 'access', body, 'creation')
        assert status == 201
        assert created['limits']['wall_seconds'] == service.controller.limits['wall_seconds']
        assert observed and observed[0] > service.controller.limits['wall_seconds']
        assert service.handle('POST', '/sessions', {}, 'access', body, 'creation') == (status, created)
        assert len(service.controller.state.runs) == 1
    finally:
        release.set()
        service.shutdown()


def test_default_case_storage_retains_blocked_dispatch_without_batch_summary(tmp_path, monkeypatch):
    """A provider failure must leave the unstarted case visibly blocked in its own directory."""
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["first", "second"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ICLAYOUT_BENCH_TOKEN", "fixture-token")
    monkeypatch.setattr('benchmarking.participants.planning.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    result = {'outcome': 'error', 'failure': {'category': 'quota_exhausted', 'stop_dispatch': True}}
    with patch('benchmarking.participants.runner.run_one', side_effect=lambda a, r, out, s: terminal_files(out, 'error') | result) as launch:
        assert main(['--config', str(config), '--endpoint', 'https://fixture']) == 1
        assert launch.call_count == 1
    root, = (tmp_path / 'results/trial').iterdir()
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'first', 'second'}
    assert json.loads((root / 'second/result.json').read_text())['state'] == 'blocked'
    assert not (root / 'second/.runtime').exists()


def test_command_participant_receives_contract_and_keeps_one_identity_across_tasks(tmp_path, monkeypatch):
    """Exercise the new launcher using a real subprocess and existing HTTP double.

    The task contract, scoped credential and stdin are independent API inputs.
    Changing instructions must distinguish schemes; task/output paths must not.
    No provider or EDA claim is made by this Public-owned regression.
    """
    import sys

    from benchmarking.participants.config import resolve
    from benchmarking.participants.scheme import resolve_scheme

    script = tmp_path / 'participant.py'
    script.write_text('import json, os, sys\n'
                      'task = json.load(open(os.environ["ICLAYOUT_BENCH_TASK_FILE"]))\n'
                      'assert "session_token" not in task\n'
                      'assert os.environ["ICLAYOUT_BENCH_TOKEN"] == "scoped-fixture-token"\n'
                      'assert os.environ["ICLAYOUT_BENCH_MODEL"] == "fixture-model"\n'
                      'assert "TASK CONTRACT:" in sys.stdin.read()\n'
                      'assert "layout" in json.load(open(os.environ["ICLAYOUT_BENCH_MCP_CONFIG"]))["mcpServers"]\n'
                      'print("contract received")\n')
    raw = {'version': 'test-1', 'launch': {'command': [sys.executable, 'participant.py'], 'files': ['participant.py']}}
    identities = []
    for index, (task, instructions) in enumerate([('one', ''), ('two', ''), ('one', 'Use tool A')]):
        scheme = resolve_scheme(dict(raw, instructions=instructions), tmp_path, 'command')
        fixture = ServiceFixture()
        monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, fixture=fixture, **kw: fixture)
        selection = resolve('command', 'fixture-model', 'medium')
        condition, env, settings = selection.condition, selection.environment, selection.settings
        output = tmp_path / str(index)
        result, error = run_participant(fixture, {'harness': 'command', 'task': task, 'scheme': scheme}, output, ParticipantSelection(condition, env, settings))
        assert error is None
        assert result['outcome'] == 'no_submission'
        assert result['score'] is None
        assert 'contract received' in (output / 'harness.jsonl').read_text()
        identities.append(fixture.condition['configuration_sha256'])
    assert identities[0] == identities[1]
    assert identities[0] != identities[2]


@pytest.mark.parametrize('harness', ['codex', 'claude-code'])
def test_declared_mcp_tool_is_enabled_without_putting_its_credentials_on_argv(tmp_path, harness):
    from benchmarking.participants.adapters import prepare

    selected = {'harness': harness, 'model': 'fixture-model', 'effort_requested': 'medium', 'effort_resolved': 'medium'}
    settings = {'mcp_servers': {'a': {'command': '/tools/a', 'args': ['serve'], 'env': {'A_API_KEY': 'private-key'}}}}
    env = {'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '60'}
    argv = prepare(LaunchContext(ParticipantSelection(selected, env, settings), tmp_path / 'mcp.json', tmp_path, tmp_path, tmp_path / 'bridge.py', 'task'))
    assert 'private-key' not in ' '.join(argv)
    if harness == 'codex':
        assert 'mcp_servers.a.command="/tools/a"' in argv
        assert 'mcp_servers.a.env_vars=["A_API_KEY"]' in argv
    else:
        assert 'mcp__a' in argv[argv.index('--allowedTools') + 1]
        assert 'mcp_servers' not in json.loads(argv[argv.index('--settings') + 1])


@pytest.mark.parametrize("credential", ["api_key_env", "oauth"])
def test_kimi_isolates_native_configuration_and_delivers_task_via_mcp(tmp_path, monkeypatch, credential):
    """Kimi's documented print/config contract must retain scoped tools and effort.

    Use the existing service fixture and fake only native execution: this guards
    credential/rule leakage and dispatch into Codex, not model or EDA quality.
    """
    import tomllib

    import tomli_w

    from benchmarking.participants.config import resolve

    home = tmp_path / 'host'
    home.mkdir()
    original = {'default_model': 'fixture/k3',
                'providers': {'fixture': {'type': 'kimi', 'api_key_env': 'KIMI_FIXTURE_API_KEY'}},
                'models': {'fixture/k3': {'provider': 'fixture', 'model': 'k3', 'max_context_size': 8192,
                                         'support_efforts': ['low', 'high', 'max']}},
                'hooks': [{'event': 'PreToolUse', 'command': 'must-not-run'}]}
    if credential == 'oauth':
        original['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': 'oauth/fixture'}}
        (home / 'oauth').mkdir()
        (home / 'oauth/fixture').write_text('{"access_token":"private-oauth-token"}')
    (home / 'config.toml').write_text(tomli_w.dumps(original))
    (home / 'mcp.json').write_text('{"mcpServers":{"unrelated":{}}}')
    monkeypatch.setenv('KIMI_CODE_HOME', str(home))
    monkeypatch.setenv('KIMI_FIXTURE_API_KEY', 'private-provider-key')
    monkeypatch.setenv('KIMI_MODEL_THINKING_EFFORT', 'low')
    selection = resolve('kimi-code', 'fixture/k3', 'high')
    selected, env, settings = selection.condition, selection.environment, selection.settings
    with pytest.raises(ValueError, match='explicitly supported'):
        resolve('kimi-code', 'fixture/k3', 'xhigh')
    fixture = ServiceFixture()
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.adapters.cli_version', lambda *a: 'kimi 1.2.3')

    def execute(argv, *, cwd, env, prompt, **kwargs):
        assert argv[0] == 'kimi'
        assert argv[argv.index('--prompt') + 1] == prompt
        assert 'TASK CONTRACT:' in prompt
        assert 'private-provider-key' not in ' '.join(argv)
        isolated = Path(env['KIMI_CODE_HOME'])
        assert isolated != home
        config = tomllib.loads((isolated / 'config.toml').read_text())
        assert config['thinking']['effort'] == selected['effort_resolved']
        assert 'hooks' not in config
        assert config['tools']['enabled'] == ['mcp__layout__*']
        assert 'KIMI_MODEL_THINKING_EFFORT' not in env
        if credential == 'api_key_env':
            assert env['KIMI_FIXTURE_API_KEY'] == 'private-provider-key'
        else:
            assert (isolated / 'oauth/fixture').read_bytes() == (home / 'oauth/fixture').read_bytes()
            assert (isolated / 'oauth/fixture').stat().st_mode & 0o777 == 0o600
            assert 'KIMI_FIXTURE_API_KEY' not in env
        servers = json.loads((isolated / 'mcp.json').read_text())['mcpServers']
        assert set(servers) == {'layout'}
        assert servers['layout']['env']['ICLAYOUT_BENCH_TOKEN'] == 'scoped-fixture-token'
        assert servers['layout']['toolTimeoutMs'] > fixture.remaining * 1000
        return 0, False

    monkeypatch.setattr('benchmarking.participants.runner.execute', execute)
    output = tmp_path / 'result'
    result, error = run_participant(fixture, {'harness': 'kimi-code', 'task': 'fixture'}, output, ParticipantSelection(selected, env, settings))
    assert error is None
    assert result['outcome'] == 'no_submission'
    assert tomllib.loads((home / 'config.toml').read_text()) == original
    assert 'private-provider-key' not in (output / 'conditions.json').read_text()


@pytest.mark.parametrize('ending, exit_code, timed_out, category', [
    ([{'type': 'turn.completed'}], 0, False, None),
    ([{'type': 'turn.failed'}], 0, False, 'unknown'),
    ([], 0, False, 'unknown'),
    ([{'type': 'turn.completed'}], 1, False, 'unknown'),
    ([{'type': 'turn.completed'}], 0, True, 'budget_exhausted'),
    ([{'type': 'turn.started'}, {'type': 'turn.completed'}], 0, False, 'unknown'),
    ([{'type': 'turn.completed'}, {'type': 'error', 'message': 'unrecognized failure'}], 0, False, 'unknown'),
    ([{'type': 'error', 'error': {'code': 'invalid_api_key'}}, {'type': 'turn.completed'}], 0, False, 'authentication'),
    ([{'type': 'error', 'error': {'code': 'insufficient_quota'}}, {'type': 'turn.completed'}], 0, False, 'quota_exhausted'),
    ([{'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'layout',
                                       'tool': 'execute', 'status': 'failed', 'error': {'message': 'transport failed'}}},
      {'type': 'turn.completed'}], 0, False, 'unknown'),
])
def test_reconnect_recovery_requires_successful_same_turn(tmp_path, ending, exit_code, timed_out, category):
    """Observed Codex reconnect events are diagnostic after successful recovery.

    Existing single-error tests miss recovered sequences. The real classifier
    consumes minimized native events; unrelated failures and turn boundaries
    must retain failure evidence. No model or EDA behavior is asserted.
    """
    from benchmarking.participants.adapters.codex import harness_failure

    events = [{'type': 'turn.started'}, {'type': 'error',
              'message': 'Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)'}] + ending
    trace = tmp_path / 'harness.jsonl'
    original = '\n'.join(json.dumps(e) for e in events)
    trace.write_text(original)
    problem = harness_failure(tmp_path, exit_code=exit_code, timed_out=timed_out)
    assert (problem['category'] if problem else None) == category
    assert trace.read_text() == original


@pytest.mark.parametrize('event, recovered', [
    ({'type': 'error', 'error': {'code': 'connection_error'}}, True),
    ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}, True),
    ({'type': 'error', 'message': 'unrecognized failure'}, False),
    ({'type': 'error', 'message': 'Reconnecting... 2/5 (stream disconnected before completion: tls handshake eof)',
      'error': {'code': 'insufficient_quota'}}, False),
])
def test_reconnect_recognition_preserves_other_error_evidence(tmp_path, event, recovered):
    from benchmarking.participants.adapters.codex import harness_failure

    events = [{'type': 'turn.started'}, event, {'type': 'turn.completed'}]
    (tmp_path / 'harness.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
    assert (harness_failure(tmp_path, exit_code=0) is None) == recovered


def test_capacity_error_cannot_hide_another_failure(tmp_path):
    from benchmarking.participants.adapters.codex_events import (
        CAPACITY_MESSAGE,
        harness_failure,
    )

    events = [{'type': 'error', 'message': 'unrecognized failure'},
              {'type': 'turn.failed', 'error': {'message': CAPACITY_MESSAGE}}]
    (tmp_path / 'harness.jsonl').write_text('\n'.join(json.dumps(event) for event in events))
    assert harness_failure(tmp_path, exit_code=1)['category'] == 'unknown'


@pytest.mark.parametrize('message', [
    'Reconnecting... 2/5 (request timed out)',
    'Reconnecting... 2/5 (workspace routing discovery timed out)',
    'Reconnecting... waiting for network (Connection failed: error sending request)',
    'Reconnecting... 2/5 (unexpected status 503 Service Unavailable: upstream connect error)',
])
@pytest.mark.parametrize('completed', [False, True])
def test_observed_reconnect_variants_require_successful_completion(tmp_path, message, completed):
    from benchmarking.participants.adapters.codex import harness_failure

    events = [{'type': 'turn.started'}, {'type': 'error', 'message': message},
              {'type': 'turn.completed' if completed else 'turn.failed'}]
    raw = '\n'.join(json.dumps(e) for e in events)
    (tmp_path / 'harness.jsonl').write_text(raw)
    problem = harness_failure(tmp_path, exit_code=0 if completed else 1)
    assert (problem is None) == completed
    assert (tmp_path / 'harness.jsonl').read_text() == raw


@pytest.mark.parametrize('scoped,stop_dispatch', [(False, False), (True, False), (True, True)])
def test_resume_observes_orphans_and_refills_before_the_slow_case_finishes(tmp_path, monkeypatch, scoped, stop_dispatch):
    """Inherited locks reproduce supervisor loss; no provider or EDA calls occur."""
    import subprocess
    import sys
    import threading
    import time

    from benchmarking.participants.storage import CaseLease, CaseRecord
    from benchmarking.run import main

    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["fast", "slow", "next"]\nconcurrency=2\nrepetitions=1\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    monkeypatch.setattr('benchmarking.participants.planning.resolve', lambda *a: ParticipantSelection({}, {}, {}))
    next_started = threading.Event()
    launches = []

    def run(access, row, output, selection):
        launches.append(row['task'])
        if row['task'] == 'next':
            next_started.set()
        return terminal_files(output)

    monkeypatch.setattr('benchmarking.participants.runner.run_one', run)
    output = tmp_path / 'batch'
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(output)]
    assert main(args) == 0
    launches.clear()
    next_started.clear()
    pending = json.loads((output / 'next/result.json').read_text())
    pending.update(state='pending')
    pending.pop('summary')
    (output / 'next/result.json').write_text(json.dumps(pending))
    owners = []
    failures = []
    script = '''import json, os, sys, time
from pathlib import Path
from benchmarking.files import write_json
from benchmarking.service.process import process_start
p = json.load(sys.stdin)
root = Path(p['root'])
write_json(root / '.runtime/worker.json', {'pid': os.getpid(), 'start': process_start(os.getpid()),
    'scheduler': {'pid': 99999999, 'start': {'ticks': '0', 'boot': 'absent'}}})
Path(p['ready']).touch()
until = time.monotonic() + 20
while not Path(p['release']).exists() and time.monotonic() < until:
    time.sleep(.01)
write_json(root / 'result.json', p['finished'])
'''
    try:
        for task in ('fast', 'slow'):
            root = output / task
            finished = json.loads((root / 'result.json').read_text())
            if task == 'fast' and stop_dispatch:
                finished['summary']['failure'] = {'category': 'quota_exhausted', 'stop_dispatch': True}
            running = dict(finished, state='running')
            running.pop('summary')
            (root / 'result.json').write_text(json.dumps(running))
            (root / '.runtime').mkdir()
            with CaseLease(root) as lease:
                child = subprocess.Popen([sys.executable, '-I', '-c', script], stdin=subprocess.PIPE,
                                         text=True, pass_fds=(lease.fileno(),))
                owners.append(child)
                child.stdin.write(json.dumps({'root': str(root), 'finished': finished,
                    'ready': str(tmp_path / (task + '.ready')), 'release': str(tmp_path / (task + '.release'))}))
                child.stdin.close()
                until = time.monotonic() + 3
                while not (tmp_path / (task + '.ready')).exists() and time.monotonic() < until:
                    time.sleep(.01)
                assert (tmp_path / (task + '.ready')).exists()

        def recover():
            try:
                assert main(args + ['--resume'] + (['--case', 'next'] if scoped else [])) == int(stop_dispatch)
            except BaseException as error:  # noqa: BLE001 -- propagate thread failures to the test owner
                failures.append(error)

        recovering = threading.Thread(target=recover)
        recovering.start()
        until = time.monotonic() + 3
        journal = output / '.scheduler/events.jsonl'
        while time.monotonic() < until and recovering.is_alive():
            events = [json.loads(line) for line in journal.read_text().splitlines(keepends=True)
                      if line.endswith('\n')]
            if any(event['event'] == 'worker_adopted' and event['case'] == 'fast' for event in events):
                break
            time.sleep(.01)
        else:
            pytest.fail('Recovered scheduler did not observe the fast worker: ' + repr(failures))
        (tmp_path / 'fast.release').touch()
        if stop_dispatch:
            recovering.join(3)
            assert not recovering.is_alive() and not failures
            assert CaseRecord(output / 'next').read()['state'] == 'blocked'
        else:
            assert next_started.wait(3), failures
        assert not (tmp_path / 'slow.release').exists()
        assert launches == ([] if stop_dispatch else ['next'])
        if scoped:
            recovering.join(3)
            assert not recovering.is_alive() and not failures
        (tmp_path / 'slow.release').touch()
        recovering.join(5)
        assert not recovering.is_alive() and not failures
    finally:
        for task in ('fast', 'slow'):
            (tmp_path / (task + '.release')).touch()
        for child in owners:
            child.wait(timeout=5)


def test_capacity_delay_is_bounded_and_respects_exponential_intervals(monkeypatch):
    from benchmarking.participants.recovery import DISABLED, capacity_delay, policy

    settings = policy(DISABLED | {'capacity_resumes': 5})
    monkeypatch.setattr('benchmarking.participants.recovery.random.uniform', lambda *args: 1.1)
    assert [capacity_delay(settings, n) for n in range(5)] == [33, 66, 132, 264, 300]


@pytest.mark.parametrize('repetitions', [1, 2])
def test_collect_only_waits_for_the_shared_case_lease(tmp_path, repetitions):
    """Collection locks the scheduler's case root, including repeated slots."""
    import subprocess
    import sys
    import time

    from benchmarking.locking import BatchLeaseError
    from benchmarking.participants.case import CollectRequest, collect_batch
    from benchmarking.participants.storage import CaseLease

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


@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("structured", [False, True])
def test_capacity_messages_are_interpreted_only_by_the_owning_adapter(tmp_path, harness, structured):
    from benchmarking.participants import adapters

    event = {"type": "error", "message": "Selected model is at capacity. Please try a different model."}
    if structured:
        event["error"] = {"type": "overloaded_error", "retry_after": 45}
    (tmp_path / "harness.jsonl").write_text(json.dumps(event))
    problem = adapters.harness_failure(harness, tmp_path, exit_code=1)
    assert problem["category"] == ("provider_overloaded" if structured or harness == "codex" else "unknown")
    if structured:
        assert problem["retry_after"] == 45


@pytest.mark.parametrize("harness", HARNESSES)
def test_reconnect_turn_semantics_are_specific_to_codex(tmp_path, harness):
    from benchmarking.participants import adapters

    events = [{"type": "turn.started"},
              {"type": "error", "message": "Reconnecting... 2/5 (request timed out)"},
              {"type": "turn.completed"}]
    (tmp_path / "harness.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    problem = adapters.harness_failure(harness, tmp_path, exit_code=0)
    assert (problem is None) == (harness == "codex")


def test_status_requires_no_provider_and_excludes_private_record_fields(tmp_path, capsys):
    import os

    from benchmarking.files import write_json
    from benchmarking.run import main
    from benchmarking.service.process import process_start

    root = tmp_path / 'batch'
    case = root / 'fixture'
    case.mkdir(parents=True)
    control = root / '.scheduler'
    control.mkdir()
    secret = 'status-private-regression-secret'
    write_json(case / 'result.json', {'identity': {'plan': [{'tasks': ['fixture']}], 'endpoint': secret},
        'state': 'running', 'summary': {'score': None, 'outcome': None, 'session_token': secret}})
    write_json(control / 'owner.json', {'pid': os.getpid(), 'start': process_start(os.getpid()),
        'state': 'running', 'concurrency': 2, 'private': secret})
    assert main(['--status', '--output', str(root)]) == 0
    raw = capsys.readouterr().out
    status = json.loads(raw)
    assert secret not in raw
    assert status['scheduler_alive'] and status['states'] == {'running': 1}
    assert status['cases'][0]['task'] == 'fixture'


def test_live_scheduler_prevents_orphan_adoption_and_pid_reuse_does_not_authorize_it(tmp_path):
    import os

    from benchmarking.files import write_json
    from benchmarking.locking import BatchLeaseError
    from benchmarking.participants.scheduler import live_worker
    from benchmarking.service.process import process_start

    runtime = tmp_path / '.runtime'
    runtime.mkdir()
    owner = {'pid': os.getpid(), 'start': process_start(os.getpid()),
             'scheduler': {'pid': os.getpid(), 'start': process_start(os.getpid())}}
    write_json(runtime / 'worker.json', owner)
    with pytest.raises(BatchLeaseError, match='live scheduler'):
        live_worker(tmp_path)
    owner['start'] = {'ticks': '0', 'boot': 'wrong-boot'}
    write_json(runtime / 'worker.json', owner)
    assert live_worker(tmp_path) is None


def test_resume_rejects_an_unverified_live_owner_outside_the_selected_cases(tmp_path):
    from benchmarking.files import write_json
    from benchmarking.locking import BatchLeaseError
    from benchmarking.participants.scheduler import live_slots
    from benchmarking.participants.storage import CaseLease

    case = tmp_path / 'unselected'
    case.mkdir()
    write_json(case / 'result.json', {'identity': {'plan': [{'tasks': ['unselected'], 'repetitions': 1}]},
        'state': 'running'})
    with CaseLease(case), pytest.raises(BatchLeaseError, match='Unverified live case owner'):
        live_slots(tmp_path)
