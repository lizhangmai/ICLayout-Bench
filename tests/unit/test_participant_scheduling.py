"""Batch dispatch: concurrency, blocking, cooldowns, resumed owners and case leases."""

import json
import os
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from functools import partial
from pathlib import Path

import pytest
from helpers.participant import (
    FakeClock,
    attempt_boundaries,
    case_run,
    host_probes,
    in_process,
    terminal_files,
    write_dataset,
)

from benchmarking.execution.leases import BatchLease, BatchLeaseError, CaseLease
from benchmarking.execution.process import process_start
from benchmarking.files import write_json
from benchmarking.participants.attempt.storage import CaseRecord
from benchmarking.participants.attempt.worker import finish_case
from benchmarking.participants.batch.coordinator import live_slots, live_worker
from benchmarking.participants.batch.runner import (
    CapacityCooldown,
    dispatch_block,
    dispatch_blocked,
    dispatch_blocks,
)
from benchmarking.participants.cli import main
from benchmarking.participants.harnesses import registry as adapters
from benchmarking.participants.harnesses.contracts import ParticipantSelection

pytestmark = pytest.mark.unit


def recording(summary=None):
    """A participant attempt that writes an independent terminal result and returns ``summary``."""
    launches = []

    def solve(access, row, output, selection):
        launches.append(output)
        return terminal_files(output, (summary or {}).get('outcome', 'no_submission')) | (summary or {})

    return solve, launches


@pytest.mark.parametrize('concurrency', [1, 2])
def test_case_list_bounds_independent_sessions_and_prints_completed_results(tmp_path, monkeypatch, capsys, concurrency):
    """Public scheduling contract; harness I/O is simulated, with a barrier proving overlap."""
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
    run_cli = partial(main, probes=host_probes(), boundaries=in_process(run))
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(tmp_path / 'batch')]
    assert run_cli(args) == 0
    assert peak == concurrency
    assert sorted(task for task, _ in calls) == sorted(tasks * 2)
    assert len({output for _, output in calls}) == len(calls)
    capsys.readouterr()
    assert run_cli(args + ['--resume']) == 0
    printed = capsys.readouterr().out
    assert len(calls) == len(tasks) * 2
    for task, output in calls:
        assert f'SKIP case={task} ' in printed
        assert str(output.parent.parent / 'result.json') in printed
    # A missing archived result must fail closed, not silently skip or rerun it.
    (calls[0][1].parent.parent / 'result.json').unlink()
    with pytest.raises(SystemExit):
        run_cli(args + ['--resume'])
    assert len(calls) == len(tasks) * 2


@pytest.mark.parametrize('recoverable', [False, True])
def test_local_case_list_routes_dataset_inputs_and_rejects_missing_cases(tmp_path, monkeypatch, recoverable):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["a", "b"]\nconcurrency=2\nrepetitions=1\n')
    if not recoverable:
        with config.open('a') as stream:
            stream.write('[recovery]\nhttp_attempts=1\nbackoff_seconds=0\nmax_backoff_seconds=0\nresume_session=false\n')
    dataset = write_dataset(tmp_path / 'dataset', ['a'])
    routed = []
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    def local_service(path, output, image, *flags):
        assert flags == (recoverable,)
        return nullcontext(path)
    def run(access, row, output, selection):
        assert access['case'] == row['task']
        assert access['dataset'] == str(dataset)
        routed.append(row['task'])
        return terminal_files(output)
    run_cli = partial(main, probes=host_probes(),
                      boundaries=in_process(run, attempt=attempt_boundaries(local_service=local_service)))
    args = ['--config', str(config), '--output', str(tmp_path / 'batch'), '--dataset', str(dataset)]
    with pytest.raises(SystemExit):
        run_cli(args)
    assert not routed
    assert not (tmp_path / 'batch').exists()
    write_dataset(dataset, ['a', 'b'])
    assert run_cli(args) == 0
    assert sorted(routed) == ['a', 'b']


def test_concurrent_batch_resume_cannot_launch(tmp_path, monkeypatch):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    batch = tmp_path / 'batch'
    batch.mkdir()
    solve, launches = recording()
    (batch / 'test').mkdir()
    with CaseLease(batch / 'test'), pytest.raises(SystemExit):
        main(['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(batch), '--resume'],
             probes=host_probes(), boundaries=in_process(solve))
    assert not launches


@pytest.mark.parametrize('harness,provider_code', [
    ('codex', None), ('kimi-code', None), ('zcode', '1308'), ('zcode', '1310'),
])
def test_fatal_provider_errors_halt_related_dispatch_without_creating_extra_repetitions(
        tmp_path, monkeypatch, harness, provider_code):
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
    launches = []

    def solve(access, row, output, selection):
        launches.append(output)
        return {'state': 'suspended', 'harness_error': 'cli_exit_1', 'failure': problem}

    assert main(['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(tmp_path / 'batch')],
                probes=host_probes(ParticipantSelection({'harness': harness, 'model': 'fixture'}, {}, {})),
                boundaries=in_process(solve)) == 1
    assert len(launches) == 1
    records = [json.loads(p.read_text()) for p in sorted((tmp_path / 'batch').rglob('result.json'))]
    assert len(records) == 3
    assert [r['state'] for r in records] == ['suspended', 'blocked', 'blocked']


@pytest.mark.parametrize('scope,expected_launches', [('provider', 1), ('session', 2), ('endpoint', 1), ('runtime', 1)])
def test_default_case_storage_retains_blocked_dispatch_without_batch_summary(tmp_path, monkeypatch, scope, expected_launches):
    """A provider failure must leave the unstarted case visibly blocked in its own directory."""
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["first", "second"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ICLAYOUT_BENCH_TOKEN", "fixture-token")
    result = {'outcome': 'error', 'failure': {
        'category': 'quota_exhausted' if scope == 'provider' else 'service_failure',
        'scope': scope, 'stop_dispatch': True}}
    solve, launches = recording(result)
    assert main(['--config', str(config), '--endpoint', 'https://fixture'],
                probes=host_probes(harness_version=lambda _: ('1.2.3', 'codex 1.2.3')),
                boundaries=in_process(solve)) == 1
    assert len(launches) == expected_launches
    root = tmp_path / 'results/trial'
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'first', 'second'}
    second = json.loads((case_run(root, 'second') / 'result.json').read_text())
    assert second['state'] == ('blocked' if expected_launches == 1 else 'finished')
    assert not (case_run(root, 'second') / '.runtime').exists()


@pytest.mark.parametrize('third_case', [False, True])
@pytest.mark.parametrize('harness,category', [('codex', 'provider_overloaded'), ('zcode', 'rate_limit')])
def test_repeated_capacity_interruptions_cool_only_related_new_dispatch(tmp_path, monkeypatch, third_case, harness, category):
    tasks = ['a', 'b', 'c'] if third_case else ['a', 'b']
    matrix = tmp_path / 'trial.toml'
    matrix.write_text(f'[defaults]\nharness="{harness}"\neffort="high"\nconcurrency=1\nrepetitions=1\n'
                      f'tasks={json.dumps(tasks)}\n'
                      '[[runs]]\nname="first"\nmodel="first"\n'
                      '[[runs]]\nname="second"\nmodel="second"\ntasks=["a"]\n')
    clock, calls = FakeClock(), []
    def run(access, row, output, selection):
        calls.append((row['model'], row['task'], clock.now))
        result = terminal_files(output)
        if row['model'] == 'first' and row['task'] in {'a', 'b'}:
            result['capacity_recovery'] = {'interruptions': [{'failure': {'category': category}}]}
        return result
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    probes = host_probes(resolve=lambda harness, model, effort: ParticipantSelection(
        {'harness': harness, 'model': model}, {}, {}))
    assert main(['--matrix', str(matrix), '--endpoint', 'https://fixture'],
                probes=probes, boundaries=in_process(run, clock=clock)) == 0
    expected_clock = 300 if third_case else 0
    assert calls[:2] == [('first', 'a', 0), ('first', 'b', 0)]
    assert calls[-1] == ('second', 'a', expected_clock)
    if third_case:
        assert calls[2] == ('first', 'c', 300)


@pytest.mark.parametrize('scoped,stop_dispatch', [(False, False), (True, False), (True, True)])
def test_resume_observes_orphans_and_refills_before_the_slow_case_finishes(tmp_path, monkeypatch, scoped, stop_dispatch):
    """Inherited locks reproduce supervisor loss; no provider or EDA calls occur."""
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["fast", "slow", "next"]\nconcurrency=2\nrepetitions=1\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    next_started = threading.Event()
    launches = []

    def run(access, row, output, selection):
        launches.append(row['task'])
        if row['task'] == 'next':
            next_started.set()
        return terminal_files(output)

    run_cli = partial(main, probes=host_probes(), boundaries=in_process(run))
    output = tmp_path / 'batch'
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(output)]
    assert run_cli(args) == 0
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
                assert run_cli(args + ['--resume'] + (['--case', 'next'] if scoped else [])) == int(stop_dispatch)
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


def test_case_lease_remains_exclusive_after_scheduler_closes_its_descriptor(tmp_path):
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


def test_finished_case_cleanup_waits_for_live_evidence_store(tmp_path):
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


def test_status_requires_no_provider_and_excludes_private_record_fields(tmp_path, capsys):
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
    case = tmp_path / 'unselected'
    case.mkdir()
    write_json(case / 'result.json', {'identity': {'plan': [{'tasks': ['unselected'], 'repetitions': 1}]},
        'state': 'running'})
    with CaseLease(case), pytest.raises(BatchLeaseError, match='Unverified live case owner'):
        live_slots(tmp_path)


def test_matrix_keeps_failure_and_runs_next_combination(tmp_path, monkeypatch):
    matrix = tmp_path / 'matrix.toml'
    matrix.write_text('[defaults]\ntasks=["test"]\nconcurrency=1\nharness="claude-code"\nmodel="test"\neffort="high"\nrepetitions=1\n'
                      '[[runs]]\nname="first"\nmodel="first"\n[[runs]]\nname="second"\nmodel="second"\n')
    selection = ParticipantSelection({'harness': 'claude-code', 'model': 'test', 'effort_resolved': None}, {}, {})

    def run(access, row, out, selected):
        if row['name'].startswith('first'):
            raise RuntimeError('fixture failure')
        return terminal_files(out)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    code = main(['--matrix', str(matrix), '--endpoint', 'http://127.0.0.1:8765'],
                probes=host_probes(selection, harness_version=lambda _: ('1.2.3', 'fixture 1.2.3')),
                boundaries=in_process(run))
    assert code == 1
    summary = [json.loads(p.read_text())['summary']
               for p in sorted((tmp_path / 'results/matrix').glob('*/test/*/result.json'))]
    assert len(summary) == 2
    assert summary[0]['harness_error'] == 'RuntimeError'
    assert summary[1]['outcome'] == 'no_submission'


@pytest.mark.parametrize('issue,endpoint,expected', [
    ({'stop_dispatch': False, 'scope': 'provider'}, 'https://fixture', None),
    ({'stop_dispatch': True, 'scope': 'session'}, 'https://fixture', None),
    ({'stop_dispatch': True, 'scope': 'runtime'}, None, ('runtime',)),
    ({'stop_dispatch': True, 'scope': 'endpoint'}, 'https://fixture', ('endpoint', 'https://fixture')),
    ({'stop_dispatch': True, 'scope': 'endpoint'}, None, None),
    ({'stop_dispatch': True, 'category': 'service_failure'}, 'https://fixture', ('endpoint', 'https://fixture')),
    ({'stop_dispatch': True, 'category': 'quota_exhausted'}, 'https://fixture', ('provider', 'codex', 'fixture-profile')),
], ids=['not-stopping', 'session', 'runtime', 'endpoint', 'local-endpoint', 'unscoped-service', 'unscoped-provider'])
def test_stop_dispatch_failure_blocks_only_its_shared_resource(issue, endpoint, expected):
    row = {'harness': 'codex', 'harness_home': 'fixture-profile', 'resolved': {'provider': 'other'}}
    assert dispatch_block(issue, row, endpoint) == expected


def test_case_and_finalization_failures_block_matching_dispatch():
    row = {'harness': 'codex', 'resolved': {'provider': 'fixture'}}
    summary = {'failure': {'category': 'task_failure'},
               'finalization_error': {'failure': {'category': 'quota_exhausted', 'stop_dispatch': True}}}
    blocked = dispatch_blocks(summary, row, 'https://fixture')
    assert blocked == {('provider', 'codex', 'fixture')}
    assert dispatch_blocked(blocked, row, 'https://fixture')
    assert not dispatch_blocked(blocked, dict(row, harness='claude-code'), 'https://fixture')
    assert not dispatch_blocked(blocked, dict(row, resolved={'provider': 'other'}), 'https://fixture')
    assert dispatch_blocked({('runtime',)}, row, None)
    assert dispatch_blocked({('endpoint', 'https://fixture')}, row, 'https://fixture')
    assert not dispatch_blocked({('endpoint', 'https://fixture')}, row, 'https://other')


def test_two_consecutive_capacity_interruptions_pause_dispatch_and_other_cases_reset_the_count():
    cooldown = CapacityCooldown(300)
    interrupted = {'capacity_recovery': {'interruptions': [{'failure': {'category': 'rate_limit'}}]}}
    overloaded = {'failure': {'category': 'provider_overloaded'}}
    assert cooldown.observe(interrupted, 10) is None
    assert cooldown.observe({'failure': {'category': 'task_failure'}}, 20) is None
    assert cooldown.observe(overloaded, 30) is None
    assert cooldown.observe(interrupted, 40) == 300 and cooldown.until == 340
    assert cooldown.observe(interrupted, 50) is None and cooldown.until == 340
