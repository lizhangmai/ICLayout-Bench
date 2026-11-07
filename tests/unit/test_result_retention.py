"""Retention preserves observations while pruning only successful check attachments."""

import hashlib
import json
import shutil

import pytest

from benchmarking.files import Asset, EvidenceError, checked, read_file
from benchmarking.results.retention import (
    EvidenceUnavailable,
    compact,
    inventory,
    verify_archive,
)

pytestmark = pytest.mark.unit


def archive(root, *, success=True, error=False):
    root.mkdir(parents=True)
    (root / 'run.json').write_text(json.dumps({'phase': 'finished', 'score': {'value': 42},
                                             'usage': {'input_tokens': 13, 'output_tokens': None}}))
    (root / 'events.jsonl').write_bytes(b'{"sequence":1,"kind":"observed","data":{}}\n')
    references = {}
    for prefix in ('feedback/check-1', 'evaluation'):
        directory = root / prefix
        (directory / 'artifacts').mkdir(parents=True)
        def put(raw, kind, directory=directory):
            asset = Asset(raw, kind)
            path = 'artifacts/' + asset.sha256
            (directory / path).write_bytes(raw)
            return dict(asset.identity(), path=path)
        wave = put(b'original native samples\n' * 10000, 'text')
        rule = put(b'fixed native rule\n' * 10000, 'text')
        candidate = put(b'candidate', 'gds')
        plan = put(b'{}', 'json')
        report = {'task_success': success, 'physical_valid': True, 'specs_pass': success,
                  'plan': plan, 'inputs': {'candidate': candidate},
                  'jobs': {'tran': {'status': 'error' if error else 'passed', 'outputs': {},
                                   'evidence': {'results/tran.tran.tran': wave, 'control.svrf': rule}}},
                  'metrics': {'value': {'status': 'passed' if success else 'failed', 'value': 1.25}},
                  'score': {'value': 42}}
        (directory / 'report.json').write_text(json.dumps(report))
        (directory / 'participant-report.json').write_bytes(b'{"feedback":"exact reply"}')
        references[prefix] = (wave, rule, candidate)
    return references


def test_compaction_preserves_final_evidence_and_feedback_and_is_portable(tmp_path):
    root = tmp_path / 'run'
    refs = archive(root)
    original = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    plan = inventory(root)
    assert plan['prunable_bytes'] == refs['feedback/check-1'][0]['bytes']
    assert (root / 'feedback/check-1' / refs['feedback/check-1'][0]['path']).exists()
    compact(root, objects=tmp_path / 'shared')
    verify_archive(root)
    for name, raw in original.items():
        if name == 'feedback/check-1/' + refs['feedback/check-1'][0]['path']:
            with pytest.raises(EvidenceUnavailable, match='successful_process_check'):
                read_file(root, name)
        else:
            assert read_file(root, name) == raw
    assert checked(root / 'evaluation', refs['evaluation'][0]) == b'original native samples\n' * 10000
    assert compact(root, objects=tmp_path / 'shared')['removed_files'] == 0
    portable = tmp_path / 'portable'
    shutil.copytree(root, portable)
    shutil.rmtree(tmp_path / 'shared')
    shutil.rmtree(root)
    verify_archive(portable)
    assert checked(portable / 'evaluation', refs['evaluation'][0]) == b'original native samples\n' * 10000


@pytest.mark.parametrize('success,error', [(False, False), (True, True), (None, False)])
def test_functional_rejection_tool_error_and_unknown_keep_original_waveforms(tmp_path, success, error):
    root = tmp_path / 'run'
    refs = archive(root, success=success, error=error)
    assert inventory(root)['prunable_bytes'] == 0
    compact(root)
    assert checked(root / 'feedback/check-1', refs['feedback/check-1'][0]).startswith(b'original native')


def test_pinned_successful_check_keeps_waveforms(tmp_path):
    root = tmp_path / 'run'
    refs = archive(root)
    compact(root, keep_checks=['check-1'])
    assert checked(root / 'feedback/check-1', refs['feedback/check-1'][0]).startswith(b'original native')


def test_unknown_metric_state_is_not_treated_as_an_ordinary_success(tmp_path):
    root = tmp_path / 'run'
    refs = archive(root)
    path = root / 'feedback/check-1/report.json'
    report = json.loads(path.read_bytes())
    report['metrics']['value']['status'] = None
    path.write_text(json.dumps(report))
    compact(root)
    assert checked(root / 'feedback/check-1', refs['feedback/check-1'][0]).startswith(b'original native')


def test_feedback_keeps_evaluation_when_its_report_is_compressed(tmp_path):
    from benchmarking.evidence.archive import RunArchive

    root = tmp_path / 'run'
    archive(root)
    path = root / 'feedback/check-1/report.json'
    report = json.loads(path.read_bytes())
    report['diagnostics'] = 'native diagnostics\n' * 1_000_000
    raw = json.dumps(report).encode()
    path.write_bytes(raw)
    state = json.loads((root / 'run.json').read_bytes())
    state['process_feedback'] = {'checks': [{'sequence': 1, 'report': {
        **Asset(raw, 'json').identity(), 'path': 'feedback/check-1/report.json'}}]}
    (root / 'run.json').write_text(json.dumps(state))
    compact(root)
    feedback = next(RunArchive(root).feedback())
    assert feedback.evaluation is not None
    assert feedback.evaluation.report == report
    assert feedback.reply == b'{"feedback":"exact reply"}'


def test_corrupt_compressed_object_is_rejected(tmp_path):
    root = tmp_path / 'run'
    refs = archive(root)
    compact(root)
    objects = list((root / '.retained/objects').rglob('*.zst'))
    assert objects
    for p in objects:
        p.chmod(0o600)
        p.write_bytes(b'corrupt')
    with pytest.raises(EvidenceError):
        checked(root / 'evaluation', refs['evaluation'][0])


def test_unfinished_and_changed_content_are_not_removed(tmp_path):
    root = tmp_path / 'run'
    refs = archive(root)
    state = root / 'run.json'
    state.write_text('{"phase":"running"}')
    with pytest.raises(ValueError, match='terminal'):
        compact(root)
    state.write_text('{"phase":"finished"}')
    wave = root / 'feedback/check-1' / refs['feedback/check-1'][0]['path']
    wave.write_bytes(b'changed')
    with pytest.raises(EvidenceError):
        compact(root)
    assert wave.read_bytes() == b'changed'
    assert not (root / '.retained/manifest.json').exists()


def test_same_content_is_one_compressed_object_across_runs(tmp_path):
    pool = tmp_path / 'shared'
    for name in ('first', 'second'):
        root = tmp_path / name
        archive(root)
        compact(root, objects=pool)
    raw = b'fixed native rule\n' * 10000
    sha = hashlib.sha256(raw).hexdigest()
    objects = list(pool.rglob(sha + '.zst'))
    assert len(objects) == 1
    assert objects[0].stat().st_nlink == 3


def test_repacking_cannot_overwrite_compressed_immutable_evidence(tmp_path):
    from benchmarking.results.package import put

    root = tmp_path / 'run'
    refs = archive(root)
    compact(root)
    name = 'evaluation/' + refs['evaluation'][0]['path']
    with pytest.raises(ValueError, match='replace different'):
        put(root, name, b'changed', [])


def test_tree_migration_preserves_unfinished_runs_and_reports_all_decisions(tmp_path):
    from benchmarking.results.retention import retain_tree

    archive(tmp_path / 'finished')
    pending = tmp_path / 'unfinished'
    archive(pending)
    (pending / 'run.json').write_text('{"phase":"running"}')
    report = tmp_path / 'receipt.json'
    summary = retain_tree(tmp_path, report=report)
    assert summary['protected_unfinished'] == 1
    assert summary['prunable_bytes'] > 0
    summary = retain_tree(tmp_path, apply=True, report=report)
    assert summary['compacted'] == 1
    assert summary['protected_error'] == 0
    assert not (pending / '.retained').exists()
    assert json.loads(report.read_bytes())['summary'] == summary


def test_active_service_owner_and_missing_required_input_prevent_cleanup(tmp_path):
    from benchmarking.execution.leases import BatchLease
    from benchmarking.results.retention import retain_tree

    store = tmp_path / 'service-store'
    root = store / 'session/run'
    refs = archive(root)
    with BatchLease(store):
        summary = retain_tree(tmp_path, apply=True)
    assert summary['protected_error'] == 1
    assert not (root / '.retained').exists()
    (root / 'evaluation' / refs['evaluation'][2]['path']).unlink()
    with pytest.raises(FileNotFoundError):
        compact(root)
    assert not (root / '.retained').exists()


def test_stopped_service_keeps_observations_and_retires_authentication(tmp_path):
    from benchmarking.results.retention import compact_service

    store = tmp_path / 'service-store'
    root = store / 'session/run'
    archive(root)
    data = {'session_id': 'session', 'token': 'scoped-secret',
            'creation_response': {'session_token': 'scoped-secret'},
            'observations': [{'sequence': 1, 'kind': 'tool.started'}],
            'executions': {'execution': {'exit_code': 1}}, 'usage': {'input_tokens': None}}
    source = root.parent / 'http.json'
    source.write_text(json.dumps(data))
    compact_service(store)
    assert not source.exists()
    retained = json.loads(read_file(root, 'service-observations.json'))
    assert retained['observations'] == data['observations']
    assert retained['executions'] == data['executions']
    assert retained['usage'] == data['usage']
    assert b'scoped-secret' not in (root / 'service-observations.json').read_bytes()


def test_nested_archive_inherits_objects_before_independent_copy(tmp_path):
    parent = tmp_path / 'parent'
    archive(parent)
    child = parent / 'reevaluations/one'
    refs = archive(child)
    compact(parent)
    compact(child)
    portable = tmp_path / 'portable'
    shutil.copytree(child, portable)
    shutil.rmtree(parent)
    verify_archive(portable)
    assert checked(portable / 'evaluation', refs['evaluation'][0]).startswith(b'original native samples')
