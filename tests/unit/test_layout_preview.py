"""Public archive previews: identity, idempotence and isolation from experiment verdicts.

The renderer is external Docker I/O. A small PNG fixture tests archive handling;
real saved candidates exercise KLayout separately, without claiming EDA validity.
"""
import json
import struct
import zlib
from types import SimpleNamespace

import pytest

from benchmarking.files import Asset
from benchmarking.layout_preview import ensure_layout_preview, export_layout

pytestmark = pytest.mark.unit


def preview_archive(tmp_path):
    archive = tmp_path / 'service/service-store/session/run'
    (archive / 'artifacts').mkdir(parents=True)
    candidate = Asset(b'archived candidate, not the mutable workspace', 'gds')
    task = Asset(json.dumps({'task_sha256': 'task-identity', 'output': {'top_cell': 'TOP'}}).encode(), 'json')
    def persist(asset):
        path = 'artifacts/' + asset.sha256
        (archive / path).write_bytes(asset.content)
        return dict(asset.identity(), path=path)
    (archive / 'run.json').write_text(json.dumps({'candidate': persist(candidate), 'task': persist(task)}))
    result = {'state': 'complete', 'session_id': 'session', 'task_sha256': 'task-identity',
              'score': {'value': 75}, 'tool_identity': {'image_id': 'frozen-image'},
              'submission': {'candidate_sha256': candidate.sha256, 'submission_id': 'last'}}
    analysis = tmp_path / 'participant/analysis'
    analysis.mkdir(parents=True)
    (analysis / 'result.json').write_text(json.dumps(result))
    return archive, candidate


def renderer_fixture(monkeypatch):
    calls = []
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b'')
    class Renderer:
        def __init__(self, image, *args):
            self.image = image
        def run(self, command, files, exports):
            calls.append((self.image, files))
            return SimpleNamespace(returncode=0, reason='', files={
                'layout.png': Asset(png, 'png'),
                'image.json': Asset(b'{"width":1,"height":1,"top_cell":"TOP"}', 'json')})
    monkeypatch.setattr('benchmarking.layout_preview.DockerTool', Renderer)
    return calls


def test_preview_uses_scored_snapshot_and_reuses_intact_image(tmp_path, monkeypatch):
    _archive, candidate = preview_archive(tmp_path)
    calls = renderer_fixture(monkeypatch)
    original = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    metadata = export_layout(tmp_path)
    assert calls[0][0] == 'frozen-image'
    assert calls[0][1]['candidate.gds'] == candidate
    assert metadata['candidate_sha256'] == candidate.sha256
    assert metadata['png_sha256'] == Asset((tmp_path / 'layout.png').read_bytes(), 'png').sha256
    assert export_layout(tmp_path) == metadata
    assert len(calls) == 1  # Completed skip cannot launch another rendering container.
    (tmp_path / 'layout.png').write_bytes(b'interrupted/corrupt image')
    assert export_layout(tmp_path) == metadata
    assert len(calls) == 2
    assert all(p.read_bytes() == raw for p, raw in original.items())


def test_preview_rejects_corrupted_or_wrong_submission_before_rendering(tmp_path, monkeypatch):
    archive, candidate = preview_archive(tmp_path)
    calls = renderer_fixture(monkeypatch)
    source = archive / 'artifacts' / candidate.sha256
    source.write_bytes(b'tampered')
    assert ensure_layout_preview(tmp_path)['status'] == 'error'
    source.write_bytes(candidate.content)
    result = tmp_path / 'participant/analysis/result.json'
    data = json.loads(result.read_text())
    data['submission']['candidate_sha256'] = 'wrong-submission'
    result.write_text(json.dumps(data))
    assert ensure_layout_preview(tmp_path)['status'] == 'error'
    assert not calls
    assert not (tmp_path / 'layout.png').exists()
    assert json.loads(result.read_text()) == data


def test_renderer_failure_does_not_change_score_and_can_retry(tmp_path, monkeypatch):
    preview_archive(tmp_path)
    result = tmp_path / 'participant/analysis/result.json'
    before = result.read_bytes()
    def unavailable(*args):
        raise RuntimeError('sensitive external diagnostics')
    monkeypatch.setattr('benchmarking.layout_preview.DockerTool', unavailable)
    assert ensure_layout_preview(tmp_path)['status'] == 'error'
    assert 'sensitive' not in (tmp_path / 'layout-preview-error.json').read_text()
    assert result.read_bytes() == before
    renderer_fixture(monkeypatch)
    assert ensure_layout_preview(tmp_path)['status'] == 'complete'
    assert result.read_bytes() == before


def test_remote_or_unsubmitted_result_does_not_render(tmp_path, monkeypatch):
    archive, _ = preview_archive(tmp_path)
    calls = renderer_fixture(monkeypatch)
    archive.rename(archive.with_name('unavailable'))
    assert export_layout(tmp_path)['reason'] == 'local_candidate_archive_unavailable'
    result = tmp_path / 'participant/analysis/result.json'
    data = json.loads(result.read_text())
    data['submission'] = None
    result.write_text(json.dumps(data))
    assert export_layout(tmp_path)['reason'] == 'no_final_submission'
    assert not calls


def test_runner_automatically_renders_and_backfills_on_skip(tmp_path, monkeypatch):
    from benchmarking.run import main
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\n'
                      'tasks=["case"]\nconcurrency=1\nrepetitions=1\n')
    native_calls = []
    def run(access, row, output, selection):
        native_calls.append(output)
        preview_archive(output.parent)
        return {'outcome': 'pass', 'score': 75, 'result': 'analysis/result.json'}
    monkeypatch.setattr('benchmarking.run.resolve', lambda *args: ({}, {}, {}))
    monkeypatch.setattr('benchmarking.run.run_one', run)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    calls = renderer_fixture(monkeypatch)
    args = ['--config', str(config), '--endpoint', 'https://fixture']
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('benchmarking.run.harness_version', lambda _: ('1.2.3', 'codex 1.2.3'))
    assert main(args) == 0
    case = native_calls[0].parent.parent
    assert (case / 'layout.png').exists()
    summary_path = case / 'result.json'
    summary = summary_path.read_bytes()
    (case / 'layout.png').unlink()
    assert main(args + ['--resume']) == 0
    assert (case / 'layout.png').exists()
    assert len(native_calls) == 1 and len(calls) == 2
    assert summary_path.read_bytes() == summary

    import sys

    from benchmarking.layout_preview import main as preview_main
    for target in (case, case.parent):
        (case / 'layout.png').unlink()
        monkeypatch.setattr(sys, 'argv', ['layout_preview', str(target)])
        with pytest.raises(SystemExit) as stop:
            preview_main()
        assert stop.value.code == 0
        assert (case / 'layout.png').exists()
        assert {p.name for p in case.parent.iterdir()} == {'case'}


def legacy_case(root):
    archive, candidate = preview_archive(root)
    (root / 'case.json').write_text(json.dumps({'identity': {'plan': [
        {'tasks': ['case'], 'model': 'fixture', 'effort': 'high', 'repetitions': 1}]}}))
    (root / 'summary.json').write_text(json.dumps({'state': 'finished', 'task': 'case', 'score': 75,
                                                'outcome': 'pass', 'result': 'participant/analysis/result.json'}))
    private = root / 'participant/.private'
    private.mkdir()
    (private / 'recovery.json').write_text(json.dumps({'redactions': ['credential-value']}))
    (root / 'participant/harness.jsonl').write_text('{"text":"credential-value"}\n')
    (private / 'auth.json').write_text('credential-value')
    (archive / 'artifacts/disposable-pdk').write_bytes(b'reusable environment')
    return archive, candidate


def test_compact_migration_preserves_results_and_redacted_trace_without_environment(tmp_path, monkeypatch):
    from benchmarking.participants.results import migrate_case
    _archive, candidate = legacy_case(tmp_path)
    original = json.loads((tmp_path / 'participant/analysis/result.json').read_text())
    renderer_fixture(monkeypatch)
    migrate_case(tmp_path)
    result = json.loads((tmp_path / 'result.json').read_text())
    assert result['evaluation']['score'] == original['score']
    assert result['evaluation']['submission']['submission_id'] == original['submission']['submission_id']
    assert result['evaluation']['submission']['candidate_sha256'] == original['submission']['candidate_sha256']
    assert 'files' in result and isinstance(result['files'], list)
    assert 'resources' not in result
    assert (tmp_path / 'final.gds').read_bytes() == candidate.content
    assert (tmp_path / 'agent.jsonl').read_text() == '{"text":"<REDACTED>"}\n'
    assert not (tmp_path / '.runtime').exists()
    assert not (tmp_path / 'service').exists()
    assert not (tmp_path / 'case.json').exists()
    assert not (tmp_path / 'layout-preview.json').exists()
    assert not any('credential-value' in p.read_text(errors='ignore') for p in tmp_path.rglob('*') if p.is_file())
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    migrate_case(tmp_path)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_compact_export_retains_runtime_until_commit_and_retries_without_duplicate_trace(tmp_path, monkeypatch):
    from benchmarking.participants import results
    legacy_case(tmp_path)
    renderer_fixture(monkeypatch)
    save = results.save
    def disk_full(path, value):
        if path.name == 'result.json' and value.get('state') == 'finished':
            raise OSError('injected full disk before result commit')
        save(path, value)
    monkeypatch.setattr(results, 'save', disk_full)
    with pytest.raises(OSError):
        results.migrate_case(tmp_path)
    assert (tmp_path / '.runtime/participant/harness.jsonl').exists()
    assert json.loads((tmp_path / 'result.json').read_text())['state'] == 'finalizing'
    monkeypatch.setattr(results, 'save', save)
    results.migrate_case(tmp_path)
    assert len((tmp_path / 'agent.jsonl').read_text().splitlines()) == 1
    assert not (tmp_path / '.runtime').exists()


def test_compact_migration_rejects_active_or_corrupt_evidence(tmp_path, monkeypatch):
    from benchmarking.participants.results import migrate_case
    archive, candidate = legacy_case(tmp_path)
    renderer_fixture(monkeypatch)
    summary = tmp_path / 'summary.json'
    original = summary.read_bytes()
    summary.write_text('{"state":"running"}')
    with pytest.raises(ValueError, match='finished'):
        migrate_case(tmp_path)
    assert not (tmp_path / '.runtime').exists()
    summary.write_bytes(original)
    (archive / 'artifacts' / candidate.sha256).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='identity mismatch'):
        migrate_case(tmp_path)
    assert (tmp_path / '.runtime/service').exists()
    assert not (tmp_path / 'final.gds').exists()


def test_simplify_completed_export_preserves_measurements_after_interrupted_commit(tmp_path, monkeypatch):
    """Old compact exports can lose their hash inventories without losing scores or logs.

    Inject a write failure at the external disk boundary: a repeated migration must
    finish even though the evaluator report was already simplified on the first pass.
    """
    from benchmarking.participants import results
    legacy_case(tmp_path)
    renderer_fixture(monkeypatch)
    results.migrate_case(tmp_path)
    result = tmp_path / 'result.json'
    before = json.loads(result.read_text())
    before['schema_version'] = 1
    before['resources'] = {'pdk': {'sha256': 'obsolete-inventory'}}
    before['identity']['inputs'] = {'case': {'input': 'retained-input-identity'}}
    evaluation = tmp_path / 'evaluation'
    evaluation.mkdir()
    raw_job = {'measurements': {'area': {'value': 12.5}}, 'status': 'passed',
               'outputs': {'log': {'content': 'original diagnostics', 'sha256': 'obsolete-inventory'}},
               'evidence': {'runner': {'sha256': 'obsolete-inventory', 'format': 'python'}}}
    report = {'jobs': {'geometry': raw_job}, 'score': before['evaluation']['score'],
              'inputs': {'netlist': {'sha256': 'obsolete-inventory'}}}
    (evaluation / 'report.json').write_text(json.dumps(report))
    before['files'] = {name: Asset((tmp_path / name).read_bytes(), 'text').sha256
                       for name in before['files'] + ['evaluation/report.json']}
    result.write_text(json.dumps(before))
    candidate = (tmp_path / 'final.gds').read_bytes()
    save = results.save
    def interrupted(path, data):
        if path == result:
            raise OSError('injected commit interruption')
        save(path, data)
    monkeypatch.setattr(results, 'save', interrupted)
    with pytest.raises(OSError):
        results.migrate_case(tmp_path)
    monkeypatch.setattr(results, 'save', save)
    results.migrate_case(tmp_path)
    after = json.loads(result.read_text())
    assert after['evaluation']['score'] == before['evaluation']['score']
    assert (tmp_path / 'final.gds').read_bytes() == candidate
    assert 'resources' not in after
    assert after['identity']['inputs'] == before['identity']['inputs']
    assert 'obsolete-inventory' not in result.read_text()
    retained = json.loads((evaluation / 'report.json').read_text())
    assert retained['jobs']['geometry']['measurements'] == raw_job['measurements']
    assert retained['jobs']['geometry']['outputs']['log']['content'] == 'original diagnostics'
    assert not retained['jobs']['geometry']['evidence']
