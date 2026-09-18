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
from benchmarking.participants.runner import run_participant
from benchmarking.protocol import PROTOCOL, USAGE_FIELDS

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def external_runtime_boundaries(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("benchmarking.run.DockerSession", lambda image: SimpleNamespace(image_id=image))
    monkeypatch.setattr("benchmarking.run.harness_version", lambda _: ("1.2.3", "fixture-cli 1.2.3"))


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
            'verification_level': 'local_development',
        }


def terminal_files(output, outcome='no_submission'):
    (output / 'analysis').mkdir(parents=True, exist_ok=True)
    result = ServiceFixture().result('fixture-session')
    result['outcome'] = outcome
    (output / 'analysis/result.json').write_text(json.dumps(result))
    return {'outcome': outcome, 'result': 'analysis/result.json'}


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
                    patch('benchmarking.participants.runner.command', return_value=[sys.executable, '-c', code]):
                result, error = run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture'},
                                           output, copy.deepcopy(selected), {}, {})
            self.assertEqual(fixture.closed, ['fixture-session'])
            self.assertEqual(result['outcome'], 'no_submission')
            self.assertTrue((output / 'analysis/result.json').exists())
            manifest = json.loads((output / 'observation/manifest.json').read_text())
            self.assertEqual(manifest['participant']['provenance'], 'participant_reported')
            self.assertEqual(manifest['service']['verification_level'], 'local_development')
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
                patch('benchmarking.participants.runner.command') as launch:
            with self.assertRaisesRegex(ValueError, 'wall_seconds'):
                run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture'}, Path(directory) / 'run',
                           {'model': 'fixture-model'}, {}, {})
            launch.assert_not_called()
            self.assertEqual(fixture.closed, ['fixture-session'])

    def test_default_batch_groups_local_and_remote_outputs_per_run(self):
        import sys

        from benchmarking.run import main
        for local in (False, True):
            with self.subTest(local=local), tempfile.TemporaryDirectory() as directory:
                batch = Path(directory) / 'results/generated'
                (Path(directory) / 'case').mkdir()
                (Path(directory) / 'case/case.toml').write_text('id="fixture"')
                config = Path(directory) / 'trial.toml'
                config.write_text('harness="claude-code"\nmodel="fixture-model"\ntasks=["fixture"]\nconcurrency=1\neffort="high"\nrepetitions=1\n')
                fixture = ServiceFixture()
                fixture.remaining = 3 * 3600
                selected = ({'harness': 'claude-code', 'model': 'fixture-model',
                             'effort_resolved': 'high', 'effort_requested': None}, {}, {})

                def local_service(prepared, output, image, batch=batch, fixture=fixture):
                    self.assertEqual(output, batch / 'fixture/.runtime/service')
                    (output / 'service.log').write_text('fixture service')
                    return nullcontext(fixture)

                with patch('benchmarking.run.default_output', return_value=batch), \
                        patch('benchmarking.run.resolve', return_value=selected), \
                        patch('benchmarking.run.Client', return_value=fixture), \
                        patch('benchmarking.run.service', side_effect=local_service), \
                        patch('benchmarking.participants.runner.Client', return_value=fixture), \
                        patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli 1.2.3'), \
                        patch('benchmarking.participants.runner.command', return_value=[sys.executable, '-c', 'print("done")']), \
                        patch.dict('os.environ', {'ICLAYOUT_BENCH_ENDPOINT': ''}), \
                        patch('builtins.print'):
                    mode = ['--prepared', directory] if local else ['--endpoint', fixture.endpoint]
                    code = main(['--config', str(config), *mode])
                self.assertEqual(code, 0)
                result = json.loads((batch / 'fixture/result.json').read_text())
                self.assertEqual(result['summary']['directory'], 'fixture')
                self.assertEqual(result['evaluation']['outcome'], 'no_submission')
                self.assertTrue((batch / 'fixture/agent.jsonl').exists())
                self.assertFalse((batch / 'fixture/.runtime').exists())
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
            selection = ({'harness': 'claude-code', 'model': 'test', 'effort_resolved': None}, {}, {})
            def run(access, row, out, selected):
                if row['name'].startswith('first'):
                    raise RuntimeError('fixture failure')
                return terminal_files(out)
            with patch('benchmarking.run.default_output', side_effect=lambda row, version: root / row['name']), \
                    patch('benchmarking.run.harness_version', return_value=('1.2.3', 'fixture 1.2.3')), \
                    patch('benchmarking.run.resolve', return_value=selection), \
                    patch('benchmarking.run.run_one', side_effect=run), \
                    patch.dict('os.environ', {'ICLAYOUT_BENCH_TOKEN': 'fixture-token'}), \
                    patch('builtins.print'):
                code = main(['--matrix', str(matrix), '--endpoint', 'http://127.0.0.1:8765'])
            self.assertEqual(code, 1)
            summary = [json.loads(p.read_text())['summary'] for p in sorted(root.glob('*/test/result.json'))]
            self.assertEqual(len(summary), 2)
            self.assertEqual(summary[0]['harness_error'], 'RuntimeError')
            self.assertEqual(summary[1]['outcome'], 'no_submission')


if __name__ == '__main__':
    unittest.main()


@pytest.mark.parametrize('event,exit_code,category', [
    ({'type': 'error', 'error': {'code': 'insufficient_quota'}}, 1, 'quota_exhausted'),
    ({'type': 'error', 'error': {'type': 'authentication_error'}}, 1, 'authentication'),
    ({'type': 'turn.failed', 'error': {'code': 'rate_limit_exceeded'}}, 1, 'rate_limit'),
    ({'type': 'assistant', 'text': 'insufficient_quota'}, 3, 'unknown'),
    ({}, -9, 'harness_crash'),
])
def test_failure_uses_evidence_not_exit_code_or_assistant_text(tmp_path, event, exit_code, category):
    from benchmarking.participants.recovery import harness_failure
    (tmp_path / 'harness.jsonl').write_text(json.dumps(event) + '\n')
    assert harness_failure(tmp_path, exit_code)['category'] == category


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
    def launch(condition, env, *args):
        observed.append(dict(env))
        if len(observed) == 1:
            return [sys.executable, '-c', f'import sys; print({events!r}); sys.exit(1)']
        return [sys.executable, '-c', 'import os; print(os.environ["ICLAYOUT_BENCH_TOKEN"]); print(os.environ["PROVIDER_API_KEY"])']
    with patch('benchmarking.participants.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.runner.command', side_effect=launch), \
            patch.object(fixture, 'create', wraps=fixture.create) as create:
        first = run_one(fixture, row, output, (selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}))
        assert first['state'] == 'suspended'
        assert first['failure']['category'] == 'quota_exhausted'
        assert fixture.closed == []
        fixture.remaining = 30  # Human billing wait did not reset the service clock.
        second = run_one(fixture, row, output, (selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}))
        assert create.call_count == 1
        assert second['state'] == 'finished'
        assert observed[1]['ICLAYOUT_BENCH_RESUME_ID'] == observed[0]['ICLAYOUT_BENCH_NATIVE_ID']
        assert (output / 'launch-1-harness.jsonl').exists()
        # A repeated collection must not re-launch or overwrite finished exports.
        run_participant(fixture, row, output, selected, {}, {})
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
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    calls = []
    def run(*args):
        calls.append(args)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return terminal_files(args[2]) | {'state': 'finished', 'harness_error': None}
    monkeypatch.setattr('benchmarking.run.run_one', run)
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
    # A historical batch must not gain new case-format measurements on upgrade.
    historical = tmp_path / 'historical'
    historical.mkdir()
    evidence = historical / 'batch.json'
    evidence.write_bytes(b'{"identity": "retained historical execution"}')
    original = evidence.read_bytes()
    for flags in ([], ['--resume']):
        with pytest.raises(SystemExit):
            main(args[:-1] + [str(historical)] + flags)
    assert list(historical.iterdir()) == [evidence]
    assert evidence.read_bytes() == original
    assert len(calls) == 3


def test_concurrent_batch_resume_cannot_launch(tmp_path, monkeypatch):
    from benchmarking.participants.storage import CaseLease
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    batch = tmp_path / 'batch'
    batch.mkdir()
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    (batch / 'test').mkdir()
    with CaseLease(batch / 'test'), patch('benchmarking.run.run_one') as launch, pytest.raises(SystemExit):
        main(['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(batch), '--resume'])
    launch.assert_not_called()


def test_quota_halts_related_dispatch_without_creating_extra_repetitions(tmp_path, monkeypatch):
    from benchmarking.participants.recovery import failure
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=3\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'secret')
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    with patch('benchmarking.run.run_one', return_value={'state': 'suspended', 'harness_error': 'billing',
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
            'task_id': 'fixture', 'task_sha256': 'b' * 64, 'condition': {}, 'tool_identity': {}, 'limits': {},
            'creation_key': 'create', 'creation_body': {'task_id': 'fixture', 'condition': {}},
            'submissions': {'accepted': receipt}, 'executions': {'e': {'execution_id': 'e', 'state': 'running',
            'exit_code': None, 'truncated': False, 'log_size': 0}},
            'requests': {'submissions:same': {'body': {'path': 'answer.gds'}, 'status': 200, 'response': receipt}}}
    (root / sid / 'http.json').write_text(json.dumps(data))
    service = LocalService(root, load_task(executable_case), {}, {}, 'unused', 'access', seconds=60)
    try:
        _, status = service.handle('GET', f'/v1/sessions/{sid}', {}, 'scoped', None, None)
        assert status['state'] == 'error'
        assert status['active_execution_id'] is None
        assert status['deadline'] == data['deadline']
        _, replay = service.handle('POST', f'/v1/sessions/{sid}/submissions', {}, 'scoped', {'path': 'answer.gds'}, 'same')
        assert replay == receipt
        with pytest.raises(APIError):
            service.handle('POST', f'/v1/sessions/{sid}/executions', {}, 'scoped', {'command': 'increment'}, 'new')
        _, result = service.handle('GET', f'/v1/sessions/{sid}/result', {}, 'scoped', None, None)
        assert result['failure_category'] == 'service_failure'
        assert result['score'] is None
        # Unacknowledged creation after restart must never create a replacement.
        with pytest.raises(APIError):
            service.handle('POST', '/v1/sessions', {}, 'access', data['creation_body'], 'create')
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
            patch('benchmarking.participants.runner.command', return_value=[sys.executable, '-c', 'print("done")']) as launch:
        with patch.object(fixture, 'close', side_effect=lost), pytest.raises(ClientError):
            run_participant(fixture, row, output, selected, {}, {})
        result, _ = run_participant(fixture, row, output, selected, {}, {})
        assert result['state'] == 'complete'
        assert launch.call_count == 1


def test_batch_resume_rejects_changed_prepared_input(tmp_path, monkeypatch):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    prepared = tmp_path / 'prepared'
    prepared.mkdir()
    (prepared / 'case').mkdir()
    (prepared / 'case/case.toml').write_text('id="test"')
    asset = prepared / 'netlist'
    asset.write_text('original input')
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    monkeypatch.setattr('benchmarking.run.service', lambda *args: nullcontext(ServiceFixture()))
    with patch('benchmarking.run.run_one', side_effect=lambda a, r, out, s: terminal_files(out)) as launch:
        args = ['--config', str(config), '--prepared', str(prepared), '--output', str(tmp_path / 'batch')]
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
        run_one(fixture, row, output, (selected, {}, {}))
    fixture.active = False  # Service subsequently closes under its own deadline.
    with patch('benchmarking.participants.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.runner.subprocess.check_output', return_value='fixture-cli'):
        summary = run_one(fixture, row, output, (selected, {}, {}))
    assert summary['failure']['category'] == 'unknown'
    assert summary['harness_error'] == 'runner_interrupted'
    assert summary['outcome'] == 'no_submission'  # Independent service evidence is retained.


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
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    monkeypatch.setattr('benchmarking.run.run_one', run)
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


def test_local_case_list_routes_prepared_inputs_and_rejects_missing_cases(tmp_path, monkeypatch):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["a", "b"]\nconcurrency=2\nrepetitions=1\n')
    prepared = {}
    for task in ['a', 'b']:
        directory = tmp_path / task
        (directory / 'case').mkdir(parents=True)
        (directory / 'case/case.toml').write_text(f'id="{task}"')
        prepared[task] = directory
    routed = []
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    monkeypatch.setattr('benchmarking.run.service', lambda path, *args: nullcontext(path))
    def run(access, row, output, selection):
        assert access == prepared[row['task']]
        routed.append(row['task'])
        return terminal_files(output)
    monkeypatch.setattr('benchmarking.run.run_one', run)
    args = ['--config', str(config), '--output', str(tmp_path / 'batch'), '--prepared']
    with pytest.raises(SystemExit):
        main(args + [str(prepared['a'])])
    assert not routed
    assert not (tmp_path / 'batch').exists()
    assert main(args + [str(prepared['b']), str(prepared['a'])]) == 0
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
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: (selected, {}, {}))
    monkeypatch.setattr('benchmarking.run.Client', lambda *args, **kwargs: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.Client', lambda *args, **kwargs: fixture)
    monkeypatch.setattr('benchmarking.participants.runner.subprocess.check_output', lambda *args, **kwargs: 'fixture-cli')
    monkeypatch.setattr('benchmarking.run.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    with patch('benchmarking.participants.runner.command', return_value=[sys.executable, '-c',
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
    from benchmarking.participants.recovery import harness_failure
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
def test_default_results_use_cli_version_and_case_names_and_reuse_completed(tmp_path, monkeypatch, capsys, repetitions):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="gpt-6-astra"\neffort="medium"\n'
                      f'tasks=["library.cell", "other.cell"]\nconcurrency=1\nrepetitions={repetitions}\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    monkeypatch.setattr('benchmarking.run.harness_version', lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    args = ['--config', str(config), '--endpoint', 'http://localhost:1']
    with patch('benchmarking.run.run_one', side_effect=lambda a, r, out, s: terminal_files(out)) as launch:
        assert main(args) == 0
        root = tmp_path / 'results/codex-1.2.3-gpt-6-astra-medium'
        for task in ['library.cell', 'other.cell']:
            directory = root / task
            for repetition in range(1, repetitions + 1):
                slot = directory if repetitions == 1 else directory / f'repetition-{repetition}'
                assert json.loads((slot / 'result.json').read_text())['summary']['task'] == task
        assert {p.name for p in root.iterdir()} == {'library.cell', 'other.cell'}
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
    monkeypatch.setattr('benchmarking.run.harness_version', lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    monkeypatch.setattr('benchmarking.run.service', lambda *args: nullcontext(None))
    directories = []
    for task in ['old', 'new-a', 'new-b']:
        directory = tmp_path / task
        (directory / 'case').mkdir(parents=True)
        (directory / 'case/case.toml').write_text(f'id="{task}"')
        directories.append(str(directory))
    barrier = threading.Barrier(2)
    calls = []
    def run(access, row, output, selection):
        calls.append(row['task'])
        if row['task'] != 'old':
            barrier.wait(timeout=5)  # Cannot pass if the two new sessions are serialized.
        return terminal_files(output, 'pass')
    monkeypatch.setattr('benchmarking.run.run_one', run)
    configure(['old'], 1)
    args = ['--config', str(config), '--prepared']
    assert main(args + directories[:1]) == 0
    root = tmp_path / 'results/codex-1.2.3-fixture-medium'
    original = {str(p.relative_to(root / 'old')): p.read_bytes() for p in (root / 'old').rglob('*') if p.is_file()}
    manifest = (root / 'old/result.json').read_bytes()
    configure(['old', 'new-a', 'new-b'], 2)
    capsys.readouterr()
    assert main(args + directories) == 0
    printed = capsys.readouterr().out
    assert 'SKIP case=old ' in printed
    assert str(root / 'old/result.json') in printed
    assert sorted(calls) == ['new-a', 'new-b', 'old']
    assert original == {str(p.relative_to(root / 'old')): p.read_bytes() for p in (root / 'old').rglob('*') if p.is_file()}
    assert (root / 'old/result.json').read_bytes() == manifest
    assert {p.name for p in root.iterdir()} == {'old', 'new-a', 'new-b'}
    assert main(args + directories) == 0
    assert len(calls) == 3
    import shutil
    relocated = tmp_path / 'relocated'
    copied = relocated / 'results' / root.name / 'old'
    shutil.copytree(root / 'old', copied)
    configure(['old'], 1)
    monkeypatch.chdir(relocated)
    assert main(args + directories[:1]) == 0
    assert len(calls) == 3
    assert {p.name for p in copied.parent.iterdir()} == {'old'}
    monkeypatch.chdir(tmp_path)
    configure(['old', 'new-a', 'new-b'], 2)
    # Inputs are version-owned: changing the benchmark release rejects all dispatch.
    monkeypatch.setattr('benchmarking.run.package_version', lambda: {"version": "different", "commit": None})
    with pytest.raises(SystemExit):
        main(args + directories)
    assert len(calls) == 3


def test_startup_failure_is_durable_and_same_key_never_starts_another_worker(tmp_path, executable_case, monkeypatch):
    from benchmarking.service.server import APIError, LocalService
    from benchmarking.tasks import load_task
    task = load_task(executable_case)
    attempts = []
    def broken_startup(*args, **kwargs):
        attempts.append(1)
        raise OSError('resource archive unavailable')
    monkeypatch.setattr('benchmarking.service.server.run_session', broken_startup)
    monkeypatch.setattr('benchmarking.service.server.AttachedSession', lambda *args: object())
    body = {'task_id': task.id, 'condition': {'harness_kind': 'custom', 'harness_id': 'startup-test',
            'harness_version': '1', 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}}
    root = tmp_path / 'service'
    for _ in range(2):
        service = LocalService(root, task, {}, {}, 'unused', 'access', seconds=60)
        try:
            for _ in range(2):
                with pytest.raises(APIError):
                    service.handle('POST', '/v1/sessions', {}, 'access', body, 'same-create')
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
    from benchmarking.tasks import load_task
    task = load_task(executable_case)
    service = server_module.LocalService(tmp_path / 'service', task, {}, {}, 'unused', 'access', seconds=60)
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
    monkeypatch.setattr(server_module, 'threading', SimpleNamespace(
        Event=lambda: next(events), Lock=threading.Lock, Thread=threading.Thread))
    monkeypatch.setattr(server_module, 'AttachedSession', lambda image, callback:
                        SimpleNamespace(image_id='fixture-image', ready=callback))
    def provision(task, config, resources, backends, destination, *, session, **kwargs):
        assert release.wait(2)
        destination.mkdir()
        (destination / 'events.jsonl').write_text('')
        session.ready(SimpleNamespace(remaining=lambda: config.wall_seconds, active=False), None)
        return {'outcome': 'no_submission'}
    monkeypatch.setattr(server_module, 'run_session', provision)
    body = {'task_id': task.id, 'condition': {'harness_kind': 'custom', 'harness_id': 'startup-test',
            'harness_version': '1', 'model': 'none', 'prompt_sha256': None, 'configuration_sha256': None}}
    try:
        status, created = service.handle('POST', '/v1/sessions', {}, 'access', body, 'creation')
        assert status == 201
        assert created['limits']['wall_seconds'] == service.limits['wall_seconds']
        assert observed and observed[0] > service.limits['wall_seconds']
        assert service.handle('POST', '/v1/sessions', {}, 'access', body, 'creation') == (status, created)
        assert len(service.runs) == 1
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
    monkeypatch.setattr('benchmarking.run.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    result = {'outcome': 'error', 'failure': {'category': 'quota_exhausted', 'stop_dispatch': True}}
    with patch('benchmarking.run.run_one', side_effect=lambda a, r, out, s: terminal_files(out, 'error') | result) as launch:
        assert main(['--config', str(config), '--endpoint', 'https://fixture']) == 1
        assert launch.call_count == 1
    root = tmp_path / 'results/codex-1.2.3-fixture-high'
    assert {p.name for p in root.iterdir()} == {'first', 'second'}
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
        condition, env, settings = resolve('command', 'fixture-model', 'medium')
        output = tmp_path / str(index)
        result, error = run_participant(fixture, {'harness': 'command', 'task': task, 'scheme': scheme},
                                        output, condition, env, settings)
        assert error is None
        assert result['outcome'] == 'no_submission'
        assert result['score'] is None
        assert 'contract received' in (output / 'harness.jsonl').read_text()
        identities.append(fixture.condition['configuration_sha256'])
    assert identities[0] == identities[1]
    assert identities[0] != identities[2]


@pytest.mark.parametrize('harness', ['codex', 'claude-code'])
def test_declared_mcp_tool_is_enabled_without_putting_its_credentials_on_argv(tmp_path, harness):
    from benchmarking.participants.runner import command

    selected = {'harness': harness, 'model': 'fixture-model', 'effort_requested': 'medium', 'effort_resolved': 'medium'}
    settings = {'mcp_servers': {'a': {'command': '/tools/a', 'args': ['serve'], 'env': {'A_API_KEY': 'private-key'}}}}
    argv = command(selected, {'ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS': '60'}, settings, tmp_path / 'mcp.json', tmp_path)
    assert 'private-key' not in ' '.join(argv)
    if harness == 'codex':
        assert 'mcp_servers.a.command="/tools/a"' in argv
        assert 'mcp_servers.a.env_vars=["A_API_KEY"]' in argv
    else:
        assert 'mcp__a' in argv[argv.index('--allowedTools') + 1]
        assert 'mcp_servers' not in json.loads(argv[argv.index('--settings') + 1])
