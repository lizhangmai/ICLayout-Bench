"""Read private participant runtime files into explicit, redacted export evidence."""

import json

from benchmarking.engine.sessions.archive import RunArchive
from benchmarking.results.export import load
from benchmarking.results.participant_export import (
    AttemptEvidence,
    AttemptRunEvidence,
    ParticipantEvidence,
    TraceEvidence,
)

from . import adapters
from .attempt import ParticipantAttempt


def read_traces(participant):
    values = (ParticipantAttempt.read_state(participant).redactions
              if ParticipantAttempt.exists(participant) else [])

    def redact(raw):
        for value in sorted(values, key=len, reverse=True):
            if value:
                raw = raw.replace(value.encode(), b'<REDACTED>')
        return raw

    paths = sorted(participant.glob('launch-*-harness.jsonl'),
                   key=lambda path: int(path.name.split('-')[1]))
    paths.append(participant / 'harness.jsonl')
    agent = b''.join(redact(path.read_bytes()).rstrip(b'\n') + b'\n'
                     for path in paths if path.is_file())
    stderr = b'\n'.join(redact(path.read_bytes()) for path in sorted(participant.glob('*harness.stderr')))
    condition = _optional(participant / 'conditions.json') or {}
    harness = condition.get('selection', {}).get('harness')
    native = {name: redact(raw) for name, raw in adapters.native_traces(harness, participant).items()} if harness else {}
    return TraceEvidence(agent, stderr.decode('utf-8', errors='replace'), native)


def _optional(path):
    return load(path) if path.is_file() else None


def read_participant_evidence(runtime):
    participant = runtime / 'participant'
    path = participant / 'analysis/result.json'
    if not path.is_file():
        raise ValueError('Terminal service result is missing; runtime retained')
    evaluation = load(path)
    archive = RunArchive.for_session(runtime / 'service/service-store', evaluation['session_id'])
    events = participant / 'observation/service-events.jsonl'
    return ParticipantEvidence(
        evaluation, archive.final_evidence(evaluation) if archive is not None else None,
        read_traces(participant), _optional(participant / 'harness-summary.json'),
        tuple(json.loads(line) for line in events.read_text().splitlines() if line.strip())
        if events.is_file() else (),
    )


def read_attempt_evidence(runtime):
    metadata = {}
    for key, path in (
        ('record', runtime / 'record.json'), ('summary', runtime / 'summary.json'),
        ('execution', runtime / 'participant/harness-summary.json'),
        ('conditions', runtime / 'participant/conditions.json'),
    ):
        value = _optional(path)
        if value is not None:
            metadata[key] = value
    metadata['startup'] = [load(path) for path in sorted(runtime.glob('service/service-store/*/startup.json'))]
    runs = tuple(AttemptRunEvidence(archive.root.parent.name, archive.candidate(), tuple(archive.feedback()))
                 for archive in RunArchive.recorded_sessions(runtime / 'service/service-store'))
    return AttemptEvidence(runtime.name, metadata, read_traces(runtime / 'participant'), runs)
