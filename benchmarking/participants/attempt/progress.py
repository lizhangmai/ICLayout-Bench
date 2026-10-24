"""Read-only single-run progress; recorded scores and evidence remain unchanged."""

import json
from pathlib import Path

from benchmarking.execution.process import process_start


def _read(path):
    return json.loads(path.read_bytes()) if path.is_file() else {}


def inspect_run(directory, *, include_usage=False):
    """Separate runner, evaluation and attachment status, including unfinished runs.

    Attachment status describes presence, not independent archive verification.
    Partial usage covers observed native requests and never implies a final score.
    """
    root = Path(directory)
    result = _read(root / 'result.json')
    if not result:
        raise ValueError('No participant run at the selected directory')
    participant = root / '.runtime/participant'
    owner = _read(root / '.runtime/worker.json')
    alive = bool(owner and owner.get('start') and process_start(owner['pid']) == owner['start'])
    state = result.get('state', 'unknown')
    evaluation = result.get('evaluation') or _read(participant / 'analysis/result.json')
    evaluation_status = evaluation.get('state', 'pending')
    files = result.get('files', [])
    expected = ['final.gds', 'evaluation/report.json', 'evaluation/plan.json'] if evaluation.get('submission') else []
    evidence = ('complete' if all(name in files and (root / name).is_file() for name in expected) else 'missing')
    if not expected:
        evidence = 'not_applicable' if evaluation_status in {'complete', 'error'} else 'pending'
    preview = result.get('image', {}).get('status') or ('missing' if expected else 'not_applicable')
    if preview == 'complete' and not (root / 'layout.png').is_file():
        preview = 'missing'
    attempt = _read(participant / '.private/recovery.json')
    lifecycle_phase = attempt.get('phase', state)
    value = {'recorded_state': state, 'phase': lifecycle_phase, 'worker_alive': alive,
             'runner_status': ('finalizing' if lifecycle_phase == 'finalizing' else 'running') if alive else 'orphaned' if state in {'running', 'finalizing'} else state,
             'evaluation_status': evaluation_status, 'outcome': evaluation.get('outcome'),
             'score': evaluation.get('score'), 'evidence_status': evidence, 'preview_status': preview,
             'attachment_verification': 'not_performed', 'usage_scope': 'unknown'}
    settlement = _read(participant / 'finalization.json')
    if settlement:
        value['phase'] = 'evaluating' if alive and settlement.get('closed') else settlement.get('phase', lifecycle_phase)
        value['settlement'] = {key: settlement.get(key) for key in ('phase', 'elapsed_seconds', 'closed', 'executions')}
    if include_usage:
        usage = result.get('model_usage')
        if usage is None and participant.is_dir():
            from benchmarking.participants.attempt.evidence import (
                read_model_usage,
                read_traces,
            )

            usage = read_model_usage(participant, read_traces(participant), _read(participant / 'harness-summary.json'))
        value['model_usage'] = usage
        if usage is not None:
            value['usage_scope'] = 'terminal' if state == 'finished' else 'partial'
    return value
