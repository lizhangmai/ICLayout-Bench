"""Attach retained service evidence to terminal participant exports."""

import json
import tempfile
from pathlib import Path

from benchmarking.eda.images import tool_image
from benchmarking.evidence.archive import RunArchive
from benchmarking.files import atomic_write, read_file
from benchmarking.participants.attempt.storage import CaseLease
from benchmarking.protocol import json_bytes
from benchmarking.results.package import (
    compact_result,
    evaluation_export,
    export_checks,
    put,
    verify,
)


def attach_session_evidence(path, store, *, renderer_image=None, renderer_runtime=None):
    """Verify and attach a scored candidate, evaluation and EDA preview."""
    from benchmarking.results.preview import ensure_layout_preview

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
        # Validate and assemble every attachment before publishing any of them.
        # The terminal manifest commits last; failures remain retryable from the store.
        with tempfile.TemporaryDirectory(prefix='.evidence-', dir=path.parent) as temporary:
            staging, files = Path(temporary), []
            if evidence.candidate is not None:
                put(staging, 'final.gds', evidence.candidate, files)
                state['top_cell'] = evidence.top_cell
            if evidence.evaluation is not None:
                evaluation_export(evidence.evaluation, staging, files)
            state['checks'] = export_checks(staging, archive.feedback(), files)
            for name in files:
                try:
                    existing = read_file(path.parent, name)
                except FileNotFoundError:
                    existing = None
                if existing is not None and existing != (staging / name).read_bytes():
                    raise ValueError('Refusing to replace different result artifact: ' + name)
            for name in files:
                put(path.parent, name, (staging / name).read_bytes(), state['files'])
            atomic_write(path, json_bytes(compact_result(state)))
        image = tool_image(renderer_image) if renderer_runtime is None else renderer_image
        preview = ensure_layout_preview(path.parent, image=image, runtime=renderer_runtime)
        verify(path.parent, json.loads(path.read_bytes()))
        return {'candidate_sha256': (result.get('submission') or {}).get('candidate_sha256'),
                'score': result.get('score'), 'preview': preview}
