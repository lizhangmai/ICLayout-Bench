"""Attach retained service evidence to terminal participant exports."""
import json
from pathlib import Path

from benchmarking.engine.sessions.archive import RunArchive
from benchmarking.files import atomic_write
from benchmarking.participants.storage import CaseLease
from benchmarking.protocol import json_bytes
from benchmarking.results.export import compact_result, evaluation_export, put, verify


def attach_session_evidence(path, store, *, renderer_image="iclayout-eda-open:local"):
    """Verify and attach a scored candidate, evaluation and EDA preview."""
    from benchmarking.layout_preview import ensure_layout_preview

    path = Path(path)
    with CaseLease(path.parent):
        state = json.loads(path.read_bytes())
        if state.get('format') != 'participant-result' or state.get('state') != 'finished':
            raise ValueError('Cannot attach evidence to an unfinished participant result')
        result = state['evaluation']
        archive = RunArchive.for_session(store, result['session_id'])
        recorded = archive.completed_report() if archive else None
        if recorded is None or recorded.get('score') != result.get('score'):
            raise ValueError('Operator archive differs from terminal participant score')
        evidence = archive.final_evidence(result)
        if evidence.candidate is not None:
            put(path.parent, 'final.gds', evidence.candidate, state['files'])
            state['top_cell'] = evidence.top_cell
        if evidence.evaluation is not None:
            evaluation_export(evidence.evaluation, path.parent, state['files'])
        atomic_write(path, json_bytes(compact_result(state)))
        preview = ensure_layout_preview(path.parent, image=renderer_image)
        verify(path.parent, json.loads(path.read_bytes()))
        return {'candidate_sha256': (result.get('submission') or {}).get('candidate_sha256'),
                'score': result.get('score'), 'preview': preview}
