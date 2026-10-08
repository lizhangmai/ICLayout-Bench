"""Commit a case's terminal export before releasing its private runtime evidence."""

import shutil
from contextlib import ExitStack

from benchmarking.files import atomic_write
from benchmarking.files import write_json as save
from benchmarking.locking import BatchLease
from benchmarking.results.export import (
    compact_result,
    load,
    verify,
)
from benchmarking.results.outbox import archive_result
from benchmarking.results.participant_export import (
    export_attempts,
    export_run,
)
from benchmarking.results.preview import ensure_layout_preview
from benchmarking.results.report import report_text

from . import local_service
from .evidence import read_attempt_evidence, read_participant_evidence
from .storage import CaseRecord

__all__ = ["finish_case"]


def finish_case(root, *, output=None, results_data=None, schedule=None):
    """Caller owns the case lease. Commit verified outputs before removing runtime state."""
    record = CaseRecord(root)
    state = record.read()
    if record.terminal_summary() is None:
        raise ValueError('Cannot finalize an unfinished case')
    if not state['identity'].get('endpoint') and record.service.exists():
        local_service.stop_local_service(record.service)
    if state['state'] == 'finished':
        ensure_layout_preview(record.root)
    summary = _finish_case(record, state)
    # Derived previews and archive indexing can be retried without a solve.
    if output is not None:
        archive_result(results_data, output, str(record.root.relative_to(output)), schedule or state['identity']['plan'])
    return summary


def _finish_case(record, state):
    root, runtime = record.root, record.runtime
    if state.get('state') == 'finished':
        if state.get('format') != 'participant-result':
            raise ValueError('Unsupported participant result format')
        verify(root, state)
        if runtime.exists():
            with ExitStack() as stack:
                for store in sorted(runtime.rglob('service-store')):
                    stack.enter_context(BatchLease(store))
                shutil.rmtree(runtime)
        return state['summary']
    summary = record.terminal_summary()
    if summary is None:
        raise ValueError('Cannot finalize an unfinished case')
    # Do not delete stores still owned by a live service, including abandoned attempts.
    with ExitStack() as stack:
        for store in sorted(runtime.rglob('service-store')):
            stack.enter_context(BatchLease(store))
        result = {'format': 'participant-result', 'identity': state['identity'], 'state': 'finalizing',
                  'summary': dict(summary, result='result.json'), 'files': []}
        files = result['files']
        export_run(root, read_participant_evidence(runtime), result)
        result['prior_plans'] = [load(p) for p in sorted((runtime / 'plans').glob('*/record.json'))]
        attempts = [read_attempt_evidence(path) for path in sorted((runtime / "attempts").glob('*')) if path.is_dir()]
        result["attempts"] = export_attempts(root, attempts, files)
        result = _commit_terminal(root, result)
        shutil.rmtree(runtime)
    return result['summary']

def _commit_terminal(root, result):
    result = compact_result(result)
    save(root / 'result.json', result)
    ensure_layout_preview(root)
    result = load(root / 'result.json')
    if ((root / 'layout.png').exists() and result.get('image', {}).get('status') == 'complete'
            and 'layout.png' not in result['files']):
        result['files'].append('layout.png')
    text = report_text(result)
    atomic_write(root / 'report.md', text)
    result['files'].append('report.md')
    verify(root, result)
    result['state'] = 'finished'
    save(root / 'result.json', result)
    return result
