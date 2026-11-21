"""Explicit replacement of unfinished cases, preserving prior evidence and solve conditions."""

import copy
import json
import os
from contextlib import ExitStack
from pathlib import Path

import pytest
from helpers.participant import (
    ServiceFixture,
    attempt_boundaries,
    case_run,
    host_probes,
    in_process,
    terminal_files,
)

from benchmarking.execution.leases import BatchLease
from benchmarking.files import write_json as save
from benchmarking.participants.batch import replacement
from benchmarking.participants.batch.replacement import (
    lease_replacement,
    validate_replacement,
)
from benchmarking.participants.cli import main
from benchmarking.participants.harnesses.contracts import ParticipantSelection

pytestmark = pytest.mark.unit


def test_explicit_replacement_keeps_failed_attempt_and_pending_plan_in_same_batch(tmp_path, monkeypatch):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["interrupted", "finished", "pending"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    selection = ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {})
    batch = tmp_path / 'batch'
    calls = []
    closed = ServiceFixture()
    closed.active = False
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
    # Replacement checks reach the recorded remote session; it has already completed.
    boundaries = in_process(run, attempt=attempt_boundaries(client=lambda *a, **kw: closed))
    old_release = host_probes(selection, package_version=lambda: {'version': 'old', 'commit': 'old'})
    args = ['--config', str(config), '--endpoint', 'https://fixture', '--output', str(batch)]
    assert main(args + ['--case', 'interrupted', '--case', 'finished'], probes=old_release, boundaries=boundaries) == 1
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
    repaired = host_probes(selection, package_version=lambda: {'version': 'repaired', 'commit': 'repaired'})
    selected = args + ['--case', 'interrupted', '--case', 'pending']
    with pytest.raises(SystemExit):
        main(args + ['--case', 'interrupted', '--case', 'finished', '--replace-unfinished'],
             probes=repaired, boundaries=boundaries)
    assert json.loads((interrupted / 'result.json').read_text()) == failed
    with pytest.raises(SystemExit):
        main(selected + ['--resume'], probes=repaired, boundaries=boundaries)
    assert main(selected + ['--replace-unfinished'], probes=repaired, boundaries=boundaries) == 0
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
        main(selected + ['--replace-unfinished'], probes=repaired, boundaries=boundaries)
    assert calls == ['interrupted', 'finished', 'interrupted', 'pending']


@pytest.mark.parametrize('changed', ['model', 'effort', 'image', 'inputs', 'endpoint', 'repetitions'])
def test_replacement_rejects_changed_solve_conditions(tmp_path, changed):
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


@pytest.mark.parametrize('source,change,accepted', [
    ('/datasets/public', 'commit', True),
    ('/datasets/public', 'pdk_files', False),
    ('fixture/dataset', 'commit', False),
])
def test_replacement_compares_local_datasets_by_content(tmp_path, source, change, accepted):
    def identity(commit, pdk_files=None):
        dataset = {'source': source, 'commit': commit}
        entry = {'dataset': dataset, 'case_sha256': 'case', 'pdk_sha256': 'manifest'}
        if pdk_files is not None:
            entry['pdk_files_sha256'] = pdk_files
        return {'benchmark': {'commit': 'old'}, 'cli_version': 'old', 'endpoint': None, 'image': 'image-id',
                'inputs': {'case': entry},
                'plan': [{'model': 'fixture', 'effort': 'high', 'repetitions': 1, 'tasks': ['case'],
                          'dataset': {**dataset, 'index_sha256': 'index'}}]}

    # Earlier releases recorded an enclosing repository commit and no PDK file digests.
    recorded = identity('a' * 40) if change == 'commit' else identity('a' * 40, {'resources/smoke.py': 'old'})
    save(tmp_path / 'result.json', {'identity': recorded, 'state': 'suspended'})
    current = identity(None if source.startswith('/') else 'b' * 40, {'resources/smoke.py': 'new'})
    if accepted:
        assert validate_replacement(tmp_path, current)['identity'] == current
    else:
        with pytest.raises(ValueError, match='cannot change'):
            validate_replacement(tmp_path, current)


@pytest.mark.parametrize('fault', ['move', 'record', 'commit'])
def test_interrupted_replacement_preserves_evidence_and_completes_same_transaction(tmp_path, monkeypatch, fault):
    old = {'identity': {'plan': [{'model': 'fixture'}], 'benchmark': {'commit': 'old'}}, 'state': 'suspended'}
    save(tmp_path / 'result.json', old)
    runtime = tmp_path / '.runtime'
    runtime.mkdir()
    (runtime / 'evidence.txt').write_text('original evidence')
    current = dict(old['identity'], benchmark={'commit': 'repaired'})
    transaction = replacement.validate_replacement(tmp_path, current)
    # Interrupt the filesystem: atomic JSON publication and directory moves.
    real_replace, real_rename = os.replace, os.rename
    def interrupted_publish(source, target):
        target = Path(target)
        if (fault == 'record' and target.name == 'record.json') or (fault == 'commit' and target == tmp_path / 'result.json'):
            raise OSError('disk interrupted')
        return real_replace(source, target)
    def interrupted_move(source, target):
        real_rename(source, target)
        if fault == 'move' and Path(source) == runtime:
            raise OSError('move interrupted')
    with monkeypatch.context() as m:
        m.setattr(os, 'replace', interrupted_publish)
        m.setattr(os, 'rename', interrupted_move)
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
    store = tmp_path / '.runtime/service/service-store'
    store.mkdir(parents=True)
    with BatchLease(store), ExitStack() as stack, pytest.raises(OSError):
        lease_replacement(tmp_path, stack)


def test_replacement_rejects_active_remote_session(tmp_path):
    identity = {'endpoint': 'https://fixture', 'plan': [{'model': 'fixture'}]}
    save(tmp_path / 'result.json', {'identity': identity, 'state': 'suspended'})
    (tmp_path / '.runtime/participant/.private').mkdir(parents=True)
    save(tmp_path / '.runtime/participant/.private/recovery.json',
         {'created': {'session_id': 'old', 'session_token': 'scoped-token'}})
    fixture = ServiceFixture()
    with pytest.raises(ValueError, match='Collect the existing remote'):
        validate_replacement(tmp_path, identity, client=lambda *a, **kw: fixture)
