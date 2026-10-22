"""Read-only progress separates scoring, attachments and partial native usage."""

import json

import pytest

pytestmark = pytest.mark.unit


def test_scored_run_with_incomplete_attachments_does_not_become_failed_score(tmp_path):
    from benchmarking.participants.attempt.progress import inspect_run

    raw = json.dumps({'state': 'finished', 'evaluation': {'state': 'complete', 'outcome': 'pass',
        'score': {'value': 75}, 'submission': {'candidate_sha256': 'frozen'}}, 'files': []}).encode()
    (tmp_path / 'result.json').write_bytes(raw)
    result = inspect_run(tmp_path)
    assert result['evaluation_status'] == 'complete' and result['score'] == {'value': 75}
    assert result['evidence_status'] == 'missing' and result['preview_status'] == 'missing'
    assert (tmp_path / 'result.json').read_bytes() == raw


def test_orphaned_running_run_exports_partial_native_usage_without_a_verdict(tmp_path):
    from benchmarking.participants.attempt.progress import inspect_run

    path = tmp_path / 'result.json'
    raw = b'{"state":"running","identity":{}}'
    path.write_bytes(raw)
    participant = tmp_path / '.runtime/participant'
    native = participant / '.private/native-home/sessions'
    native.mkdir(parents=True)
    (participant / 'conditions.json').write_text(json.dumps({'selection': {'harness': 'codex', 'model': 'fixture'}}))
    (native / 'run.jsonl').write_text(json.dumps({'type': 'token_usage_record', 'payload': {
        'response_id': 'r1', 'usage': {'input_tokens': 100, 'output_tokens': 20}}}) + '\n')
    result = inspect_run(tmp_path, include_usage=True)
    assert result['runner_status'] == 'orphaned' and result['recorded_state'] == 'running'
    assert result['score'] is None and result['evaluation_status'] == 'pending'
    assert result['usage_scope'] == 'partial'
    assert result['model_usage']['tokens']['output_tokens'] == 20
    assert result['model_usage']['api_seconds'] is None
    assert path.read_bytes() == raw
