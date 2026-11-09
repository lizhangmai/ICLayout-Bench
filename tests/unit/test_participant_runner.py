"""Native runner lifecycle tests use subprocess fixtures, never a model provider."""
import copy
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest
from helpers.harness import FixtureRuntime, codex_tool_reply, native_session
from helpers.participant import InFlightService, ServiceFixture, terminal_files

from benchmarking.client import ClientError
from benchmarking.participants.attempt.runner import run_participant
from benchmarking.participants.harnesses.contracts import (
    LaunchContext,
    ParticipantSelection,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def external_runtime_boundaries(monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.attempt.worker import execute_owned_slot
    monkeypatch.setattr("benchmarking.participants.batch.worker.supervise_slot", execute_owned_slot)
    monkeypatch.setattr("benchmarking.participants.batch.plan.DockerSession", lambda image: SimpleNamespace(image_id=image))
    monkeypatch.setattr("benchmarking.participants.batch.plan.harness_version", lambda _: ("1.2.3", "fixture-cli 1.2.3"))

    monkeypatch.setattr('benchmarking.participants.attempt.runner.NativeRuntime', FixtureRuntime)


def write_dataset(root, names):
    from helpers.protocol import write_protocol_task
    for name in names:
        config = write_protocol_task(root / 'tasks' / name.split('.')[0] / 'fixture/cases' / name)
        (config.parent / 'case.toml').write_text(config.read_text().replace('protocol-test', name))
        process = root / 'tasks' / name.split('.')[0]
        process.mkdir(parents=True, exist_ok=True)
        (process / 'pdk.toml').write_text('id="fixture"\n')
    return root


def case_run(root, task):
    directory, = (root / task).iterdir()
    return directory


@pytest.mark.parametrize('collect_only', [False, True])
def test_checkpoint_failure_retains_case_recovery_until_explicit_collection(tmp_path, monkeypatch, collect_only):
    from benchmarking.participants.attempt.runner import run_one

    result = {'state': 'error', 'session_id': 'session', 'failure_category': 'service_failure',
              'failure_reason': 'checkpoint_timeout', 'failure_scope': 'session', 'submission': None,
              'outcome': 'error', 'score': None, 'task_success': None, 'evaluation_mode': 'self_run'}
    for name in ('run_participant', 'recover_participant'):
        monkeypatch.setattr('benchmarking.participants.attempt.runner.'+name, lambda *a: (result, None))
    summary = run_one(None, {'name': 'condition'}, tmp_path, ParticipantSelection({}, {}, {}), collect_only=collect_only)
    assert summary['state'] == ('finished' if collect_only else 'suspended')
    assert summary['score'] is None
    assert summary['failure']['scope'] == 'session' and not summary['failure']['stop_dispatch']


def test_initial_prompt_contains_problem_verbatim_without_serializing_the_task_plan(tmp_path, monkeypatch):
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
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare', lambda context: ['fixture'])
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.cli_version', lambda *a: 'fixture')
    prompts = []

    def execute(argv, *, prompt, **kwargs):
        prompts.append(prompt)
        assert prompt == problem
        assert 'evaluator-only-' not in prompt
        assert len(prompt) < 10_000
        return 0, False

    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', execute)
    selection = ParticipantSelection({'model': 'fixture', 'effort_resolved': 'low'}, {}, {})
    result, error = run_participant(fixture, {'harness': 'command', 'task': 'fixture'}, tmp_path, selection)
    assert error is None and result['outcome'] == 'no_submission'
    assert len(prompts) == 1


@pytest.mark.parametrize('harness', ['codex', 'claude-code', 'command'])
def test_failed_harness_drains_execution_before_shared_finalization(tmp_path, monkeypatch, harness):
    import sys

    from benchmarking.participants.attempt.recovery import DISABLED
    from benchmarking.participants.attempt.runner import run_one
    from benchmarking.participants.harnesses.scheme import resolve_scheme

    fixture = InFlightService()
    selected = {'harness': harness, 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': harness, 'task': 'fixture', 'recovery': DISABLED}
    argv = [sys.executable, '-c', 'import sys; print("participant interrupted"); sys.exit(7)']
    if harness == 'command':
        row['scheme'] = resolve_scheme({'version': 'fixture', 'launch': {'command': argv, 'files': []}}, tmp_path, harness)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare', lambda *a: argv)
    output = tmp_path / 'participant'
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
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


def test_finalization_retains_only_participant_accepted_snapshot(tmp_path):
    from benchmarking.participants.attempt.runner import finalize_session
    fixture = InFlightService(race=True)
    fixture.condition = {}
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    receipt = {'submission_id': 'explicit', 'sequence': 1, 'candidate_sha256': 'a' * 64}
    session, result = fixture.session, fixture.result
    fixture.session = lambda sid: dict(session(sid), last_submission=receipt)
    fixture.result = lambda sid: dict(result(sid), submission=receipt)
    outcome = finalize_session(fixture, 'fixture-session', tmp_path)
    assert outcome['submission'] == receipt
    assert not fixture.submitted
    assert fixture.closed == ['fixture-session']
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['receipt'] == receipt and record['submission'] == 'retained'


@pytest.mark.parametrize('state', ['evaluating', 'complete', 'error'])
@pytest.mark.parametrize('close_race', [False, True])
def test_finalization_collects_a_session_closed_by_the_service(tmp_path, monkeypatch, state, close_race):
    from benchmarking.participants.attempt.runner import finalize_session

    fixture = InFlightService(race=True)
    fixture.condition = {}
    receipt = {'submission_id': 'accepted', 'sequence': 21, 'candidate_sha256': 'a' * 64}
    observed = {'state': 'active' if close_race else state}
    monkeypatch.setattr(fixture, 'session', lambda _: {
        'state': observed['state'], 'remaining_seconds': 0,
        'active_execution_id': None, 'last_submission': receipt,
    })

    def close(*args, **kwargs):
        observed['state'] = state
        raise ClientError('session_closed', 'Session closed', status=410)

    monkeypatch.setattr(fixture, 'close', close)
    original_result = fixture.result
    monkeypatch.setattr(fixture, 'result', lambda sid: dict(original_result(sid), submission=receipt))
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    (tmp_path / 'harness-summary.json').write_text(json.dumps({
        'finalization_error': {'error': 'ClientError', 'failure': {'code': 'session_closed'}},
    }))

    result = finalize_session(fixture, 'fixture-session', tmp_path)

    assert result['submission'] == receipt and result['state'] == 'complete'
    assert (tmp_path / 'observation/manifest.json').is_file()
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['closed'] and record['receipt'] == receipt and record['close_error'] is None
    assert 'finalization_error' not in json.loads((tmp_path / 'harness-summary.json').read_text())
    assert not fixture.submitted


def test_finalization_does_not_hide_session_closed_without_a_closed_state(tmp_path, monkeypatch):
    from benchmarking.participants.attempt.settlement import settle_session

    fixture = InFlightService(race=True)
    def close(*args, **kwargs):
        raise ClientError('session_closed', 'Workspace is unavailable', status=410)
    monkeypatch.setattr(fixture, 'close', close)
    with pytest.raises(ClientError, match='Workspace is unavailable'):
        settle_session(fixture, 'fixture-session', tmp_path)
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert not record['closed'] and record['close_error']['code'] == 'session_closed'


def test_finalization_command_expiry_retains_accepted_candidate(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.attempt.runner import finalize_session
    fixture = InFlightService()
    fixture.condition = {}
    receipt = {'submission_id': 'earlier', 'sequence': 1, 'candidate_sha256': 'a' * 64}
    old_session = fixture.session
    fixture.session = lambda sid: dict(old_session(sid), last_submission=receipt,
        budget={'command_remaining_seconds': 1})
    fixture.poll = lambda sid, eid, offset=0: {'execution_id': eid, 'state': 'running', 'exit_code': None,
                                            'log_base64': '', 'next_offset': offset, 'truncated': False}
    clock = [0]
    def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr('benchmarking.participants.attempt.settlement.time', SimpleNamespace(
        monotonic=lambda: clock[0], time=lambda: clock[0], sleep=sleep))
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')
    result = fixture.result
    monkeypatch.setattr(fixture, 'result', lambda sid: dict(
        result(sid), submission=receipt, outcome='fail',
        score={'method': 'layout', 'maximum': 100, 'reference': 100, 'value': 0.0}))
    observed = finalize_session(fixture, 'fixture-session', tmp_path)
    assert observed['submission'] == receipt and observed['score']['value'] == 0.0
    evidence = json.loads((tmp_path / 'finalization.json').read_text())
    assert evidence['receipt'] == receipt and evidence['closed']
    assert evidence['error']['error'] == 'TimeoutError'
    assert fixture.closed == ['fixture-session'] and not fixture.submitted


@pytest.mark.parametrize('score', [0.0, 87.5])
def test_finalization_collects_accepted_candidate_after_drain_timeout(tmp_path, monkeypatch, score):
    from benchmarking.participants.attempt.runner import finalize_session

    fixture = InFlightService()
    fixture.condition = {}
    receipt = {'submission_id': 'final', 'sequence': 4, 'candidate_sha256': 'a' * 64}
    session, result = fixture.session, fixture.result
    monkeypatch.setattr(fixture, 'session', lambda sid: dict(session(sid), last_submission=receipt))
    monkeypatch.setattr(fixture, 'result', lambda sid: dict(
        result(sid), submission=receipt, outcome='pass' if score else 'fail',
        score={'method': 'layout', 'maximum': 100, 'reference': 100, 'value': score}))

    def poll(*args, **kwargs):
        raise TimeoutError('execution polling timed out')

    monkeypatch.setattr(fixture, 'poll', poll)
    (tmp_path / '.private').mkdir()
    (tmp_path / '.private/recovery.json').write_text('{"redactions": []}')

    observed = finalize_session(fixture, 'fixture-session', tmp_path)

    assert observed['state'] == 'complete' and observed['score']['value'] == score
    assert observed['submission'] == receipt and not fixture.submitted
    assert (tmp_path / 'observation/manifest.json').is_file()
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['closed'] and record['error']['error'] == 'TimeoutError'


def test_finalization_keeps_primary_error_when_close_also_fails(tmp_path, monkeypatch):
    from benchmarking.participants.attempt.runner import finalize_session
    fixture = InFlightService(conflict=True)
    def close(*a, **kw):
        raise ClientError('transport_error', 'response lost')
    monkeypatch.setattr(fixture, 'close', close)
    with pytest.raises(ClientError) as caught:
        finalize_session(fixture, 'fixture-session', tmp_path)
    assert caught.value.code == 'conflict'
    evidence = json.loads((tmp_path / 'finalization.json').read_text())
    assert evidence['error']['code'] == 'conflict'
    assert evidence['close_error']['code'] == 'transport_error'
    assert not evidence['closed']


def test_operator_interruption_is_not_replaced_by_transport_failure_during_close(tmp_path, monkeypatch):
    from benchmarking.participants.attempt.settlement import settle_session

    fixture = InFlightService()
    def interrupted(*a, **kw):
        raise KeyboardInterrupt
    def close(*a, **kw):
        raise ClientError('transport_error', 'service shutting down')
    monkeypatch.setattr(fixture, 'session', interrupted)
    monkeypatch.setattr(fixture, 'close', close)
    with pytest.raises(KeyboardInterrupt):
        settle_session(fixture, 'fixture-session', tmp_path)
    record = json.loads((tmp_path / 'finalization.json').read_text())
    assert record['error']['code'] == 'operator_interrupted'
    assert record['close_error']['code'] == 'transport_error'


@pytest.mark.parametrize('failure_code', ['conflict', 'infrastructure_error', 'result_transport'])
def test_unrelated_finalization_conflict_retains_original_harness_failure(tmp_path, monkeypatch, failure_code):
    import sys

    from benchmarking.run import main
    fixture = InFlightService(conflict=failure_code != 'result_transport')
    tasks = ['fixture', 'untouched'] if failure_code == 'infrastructure_error' else ['fixture']
    if failure_code == 'infrastructure_error':
        def poll(sid, eid, *, offset=0):
            raise ClientError(failure_code, 'service unavailable', status=500)
        monkeypatch.setattr(fixture, 'poll', poll)
    if failure_code == 'result_transport':
        def result(sid):
            raise ClientError('transport_error', 'response lost')
        monkeypatch.setattr(fixture, 'result', result)
    config = tmp_path / 'trial.toml'
    config.write_text('harness="claude-code"\nmodel="fixture"\neffort="high"\n'
                      f'tasks={json.dumps(tasks)}\nconcurrency=1\nrepetitions=1\n'
                      '[recovery]\nhttp_attempts=1\nbackoff_seconds=0\nmax_backoff_seconds=0\nresume_session=false\n')
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *a: ParticipantSelection(selected, {}, {}))
    monkeypatch.setattr('benchmarking.participants.attempt.service.service', lambda *a: nullcontext(fixture))
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare', lambda *a: [sys.executable, '-c', 'import sys; sys.exit(7)'])
    dataset = write_dataset(tmp_path / 'dataset', tasks)
    output = tmp_path / 'batch'
    assert main(['--config', str(config), '--dataset', str(dataset), '--output', str(output)]) == 1
    result = json.loads((case_run(output, 'fixture') / 'result.json').read_text())
    assert result['summary']['harness_error'] == 'cli_exit_7'
    assert result['summary']['failure']['source'] == 'harness_exit'
    assert result['summary']['finalization_error']['failure']['code'] == ('transport_error' if failure_code == 'result_transport' else failure_code)
    assert not fixture.submitted
    assert fixture.closed == ['fixture-session']
    if len(tasks) > 1:
        assert json.loads((case_run(output, 'untouched') / 'result.json').read_text())['state'] == 'finished'


class LifecycleTests(unittest.TestCase):
    def exercise(self, code, seconds):
        import sys

        from benchmarking.participants.attempt.recovery import DISABLED
        fixture = ServiceFixture()
        fixture.remaining = seconds
        selected = {'harness': 'claude-code', 'model': 'fixture-model', 'effort_resolved': 'xhigh',
                    'effort_requested': None, 'effort_source': 'test', 'provider_effective_effort': None}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'run'
            with patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
                    patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli'), \
                    patch('benchmarking.participants.harnesses.registry.prepare', return_value=[sys.executable, '-c', code]):
                result, error = run_participant(fixture, {'harness': 'claude-code', 'task': 'fixture', 'recovery': DISABLED}, output, ParticipantSelection(copy.deepcopy(selected), {}, {}))
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
                patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
                patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli'), \
                patch('benchmarking.participants.harnesses.registry.prepare') as launch:
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
                fixture = ServiceFixture()
                fixture.remaining = 3 * 3600
                selected = ParticipantSelection({'harness': 'claude-code', 'model': 'fixture-model',
                             'effort_resolved': 'high', 'effort_requested': None}, {}, {})

                def local_service(prepared, output, image, recoverable, batch=batch, fixture=fixture):
                    self.assertEqual(output, case_run(batch, 'fixture') / '.runtime/service')
                    (output / 'service.log').write_text('fixture service')
                    return nullcontext(fixture)

                with patch('benchmarking.participants.batch.plan.default_output', return_value=batch), \
                        patch('benchmarking.participants.batch.plan.resolve', return_value=selected), \
                        patch('benchmarking.participants.attempt.worker.Client', return_value=fixture), \
                        patch('benchmarking.participants.attempt.service.service', side_effect=local_service), \
                        patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
                        patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli 1.2.3'), \
                        patch('benchmarking.participants.harnesses.registry.prepare', return_value=[sys.executable, '-c', 'print("done")']), \
                        patch.dict('os.environ', {'ICLAYOUT_BENCH_ENDPOINT': ''}), \
                        patch('builtins.print'):
                    mode = ['--dataset', directory] if local else ['--endpoint', fixture.endpoint]
                    code = main(['--config', str(config), *mode])
                self.assertEqual(code, 0)
                case_path = str(case_run(batch, 'fixture').relative_to(batch))
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
            with patch('benchmarking.participants.batch.plan.default_output', side_effect=lambda group: root / Path(group).name), \
                    patch('benchmarking.participants.batch.plan.harness_version', return_value=('1.2.3', 'fixture 1.2.3')), \
                    patch('benchmarking.participants.batch.plan.resolve', return_value=selection), \
                    patch('benchmarking.participants.attempt.runner.run_one', side_effect=run), \
                    patch.dict('os.environ', {'ICLAYOUT_BENCH_TOKEN': 'fixture-token'}), \
                    patch('builtins.print'):
                code = main(['--matrix', str(matrix), '--endpoint', 'http://127.0.0.1:8765'])
            self.assertEqual(code, 1)
            summary = [json.loads(p.read_text())['summary'] for p in sorted(root.glob('*/test/*/result.json'))]
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
    with patch('benchmarking.participants.batch.runner.execute_condition', return_value=0) as execute:
        assert main(['--config', str(config)]) == 0
        assert execute.call_args.args[0].image == 'tools:configured'
        assert execute.call_args.args[3] == tmp_path / 'results/from-env'
        assert main(['--config', str(config), '--image', 'tools:explicit', '--output', 'results/explicit']) == 0
        assert execute.call_args.args[0].image == 'tools:explicit'
        assert execute.call_args.args[3] == tmp_path / 'results/explicit'
        monkeypatch.setenv('ICLAYOUT_BENCH_OUTPUT', '')
        assert main(['--config', str(config)]) == 0
        assert execute.call_args.args[3] == tmp_path / 'results/trial'
        first = execute.call_args.args[0].case_paths['library.cell']
        from datetime import datetime
        assert Path(first).parent == Path('library.cell')
        datetime.strptime(Path(first).name, '%Y%m%d-%H%M%S-%f').astimezone()
        assert main(['--config', str(config)]) == 0
        assert execute.call_args.args[3] == tmp_path / 'results/trial'
        assert execute.call_args.args[0].case_paths['library.cell'] != first
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


@pytest.mark.parametrize('kind', ['capacity', 'network'])
@pytest.mark.parametrize('scenario,expected', [
    ('ready', 'waiting'), ('limit', 'limit_reached'), ('disabled', 'limit_reached'),
    ('closed', 'deadline'), ('expired', 'deadline'), ('missing_native', 'native_session_missing'),
    ('retry_after', 'retry_after_exceeds_cap'), ('insufficient_budget', 'deadline'),
])
def test_resume_policy_bounds_waiting_without_changing_session(monkeypatch, kind, scenario, expected):
    from benchmarking.participants.attempt import recovery

    settings = recovery.policy({kind + '_resumes': 0 if scenario == 'disabled' else 2})
    monkeypatch.setattr(recovery, kind + '_delay', lambda settings, count: 30)
    status = {'state': 'complete' if scenario == 'closed' else 'active',
              'remaining_seconds': 0 if scenario == 'expired' else 20 if scenario == 'insufficient_budget' else 1000}
    problem = {'retry_after': 400} if scenario == 'retry_after' else {}
    native_id = None if scenario == 'missing_native' else 'original-native-thread'
    before = copy.deepcopy((settings, status, problem))
    decision = getattr(recovery, 'plan_' + kind + '_resume')(
        settings, 2 if scenario == 'limit' else 0, problem, status, native_id)
    assert decision.outcome == expected
    assert (settings, status, problem) == before
    if scenario == 'ready':
        assert decision.native_id == native_id and decision.delay_seconds == 30


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
def test_native_continuation_preserves_session_budget_and_evidence(tmp_path, monkeypatch, kind, harness, scenario):
    """Shared recovery runs real child processes; adapters own native error variants."""
    import sys
    from types import SimpleNamespace

    from benchmarking.execution.process import execute as actual_execute
    from benchmarking.participants.attempt.recovery import DISABLED
    from benchmarking.participants.attempt.runner import CONTINUE_PROMPT, run_one

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
    launches, prompts, delays, timeouts = [], [], [], []
    clock = [0]
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

    def sleep(seconds):
        delays.append(seconds)
        clock[0] += seconds
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

    monkeypatch.setattr(fixture, 'session', session)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare', launch)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', execute)
    monkeypatch.setattr('benchmarking.participants.attempt.recovery.' + kind + '_delay', lambda settings, count: min(300, 30 * 2 ** count))
    monkeypatch.setattr('benchmarking.participants.attempt.runner.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    with patch.object(fixture, 'create', wraps=fixture.create) as create:
        summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
        assert create.call_count == 1
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
        assert timeouts == ([1000, 970, 910] if stop == 'limit' else [1000, 970] if len(launches) == 2 else [1000])
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
            assert summary['harness_error'] is None and delays == [30]
            assert summary['failure']['category'] == 'task_failure'
        if scenario == 'rotated_credentials':
            for path in (output / 'observation').rglob('*'):
                if path.is_file():
                    assert b'rotated-native-secret-1' not in path.read_bytes()
                    assert b'rotated-native-secret-2' not in path.read_bytes()
            assert b'rotated-native-secret-1' in (output / 'launch-1-harness.jsonl').read_bytes()
        if kind == 'network' and stop == 'limit':
            assert delays == [30, 60] and summary[key]['resumes'] == 2
            assert (output / '.private/recovery.json').is_file()
            manually_recovered[0] = True
            fixture.remaining, fixture.busy = 30, True
            resumed = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
            assert create.call_count == 1 and resumed['state'] == 'finished'
            assert resumed[key]['outcome'] == 'recovered' and timeouts[-1] == 30


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
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *a: ParticipantSelection(selected, {'CODEX_HOME': str(tmp_path / 'caller-home')}, {}))
    monkeypatch.setattr('benchmarking.participants.attempt.service.service', lambda *a: nullcontext(fixture))
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.subprocess.check_output', lambda *a, **kw: 'fixture-cli')

    def launch(context):
        env = context.selection.environment
        launches.append(dict(env))
        native_session(context.output, 'codex', 'original-thread')
        event = ({'type': 'error', 'message': 'Selected model is at capacity. Please try a different model.'}
                 if len(launches) == 1 else {'type': 'turn.completed'})
        thread = json.dumps({'type': 'thread.started', 'thread_id': 'original-thread'})
        return [sys.executable, '-c', f'import sys; print({thread!r}); print({json.dumps(event)!r}); sys.exit({int(len(launches) == 1)})']

    def sleep(seconds):
        clock[0] += seconds
        fixture.remaining -= seconds

    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare', launch)
    monkeypatch.setattr('benchmarking.participants.attempt.recovery.capacity_delay', lambda *a: 30)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    batch = tmp_path / 'batch'
    assert main(['--config', str(config), '--dataset', str(dataset), '--output', str(batch)]) == 0
    case = case_run(batch, 'fixture')
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
@pytest.mark.parametrize('harness,category', [('codex', 'provider_overloaded'), ('zcode', 'rate_limit')])
def test_repeated_capacity_interruptions_cool_only_related_new_dispatch(tmp_path, monkeypatch, third_case, harness, category):
    from types import SimpleNamespace

    from benchmarking.run import main

    tasks = ['a', 'b', 'c'] if third_case else ['a', 'b']
    matrix = tmp_path / 'trial.toml'
    matrix.write_text(f'[defaults]\nharness="{harness}"\neffort="high"\nconcurrency=1\nrepetitions=1\n'
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
            result['capacity_recovery'] = {'interruptions': [{'failure': {'category': category}}]}
        return result
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda harness, model, effort: ParticipantSelection({'harness': harness, 'model': model}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.batch.plan.default_output', lambda group: tmp_path / Path(group).name)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
    monkeypatch.setattr('benchmarking.participants.batch.runner.time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    assert main(['--matrix', str(matrix), '--endpoint', 'https://fixture']) == 0
    expected_clock = 300 if third_case else 0
    assert calls[:2] == [('first', 'a', 0), ('first', 'b', 0)]
    assert calls[-1] == ('second', 'a', expected_clock)
    if third_case:
        assert calls[2] == ('first', 'c', 300)


@pytest.mark.parametrize('harness,service_restarted', [
    ('codex', False), ('codex', True), ('claude-code', False),
])
def test_same_session_resume_preserves_budget_and_private_credentials(tmp_path, service_restarted, harness):
    import sys

    from benchmarking.participants.attempt.runner import run_one
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
    with patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.harnesses.registry.prepare', side_effect=launch), \
            patch.object(fixture, 'create', wraps=fixture.create) as create:
        first = run_one(fixture, row, output, ParticipantSelection(selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}))
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
        second = run_one(fixture, row, output, ParticipantSelection(selected, {"PROVIDER_API_KEY": "fixture-api-secret"}, {}))
        assert create.call_count == 1
        assert second['state'] == 'finished'
        assert observed[1]['ICLAYOUT_BENCH_RESUME_ID'] == observed[0]['ICLAYOUT_BENCH_NATIVE_ID']
        if service_restarted:
            assert 'interrupted-write' in (output / 'tools.jsonl').read_text()
            assert 'interrupted-command' in prompts[1] and 'rolled back' in prompts[1]
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
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    calls = []
    def run(*args):
        calls.append(args)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return terminal_files(args[2]) | {'state': 'finished', 'harness_error': None}
    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
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
    from benchmarking.participants.attempt.storage import CaseLease
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    batch = tmp_path / 'batch'
    batch.mkdir()
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    (batch / 'test').mkdir()
    with CaseLease(batch / 'test'), patch('benchmarking.participants.attempt.runner.run_one') as launch, pytest.raises(SystemExit):
        main(['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(batch), '--resume'])
    launch.assert_not_called()


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


def test_explicit_replacement_keeps_failed_attempt_and_pending_plan_in_same_batch(tmp_path, monkeypatch):
    from benchmarking.files import write_json as save
    from benchmarking.run import main

    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["interrupted", "finished", "pending"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *a: ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.batch.plan.package_version', lambda: {'version': 'old', 'commit': 'old'})
    batch = tmp_path / 'batch'
    calls = []
    closed = ServiceFixture()
    closed.active = False
    monkeypatch.setattr('benchmarking.participants.batch.replacement.Client', lambda *a, **kw: closed)
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
    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(batch)]
    assert main(args + ['--case', 'interrupted', '--case', 'finished']) == 1
    interrupted = case_run(batch, 'interrupted')
    finished = case_run(batch, 'finished')
    failed = json.loads((interrupted / 'result.json').read_text())
    original_finished = (finished / 'result.json').read_bytes()
    pending = copy.deepcopy(failed)
    pending.pop('summary')
    pending['state'] = 'pending'
    pending['identity']['plan'][0]['tasks'] = ['pending']
    pending_root = batch / 'pending' / interrupted.name
    pending_root.mkdir(parents=True)
    save(pending_root / 'result.json', pending)
    monkeypatch.setattr('benchmarking.participants.batch.plan.package_version', lambda: {'version': 'repaired', 'commit': 'repaired'})
    selected = args + ['--case', 'interrupted', '--case', 'pending']
    with pytest.raises(SystemExit):
        main(args + ['--case', 'interrupted', '--case', 'finished', '--replace-unfinished'])
    assert json.loads((interrupted / 'result.json').read_text()) == failed
    with pytest.raises(SystemExit):
        main(selected + ['--resume'])
    assert main(selected + ['--replace-unfinished']) == 0
    assert calls == ['interrupted', 'finished', 'interrupted', 'pending']
    result = json.loads((interrupted / 'result.json').read_text())
    assert result['identity']['benchmark']['commit'] == 'repaired'
    attempt, = result['attempts']
    assert attempt['record'] == failed
    assert attempt['conditions'] == {'framework': 'old'}
    assert attempt['execution']['error'] == 'capacity_failure'
    assert b'old-scoped-token' not in (interrupted / next(f for f in result['files'] if f.startswith('attempts/') and f.endswith('agent.jsonl'))).read_bytes()
    assert json.loads((pending_root / 'result.json').read_text())['prior_plans'] == [pending]
    assert (finished / 'result.json').read_bytes() == original_finished
    assert not (interrupted / '.runtime').exists()
    with pytest.raises(SystemExit):
        main(selected + ['--replace-unfinished'])
    assert calls == ['interrupted', 'finished', 'interrupted', 'pending']


@pytest.mark.parametrize('changed', ['model', 'effort', 'image', 'inputs', 'endpoint', 'repetitions'])
def test_replacement_rejects_changed_solve_conditions(tmp_path, changed):
    from benchmarking.files import write_json as save
    from benchmarking.participants.batch.replacement import validate_replacement
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
    from benchmarking.participants.attempt import storage
    from benchmarking.participants.batch import replacement
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

    from benchmarking.execution.leases import BatchLease
    from benchmarking.participants.batch.replacement import lease_replacement
    store = tmp_path / '.runtime/service/service-store'
    store.mkdir(parents=True)
    with BatchLease(store), ExitStack() as stack, pytest.raises(OSError):
        lease_replacement(tmp_path, stack)


def test_finished_case_cleanup_waits_for_live_evidence_store(tmp_path):
    from benchmarking.execution.leases import BatchLease
    from benchmarking.participants.attempt.storage import CaseRecord
    from benchmarking.participants.attempt.worker import finish_case

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
    from benchmarking.participants.batch.replacement import validate_replacement
    identity = {'endpoint': 'https://fixture', 'plan': [{'model': 'fixture'}]}
    save(tmp_path / 'result.json', {'identity': identity, 'state': 'suspended'})
    (tmp_path / '.runtime/participant/.private').mkdir(parents=True)
    save(tmp_path / '.runtime/participant/.private/recovery.json',
         {'created': {'session_id': 'old', 'session_token': 'scoped-token'}})
    fixture = ServiceFixture()
    monkeypatch.setattr('benchmarking.participants.batch.replacement.Client', lambda *a, **kw: fixture)
    with pytest.raises(ValueError, match='Collect the existing remote'):
        validate_replacement(tmp_path, identity)


@pytest.mark.parametrize('harness,provider_code', [
    ('codex', None), ('kimi-code', None), ('zcode', '1308'), ('zcode', '1310'),
])
def test_fatal_provider_errors_halt_related_dispatch_without_creating_extra_repetitions(
        tmp_path, monkeypatch, harness, provider_code):
    from benchmarking.participants.harnesses import registry as adapters
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text(f'harness="{harness}"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=3\n')
    (tmp_path / 'harness.jsonl').write_text('{"type":"error","code":"insufficient_quota"}\n' if harness == 'codex' else '')
    if harness == 'zcode':
        event = json.loads((Path(__file__).parents[1] / f'fixtures/agents/zcode-{provider_code}.json').read_text())
        (tmp_path / 'harness.jsonl').write_text(json.dumps(event) + '\n')
    if harness == 'kimi-code':
        (tmp_path / 'harness.stderr').write_text('error: failed to run prompt: The provided authorization grant is invalid\n')
    problem = adapters.harness_failure(harness, tmp_path, exit_code=1)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'secret')
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({'harness': harness, 'model': 'fixture'}, {}, {}))
    with patch('benchmarking.participants.attempt.runner.run_one', return_value={'state': 'suspended', 'harness_error': 'cli_exit_1',
               'failure': problem}) as run:
        assert main(['--config', str(config), '--endpoint', 'http://localhost:1',
                     '--output', str(tmp_path / 'batch')]) == 1
    assert run.call_count == 1
    records = [json.loads(p.read_text()) for p in sorted((tmp_path / 'batch').rglob('result.json'))]
    assert len(records) == 3
    assert [r['state'] for r in records] == ['suspended', 'blocked', 'blocked']


def test_service_restart_terminates_lost_execution_and_preserves_receipt(tmp_path, executable_case):
    """Durable HTTP metadata after abrupt loss; no Docker or model is started."""
    import time

    from benchmarking.evidence.journal import RunRecorder
    from benchmarking.files import Asset
    from benchmarking.participants.attempt.evidence import read_participant_evidence
    from benchmarking.results.package import export_run
    from benchmarking.service.server import APIError, LocalService
    from benchmarking.tasks.contract import load_task
    runtime = tmp_path / '.runtime'
    root = runtime / 'service/service-store'
    sid = 'interrupted'
    (root / sid).mkdir(parents=True)
    candidate = Asset(b'accepted-before-reboot', 'gds')
    receipt = {'submission_id': '1', 'sequence': 1, 'candidate_sha256': candidate.sha256}
    data = {'session_id': sid, 'token': 'scoped', 'created_at': 'original-start', 'deadline': 'original-deadline',
            'deadline_epoch': time.time() + 60, 'retained_epoch': time.time() + 600,
            'task_id': 'fixture', 'task_sha256': 'b' * 64, 'condition': {}, 'tool_identity': {}, 'limits': {'wall_seconds': 60},
            'creation_key': 'create', 'creation_body': {'task_id': 'fixture', 'condition': {}},
            'submissions': {'accepted': receipt}, 'executions': {'e': {'execution_id': 'e', 'state': 'running',
            'exit_code': None, 'truncated': False, 'log_size': 0}},
            'requests': {'submissions:same': {'body': {'path': 'answer.gds'}, 'status': 200, 'response': receipt}}}
    (root / sid / 'http.json').write_text(json.dumps(data))
    recorder = RunRecorder(root / sid / 'run')
    frozen_task = recorder.archive(Asset(json.dumps({
        'task_sha256': data['task_sha256'], 'output': {'top_cell': 'fixture'},
    }).encode(), 'json'))
    recorder.save({'phase': 'running', 'task': frozen_task})
    recorder.event('submission', receipt={'accepted': True, 'sequence': 1, **candidate.identity()},
                   candidate=recorder.archive(candidate))
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
        participant = runtime / 'participant'
        (participant / 'analysis').mkdir(parents=True)
        (participant / 'analysis/result.json').write_text(json.dumps(result))
        exported = {'files': []}
        export_root = tmp_path / 'export'
        export_run(export_root, read_participant_evidence(runtime), exported)
        assert (export_root / 'final.gds').read_bytes() == candidate.content
        assert exported['evaluation']['submission'] == result['submission']
        assert exported['evaluation']['outcome'] == 'error'
        assert exported['evaluation']['score'] is None
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
    with patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.harnesses.registry.prepare', return_value=[sys.executable, '-c', 'print("done")']) as launch:
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
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.attempt.service.service', lambda *args: nullcontext(ServiceFixture()))
    with patch('benchmarking.participants.attempt.runner.run_one', side_effect=lambda a, r, out, s: terminal_files(out)) as launch:
        args = ['--config', str(config), '--dataset', str(dataset), '--output', str(tmp_path / 'batch')]
        assert main(args) == 0
        asset.write_text('different input')
        with pytest.raises(SystemExit):
            main(args + ['--resume'])
    assert launch.call_count == 1


def test_runner_interruption_is_not_inferred_as_a_model_failure(tmp_path):
    from benchmarking.participants.attempt.recovery import DISABLED
    from benchmarking.participants.attempt.runner import run_one
    fixture = ServiceFixture()
    selected = {'harness': 'claude-code', 'model': 'fixture', 'effort_resolved': 'high', 'effort_requested': 'high'}
    row = {'name': 'trial', 'harness': 'claude-code', 'task': 'fixture',
           'recovery': DISABLED | {'resume_session': True}}
    output = tmp_path / 'participant'
    with patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli'), \
            patch('benchmarking.participants.attempt.runner.subprocess.Popen', side_effect=KeyboardInterrupt), \
            pytest.raises(KeyboardInterrupt):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    fixture.active = False  # Service subsequently closes under its own deadline.
    with patch('benchmarking.participants.attempt.runner.Client', return_value=fixture), \
            patch('benchmarking.participants.attempt.runner.subprocess.check_output', return_value='fixture-cli'):
        summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    assert summary['failure']['category'] == 'unknown'
    assert summary['harness_error'] == 'runner_interrupted'
    assert summary['outcome'] == 'no_submission'  # Independent service evidence is retained.


def test_interrupted_runner_can_collect_without_native_continuation(tmp_path, monkeypatch):
    """A command has delivered its candidate; its supervisor dies before cleanup."""
    import sys

    from benchmarking.participants.attempt.runner import run_one
    from benchmarking.participants.harnesses.scheme import resolve_scheme

    fixture = InFlightService()
    selected = {'harness': 'command', 'model': 'fixture', 'effort_resolved': None}
    row = {'name': 'trial', 'harness': 'command', 'task': 'fixture',
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    output = tmp_path / 'participant'
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    assert json.loads((output / '.private/recovery.json').read_text())['phase'] == 'running'
    with pytest.raises(ValueError, match='Session continuation was not enabled'):
        run_one(fixture, row, output, ParticipantSelection(selected, {}, {}))
    def forbidden(*args, **kwargs):
        pytest.fail('Collection must never relaunch a participant')
    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', forbidden)
    summary = run_one(fixture, row, output, ParticipantSelection(selected, {}, {}), collect_only=True)
    assert summary['state'] == 'finished'
    assert summary['harness_error'] == 'runner_interrupted'
    assert fixture.closed == ['fixture-session']
    assert not fixture.submitted  # Keep the already accepted candidate, not mutable output.


@pytest.mark.parametrize('wrong_identity', [False, True])
def test_collect_only_cli_preserves_old_identity_and_never_resolves_harness(tmp_path, monkeypatch, wrong_identity):
    import sys

    from benchmarking.participants.harnesses.scheme import resolve_scheme
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
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_participant(fixture, dict(row, task='fixture'), output, ParticipantSelection(selected, {}, {}))
    identity = {'benchmark': {'version': 'old-release', 'commit': 'old-commit'},
                'endpoint': fixture.endpoint, 'plan': [row]}
    (case / 'result.json').write_text(json.dumps({'identity': identity, 'state': 'running'}))
    def forbidden(*args, **kwargs):
        pytest.fail('Collection must not resolve or launch a harness')
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', forbidden)
    monkeypatch.setattr('benchmarking.participants.batch.plan.harness_version', forbidden)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', forbidden)
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

    from benchmarking.execution.leases import BatchLeaseError
    from benchmarking.participants.attempt.storage import CaseLease

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

    from benchmarking.participants.attempt.runner import run_one, save
    from benchmarking.participants.harnesses.scheme import resolve_scheme
    from benchmarking.run import main

    fixture = ServiceFixture()
    row = {'name': 'trial', 'harness': 'command', 'model': 'fixture', 'effort': 'off',
           'tasks': ['fixture'], 'repetitions': 1,
           'scheme': resolve_scheme({'version': 'fixture', 'launch': {
               'command': [sys.executable, '-c', 'pass'], 'files': []}}, tmp_path, 'command')}
    case = tmp_path / 'batch/fixture'
    runtime = case / '.runtime'
    runtime.mkdir(parents=True)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    selection = ParticipantSelection({'harness': 'command', 'model': 'fixture', 'effort_resolved': 'off'}, {}, {})
    summary = run_one(fixture, dict(row, task='fixture'), runtime / 'participant', selection)
    summary.update(result='participant/analysis/result.json', task='fixture', directory='fixture', repetition=1)
    identity = {'benchmark': {'version': 'old', 'commit': 'old'}, 'endpoint': None, 'plan': [row]}
    save(runtime / 'summary.json', summary)
    save(case / 'result.json', {'identity': identity, 'state': 'finalizing', 'summary': summary})
    def forbidden(*args, **kwargs):
        pytest.fail('A committed terminal export needs neither service nor model')
    monkeypatch.setattr('benchmarking.participants.attempt.service.local_service_client', forbidden)
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', forbidden)
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
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
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


@pytest.mark.parametrize('recoverable', [False, True])
def test_local_case_list_routes_dataset_inputs_and_rejects_missing_cases(tmp_path, monkeypatch, recoverable):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["a", "b"]\nconcurrency=2\nrepetitions=1\n')
    if not recoverable:
        with config.open('a') as stream:
            stream.write('[recovery]\nhttp_attempts=1\nbackoff_seconds=0\nmax_backoff_seconds=0\nresume_session=false\n')
    dataset = write_dataset(tmp_path / 'dataset', ['a'])
    routed = []
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    def local_service(path, output, image, *flags):
        assert flags == (recoverable,)
        return nullcontext(path)
    monkeypatch.setattr('benchmarking.participants.attempt.service.service', local_service)
    def run(access, row, output, selection):
        assert access['case'] == row['task']
        assert access['dataset'] == str(dataset)
        routed.append(row['task'])
        return terminal_files(output)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
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
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection(selected, {}, {}))
    monkeypatch.setattr('benchmarking.participants.attempt.worker.Client', lambda *args, **kwargs: fixture)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *args, **kwargs: fixture)
    monkeypatch.setattr('benchmarking.participants.attempt.runner.subprocess.check_output', lambda *args, **kwargs: 'fixture-cli')
    monkeypatch.setattr('benchmarking.participants.batch.plan.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    with patch('benchmarking.participants.harnesses.registry.prepare', return_value=[sys.executable, '-c',
               'print(' + repr(json.dumps(event)) + ')']) as launch:
        args = ['--config', str(config), '--endpoint', fixture.endpoint, '--output', str(tmp_path / 'batch')]
        assert main(args) == 1
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
        assert main(args + ['--resume']) == 1
        assert launch.call_count == 1


@pytest.mark.parametrize('mode,category', [('prose', None), ('unknown', 'unknown'), ('recovered', None)])
def test_mcp_failure_requires_structured_unrecovered_evidence(tmp_path, mode, category):
    from benchmarking.participants.harnesses.codex import harness_failure
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
    monkeypatch.setattr('benchmarking.participants.batch.plan.harness_version', lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    args = ['--config', str(config), '--endpoint', 'http://localhost:1']
    with patch('benchmarking.participants.attempt.runner.run_one', side_effect=lambda a, r, out, s: terminal_files(out)) as launch:
        assert main(args) == 0
        root = tmp_path / 'results/trial'
        args += ['--output', str(root)]
        for task in ['library.cell', 'other.cell']:
            directory = case_run(root, task)
            for repetition in range(1, repetitions + 1):
                slot = directory if repetitions == 1 else directory / f'repetition-{repetition}'
                assert json.loads((slot / 'result.json').read_text())['summary']['task'] == task
        assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'library.cell', 'other.cell'}
        from benchmarking.participants.attempt.storage import CaseLease
        count = launch.call_count
        directory = case_run(root, 'library.cell')
        with CaseLease(directory), pytest.raises(SystemExit):
            main(args)
        assert launch.call_count == count
        capsys.readouterr()
        assert main(args) == 0
        assert launch.call_count == count
        assert 'SKIP case=library.cell' in capsys.readouterr().out
        # A different benchmark version cannot silently reuse this case.
        manifest = directory / ('result.json' if repetitions == 1 else 'repetition-1/result.json')
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
        slot = directory
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


def test_updated_profile_prices_apply_to_new_runs_and_preserve_resumed_run_prices(tmp_path, monkeypatch):
    import tomli_w

    from benchmarking.run import main

    prices = tmp_path / 'pricing.toml'
    original = {'currency': 'USD', 'source': 'https://provider.example/pricing', 'as_of': '2026-10-16',
                'input_per_million': 2, 'cache_read_per_million': .2,
                'cache_write_per_million': 2.5, 'output_per_million': 10}
    prices.write_text(tomli_w.dumps({'models': {'fixture': original}}))
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["interrupted", "finished"]\nconcurrency=1\nrepetitions=2\n'
                      'pricing_file="pricing.toml"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    observed = []

    def run(access, row, output, selection):
        observed.append(copy.deepcopy(row['pricing']))
        if len(observed) == 1:
            raise RuntimeError('synthetic interruption')
        return terminal_files(output)

    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
    arguments = ['--config', str(config), '--endpoint', 'https://fixture']
    reuse = arguments + ['--output', str(tmp_path / 'retained')]
    assert main(reuse) == 1
    finished = case_run(tmp_path / 'retained', 'finished') / 'repetition-1/result.json'
    retained = finished.read_bytes()
    updated = dict(original, input_per_million=4, output_per_million=20)
    prices.write_text(tomli_w.dumps({'models': {'fixture': updated}}))
    assert main(reuse + ['--resume']) == 0
    assert observed == [original] * 5
    assert finished.read_bytes() == retained
    assert main(reuse) == 0  # Completed runs continue to use their recorded prices.
    assert observed == [original] * 5
    assert main(arguments) == 0
    assert observed[5:] == [updated] * 4
    for result in (tmp_path / 'results').rglob('result.json'):
        assert json.loads(result.read_text())['identity']['plan'][0]['pricing'] == updated
    config.write_text(config.read_text().replace('effort="medium"', 'effort="low"'))
    with pytest.raises(SystemExit):
        main(reuse + ['--resume'])
    assert len(observed) == 9


def test_new_runs_preserve_task_history_and_reuse_only_the_latest(tmp_path, monkeypatch, capsys):
    from datetime import datetime

    from benchmarking.run import main

    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["library.cell"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *a: ParticipantSelection({}, {}, {}))
    outcomes = iter(['pass', 'fail'])
    calls = []

    def run(access, row, output, selection):
        calls.append(output)
        return terminal_files(output, next(outcomes))

    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
    args = ['--config', str(config), '--endpoint', 'https://fixture']
    root = tmp_path / 'results/trial'
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    assert main(args) == 0
    first = case_run(root, 'library.cell')
    original = {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}
    archived = root / '.batches/previous'
    archived.mkdir(parents=True)
    (archived / 'result.json').write_bytes((first / 'result.json').read_bytes())
    assert main(args) == 0
    history = sorted((root / 'library.cell').iterdir())
    assert len(history) == 2 and history[0] == first
    for directory in history:
        datetime.strptime(directory.name, '%Y%m%d-%H%M%S-%f').astimezone()
    latest = history[-1]
    assert json.loads((latest / 'result.json').read_text())['evaluation']['outcome'] == 'fail'
    capsys.readouterr()
    explicit = args + ['--output', str(root)]
    assert main(explicit) == 0
    assert str(latest / 'result.json') in capsys.readouterr().out
    assert len(calls) == 2
    assert main(['--status', '--output', str(root)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert {r['directory'] for r in status['cases']} == {str(p.relative_to(root)) for p in history}
    record = json.loads((latest / 'result.json').read_text())
    record['identity']['benchmark']['commit'] = 'changed'
    (latest / 'result.json').write_text(json.dumps(record))
    with pytest.raises(SystemExit):
        main(explicit + ['--resume'])
    (latest / 'result.json').unlink()
    with pytest.raises(SystemExit):
        main(explicit + ['--resume'])
    assert len(calls) == 2
    assert original == {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}


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
    monkeypatch.setattr('benchmarking.participants.batch.plan.harness_version', lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    monkeypatch.setattr('benchmarking.participants.attempt.service.service', lambda *args: nullcontext(None))
    dataset = write_dataset(tmp_path / 'dataset', ['old', 'new-a', 'new-b'])
    barrier = threading.Barrier(2)
    calls = []
    def run(access, row, output, selection):
        calls.append(row['task'])
        if row['task'] != 'old':
            barrier.wait(timeout=5)  # Cannot pass if the two new sessions are serialized.
        return terminal_files(output, 'pass')
    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
    configure(['old'], 1)
    args = ['--config', str(config), '--dataset', str(dataset)]
    assert main(args) == 0
    root = tmp_path / 'results/trial'
    args += ['--output', str(root)]
    old = case_run(root, 'old')
    original = {str(p.relative_to(old)): p.read_bytes() for p in old.rglob('*') if p.is_file()}
    manifest = (old / 'result.json').read_bytes()
    configure(['old', 'new-a', 'new-b'], 2)
    capsys.readouterr()
    assert main(args) == 0
    printed = capsys.readouterr().out
    assert 'SKIP case=old ' in printed
    assert str(old / 'result.json') in printed
    assert sorted(calls) == ['new-a', 'new-b', 'old']
    assert original == {str(p.relative_to(old)): p.read_bytes() for p in old.rglob('*') if p.is_file()}
    assert (old / 'result.json').read_bytes() == manifest
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'old', 'new-a', 'new-b'}
    assert main(args) == 0
    assert len(calls) == 3
    import shutil
    relocated = tmp_path / 'relocated'
    copied_root = relocated / 'results' / root.name
    copied = copied_root / old.relative_to(root)
    shutil.copytree(old, copied)
    configure(['old'], 1)
    monkeypatch.chdir(relocated)
    relocated_args = args[:-2] + ['--output', str(copied_root)]
    assert main(relocated_args) == 0
    assert len(calls) == 3
    assert {p.name for p in copied.parent.iterdir()} == {old.name}
    monkeypatch.chdir(tmp_path)
    configure(['old', 'new-a', 'new-b'], 2)
    # Inputs are version-owned: changing the benchmark release rejects all dispatch.
    monkeypatch.setattr('benchmarking.participants.batch.plan.package_version', lambda: {"version": "different", "commit": None})
    with pytest.raises(SystemExit):
        main(args)
    assert len(calls) == 3


def test_startup_failure_is_durable_and_same_key_never_starts_another_worker(tmp_path, executable_case, monkeypatch):
    from benchmarking.service.server import APIError, LocalService
    from benchmarking.tasks.contract import load_task
    task = load_task(executable_case)
    attempts = []
    def broken_startup(*args, **kwargs):
        attempts.append(1)
        raise OSError('resource archive unavailable')
    monkeypatch.setattr('benchmarking.service.supervisor.run_session', broken_startup)
    monkeypatch.setattr('benchmarking.service.supervisor.AttachedSession', lambda *args, **kwargs: object())
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
    from benchmarking.service import supervisor as session_control
    from benchmarking.tasks.contract import load_task
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
    service = server_module.LocalService(tmp_path / 'service', task, {}, {}, 'unused', 'access', seconds=60,
                                        recoverable=False)
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


@pytest.mark.parametrize('scope,expected_launches', [('provider', 1), ('session', 2), ('endpoint', 1), ('runtime', 1)])
def test_default_case_storage_retains_blocked_dispatch_without_batch_summary(tmp_path, monkeypatch, scope, expected_launches):
    """A provider failure must leave the unstarted case visibly blocked in its own directory."""
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["first", "second"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ICLAYOUT_BENCH_TOKEN", "fixture-token")
    monkeypatch.setattr('benchmarking.participants.batch.plan.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *args: ParticipantSelection({}, {}, {}))
    result = {'outcome': 'error', 'failure': {
        'category': 'quota_exhausted' if scope == 'provider' else 'service_failure',
        'scope': scope, 'stop_dispatch': True}}
    with patch('benchmarking.participants.attempt.runner.run_one', side_effect=lambda a, r, out, s: terminal_files(out, 'error') | result) as launch:
        assert main(['--config', str(config), '--endpoint', 'https://fixture']) == 1
        assert launch.call_count == expected_launches
    root = tmp_path / 'results/trial'
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'first', 'second'}
    second = json.loads((case_run(root, 'second') / 'result.json').read_text())
    assert second['state'] == ('blocked' if expected_launches == 1 else 'finished')
    assert not (case_run(root, 'second') / '.runtime').exists()


@pytest.mark.parametrize('layout_override', [False, True])
def test_command_participant_receives_problem_and_keeps_one_identity_across_tasks(tmp_path, monkeypatch, layout_override):
    """Exercise the new launcher using a real subprocess and existing HTTP double.

    The problem, optional scheme instructions and scoped credential are separate inputs.
    Changing instructions must distinguish schemes; task/output paths must not.
    No provider or EDA claim is made by this Public-owned regression.
    """
    import sys

    from benchmarking.participants.batch.config import resolve
    from benchmarking.participants.harnesses.scheme import resolve_scheme

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
                      + ('server = json.load(open(os.environ["ICLAYOUT_BENCH_MCP_CONFIG"]))["mcpServers"]["layout"]\n'
                         'assert server["args"] == ' + repr([str(wrapper)]) + '\n'
                         'assert server["env"]["ICLAYOUT_BENCH_TOKEN"] == "scoped-fixture-token"\n'
                         if layout_override else '') +
                      'print("contract received")\n')
    raw = {'version': 'test-1', 'launch': {'command': [sys.executable, 'participant.py'], 'files': ['participant.py']}}
    if layout_override:
        raw['mcp'] = {'layout': {'command': [sys.executable, 'wrapper.py'], 'files': ['wrapper.py']}}
    identities = []
    for index, (task, instructions) in enumerate([('one', ''), ('two', ''), ('one', 'Use tool A')]):
        scheme = resolve_scheme(dict(raw, instructions=instructions), tmp_path, 'command')
        fixture = ServiceFixture()
        monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, fixture=fixture, **kw: fixture)
        selection = resolve('command', 'fixture-model', 'medium')
        condition, env, settings = selection.condition, selection.environment, selection.settings
        output = tmp_path / str(index)
        result, error = run_participant(fixture, {'harness': 'command', 'task': task, 'scheme': scheme}, output, ParticipantSelection(condition, env, settings))
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
    from benchmarking.participants.harnesses.registry import prepare

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


@pytest.mark.parametrize("credential", ["api_key_env", "oauth"])
def test_kimi_isolates_native_configuration_and_delivers_task_via_mcp(tmp_path, monkeypatch, credential):
    """Kimi's documented print/config contract must retain scoped tools and effort.

    Use the existing service fixture and fake only native execution: this guards
    credential/rule leakage and dispatch into Codex, not model or EDA quality.
    """
    import tomllib

    import tomli_w

    from benchmarking.participants.batch.config import resolve

    home = tmp_path / 'host'
    home.mkdir()
    original = {'default_model': 'fixture/k3',
                'providers': {'fixture': {'type': 'kimi', 'api_key_env': 'KIMI_FIXTURE_API_KEY'}},
                'models': {'fixture/k3': {'provider': 'fixture', 'model': 'k3', 'max_context_size': 8192,
                                         'support_efforts': ['low', 'high', 'max']}},
                'hooks': [{'event': 'PreToolUse', 'command': 'must-not-run'}]}
    if credential == 'oauth':
        original['providers']['fixture'] = {'type': 'kimi', 'oauth': {'storage': 'file', 'key': 'oauth/fixture'}}
        (home / 'credentials').mkdir()
        (home / 'credentials/fixture.json').write_text('{"access_token":"private-oauth-token"}')
    (home / 'config.toml').write_text(tomli_w.dumps(original))
    (home / 'mcp.json').write_text('{"mcpServers":{"unrelated":{}}}')
    monkeypatch.setenv('KIMI_CODE_HOME', str(home))
    monkeypatch.setenv('KIMI_FIXTURE_API_KEY', 'private-provider-key')
    monkeypatch.setenv('KIMI_MODEL_THINKING_EFFORT', 'low')
    selection = resolve('kimi-code', 'fixture/k3', 'high')
    # The real batch transports this private selection through both coordinator
    # and worker JSON pipes. Direct runner tests previously skipped that seam.
    selection = ParticipantSelection(**json.loads(json.dumps(selection.launch_payload())))
    selected, env, settings = selection.condition, selection.environment, selection.settings
    with pytest.raises(ValueError, match='explicitly supported'):
        resolve('kimi-code', 'fixture/k3', 'xhigh')
    fixture = ServiceFixture()
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.cli_version', lambda *a: 'kimi 1.2.3')

    def execute(argv, *, cwd, env, prompt, **kwargs):
        assert argv[0] == 'kimi'
        assert argv[argv.index('--prompt') + 1] == prompt
        assert prompt == '# Fixture problem\n'
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
            assert (isolated / 'credentials/fixture.json').read_bytes() == (home / 'credentials/fixture.json').read_bytes()
            assert (isolated / 'credentials/fixture.json').stat().st_mode & 0o777 == 0o600
            assert 'KIMI_FIXTURE_API_KEY' not in env
        servers = json.loads((isolated / 'mcp.json').read_text())['mcpServers']
        assert set(servers) == {'layout'}
        assert servers['layout']['env']['ICLAYOUT_BENCH_TOKEN'] == 'scoped-fixture-token'
        assert servers['layout']['toolTimeoutMs'] > fixture.remaining * 1000
        return 0, False

    monkeypatch.setattr('benchmarking.participants.attempt.runner.execute', execute)
    output = tmp_path / 'result'
    result, error = run_participant(fixture, {'harness': 'kimi-code', 'task': 'fixture'}, output, ParticipantSelection(selected, env, settings))
    assert error is None
    assert result['outcome'] == 'no_submission'
    assert tomllib.loads((home / 'config.toml').read_text()) == original
    assert 'private-provider-key' not in (output / 'conditions.json').read_text()


@pytest.mark.parametrize('scoped,stop_dispatch', [(False, False), (True, False), (True, True)])
def test_resume_observes_orphans_and_refills_before_the_slow_case_finishes(tmp_path, monkeypatch, scoped, stop_dispatch):
    """Inherited locks reproduce supervisor loss; no provider or EDA calls occur."""
    import subprocess
    import sys
    import threading
    import time

    from benchmarking.participants.attempt.storage import CaseLease, CaseRecord
    from benchmarking.run import main

    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["fast", "slow", "next"]\nconcurrency=2\nrepetitions=1\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    monkeypatch.setattr('benchmarking.participants.batch.plan.resolve', lambda *a: ParticipantSelection({}, {}, {}))
    next_started = threading.Event()
    launches = []

    def run(access, row, output, selection):
        launches.append(row['task'])
        if row['task'] == 'next':
            next_started.set()
        return terminal_files(output)

    monkeypatch.setattr('benchmarking.participants.attempt.runner.run_one', run)
    output = tmp_path / 'batch'
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(output)]
    assert main(args) == 0
    launches.clear()
    next_started.clear()
    next_case = case_run(output, 'next')
    pending = json.loads((next_case / 'result.json').read_text())
    pending.update(state='pending')
    pending.pop('summary')
    (next_case / 'result.json').write_text(json.dumps(pending))
    owners = []
    failures = []
    script = '''import json, os, sys, time
from pathlib import Path
from benchmarking.files import write_json
from benchmarking.execution.process import process_start
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
            root = case_run(output, task)
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
            if any(event['event'] == 'worker_adopted' and event['case'] == str(case_run(output, 'fast').relative_to(output)) for event in events):
                break
            time.sleep(.01)
        else:
            pytest.fail('Recovered scheduler did not observe the fast worker: ' + repr(failures))
        (tmp_path / 'fast.release').touch()
        if stop_dispatch:
            recovering.join(3)
            assert not recovering.is_alive() and not failures
            assert CaseRecord(next_case).read()['state'] == 'blocked'
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
    from benchmarking.participants.attempt.recovery import (
        DISABLED,
        capacity_delay,
        policy,
    )

    settings = policy(DISABLED | {'capacity_resumes': 5})
    monkeypatch.setattr('benchmarking.participants.attempt.recovery.random.uniform', lambda *args: 1.1)
    assert [capacity_delay(settings, n) for n in range(5)] == [33, 66, 132, 264, 300]


@pytest.mark.parametrize('repetitions', [1, 2])
def test_collect_only_waits_for_the_shared_case_lease(tmp_path, repetitions):
    """Collection locks the scheduler's case root, including repeated slots."""
    import subprocess
    import sys
    import time

    from benchmarking.execution.leases import BatchLeaseError
    from benchmarking.participants.attempt.storage import CaseLease
    from benchmarking.participants.attempt.worker import CollectRequest, collect_batch

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


def test_status_requires_no_provider_and_excludes_private_record_fields(tmp_path, capsys):
    import os

    from benchmarking.execution.process import process_start
    from benchmarking.files import write_json
    from benchmarking.run import main

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

    from benchmarking.execution.leases import BatchLeaseError
    from benchmarking.execution.process import process_start
    from benchmarking.files import write_json
    from benchmarking.participants.batch.coordinator import live_worker

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
    from benchmarking.execution.leases import BatchLeaseError
    from benchmarking.files import write_json
    from benchmarking.participants.attempt.storage import CaseLease
    from benchmarking.participants.batch.coordinator import live_slots

    case = tmp_path / 'unselected'
    case.mkdir()
    write_json(case / 'result.json', {'identity': {'plan': [{'tasks': ['unselected'], 'repetitions': 1}]},
        'state': 'running'})
    with CaseLease(case), pytest.raises(BatchLeaseError, match='Unverified live case owner'):
        live_slots(tmp_path)


@pytest.mark.parametrize('budgets,expected', [(None, 120), ({'solve_seconds': 120, 'command_seconds': 300, 'settlement_seconds': 60, 'evaluation_seconds': 600}, 480)])
def test_command_runner_uses_service_budget_and_retains_last_submission(tmp_path, monkeypatch, budgets, expected):
    from types import SimpleNamespace

    from benchmarking.participants import command

    calls = []
    created = {'session_id': 'session', 'session_token': 'secret',
               'remaining_seconds': 120, 'limits': {'phase_budgets': budgets} if budgets else {}}
    terminal = {'state': 'complete'}
    client = SimpleNamespace(
        session=lambda sid: {'state': 'active', 'remaining_seconds': 120,
                             'budget': {}, 'last_submission': {'candidate': 'accepted'}},
        close=lambda sid, **kw: calls.append('close'), result=lambda sid: terminal)
    access = SimpleNamespace(endpoint='http://localhost', create=lambda *a, **kw: created)
    monkeypatch.setenv('LAYOUT_BENCH_SESSION', 'unrelated-session')
    monkeypatch.setenv('ICLAYOUT_BENCH_ACCESS_TOKEN', 'unrelated-access')
    monkeypatch.setenv('PYTHONPATH', '/unrelated/source')
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
    monkeypatch.setattr(command, 'export_session_result', lambda *a, **kw: None)
    monkeypatch.setattr(command, 'export_observation', lambda *a, **kw: None)
    output = tmp_path / 'attempt'
    result = command.run_command(access, 'task', {'command': ['unused'], 'cwd': str(tmp_path),
                                                'condition': {}}, output, creation_key='test')
    assert result == terminal and calls == [expected, 'close']
    record = json.loads((output / 'finalization.json').read_bytes())
    assert record['submission'] == 'retained' and record['receipt'] == {'candidate': 'accepted'}
    assert 'secret' not in (output / 'session.json').read_text()


def test_evaluation_uses_its_own_declared_budget(monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.attempt import settlement as lifecycle

    clock = iter([0, 1, 601, 602])
    monkeypatch.setattr(lifecycle.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(lifecycle.time, 'sleep', lambda _: None)
    terminal = {'state': 'complete', 'limits': {'phase_budgets': {'solve_seconds': 10, 'evaluation_seconds': 7200}}}
    results = iter([{'state': 'evaluating', 'limits': {'phase_budgets': {'solve_seconds': 10, 'evaluation_seconds': 7200}}}, terminal])
    assert lifecycle.wait_result(SimpleNamespace(result=lambda _: next(results)), 'session') == terminal


def test_pending_evaluation_has_bounded_collection_wait(monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.attempt import settlement

    clock = iter([0, 1, 601, 602, 1201])
    monkeypatch.setattr(settlement.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(settlement.time, "sleep", lambda _: None)
    calls = []
    def result(sid):
        calls.append(sid)
        assert len(calls) < 3, "Collection kept waiting after its timeout"
        return {"state": "evaluating", "limits": {"phase_budgets": {"solve_seconds": 3600, "evaluation_seconds": 600}}}
    with pytest.raises(TimeoutError, match="Evaluation remains pending"):
        settlement.wait_result(SimpleNamespace(result=result), "session")


def test_command_deadline_closes_stuck_execution_and_retains_receipt(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from benchmarking.participants.attempt import settlement

    receipt = {"submission_id": "10", "candidate_sha256": "a"*64}
    clock = iter([0, 0, 0, 601, 602, 603, 604, 605, 606, 607, 608])
    monkeypatch.setattr(settlement.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(settlement.time, "sleep", lambda _: None)
    closed = []
    polls = []
    def poll(*args, **kwargs):
        polls.append(args)
        assert len(polls) < 3, "Stuck execution was drained without a bound"
        return {"log_base64": "", "state": "running", "exit_code": None,
                "truncated": False, "next_offset": 0}
    client = SimpleNamespace(session=lambda _: {"state": "active", "remaining_seconds": 0,
        "budget": {"command_remaining_seconds": 60}, "active_execution_id": "in-flight", "last_submission": receipt},
        poll=poll, close=lambda sid, **kw: closed.append(sid))
    with pytest.raises(TimeoutError, match="settlement"):
        settlement.settle_session(client, "session", tmp_path)
    record = json.loads((tmp_path/"finalization.json").read_text())
    assert closed == ["session"] and record["closed"]
    assert record["receipt"] == receipt and record["error"]["error"] == "TimeoutError"


def test_settlement_respects_independent_command_allowance(tmp_path, monkeypatch):
    from benchmarking.participants.attempt import settlement

    fixture = InFlightService()
    original_session = fixture.session
    fixture.session = lambda sid: dict(original_session(sid), budget={"command_remaining_seconds": 1200})
    (tmp_path/"session.json").write_text(json.dumps({"limits": {"phase_budgets": {"solve_seconds": 10, "command_seconds": 1200}}}))
    clock = {"now": 0}
    monkeypatch.setattr(settlement.time, "monotonic", lambda: clock["now"])
    original_poll = fixture.poll
    def poll(*args, **kwargs):
        clock["now"] = 700
        return original_poll(*args, **kwargs)
    fixture.poll = poll
    settlement.settle_session(fixture, "fixture-session", tmp_path)
    record = json.loads((tmp_path/"finalization.json").read_text())
    assert record["closed"] and record["error"] is None


def test_resume_after_solve_expiry_drains_existing_command_without_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.cli_version', lambda *a: 'fixture')
    fixture = InFlightService()
    create = fixture.create
    def created(*args, **kwargs):
        value = create(*args, **kwargs)
        fixture.remaining = 0
        return value
    fixture.create = created
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    def launch(*args, **kwargs):
        raise AssertionError('No model may launch after solve expiry')
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare', launch)
    selected = ParticipantSelection({'model': 'fixture', 'effort_resolved': 'low'}, {}, {})
    result, error = run_participant(fixture, {'harness': 'command', 'task': 'fixture'}, tmp_path, selected)
    assert error == 'harness_timeout' and result['state'] == 'complete'
    evidence = json.loads((tmp_path/'finalization.json').read_text())
    assert evidence['executions']['in-flight']['state'] == 'complete'
    assert evidence['closed'] and not fixture.submitted
