"""Terminal result, observation and redacted trace exports."""

import io
import json
import uuid
import zipfile

from benchmarking.evidence.archive import RunArchive
from benchmarking.files import atomic_write
from benchmarking.observe import export_observation
from benchmarking.participants.attempt.settlement import wait_result
from benchmarking.participants.attempt.state import ParticipantAttempt
from benchmarking.participants.harnesses import registry as adapters
from benchmarking.results.analysis import export_session_result
from benchmarking.results.package import (
    AttemptEvidence,
    AttemptRunEvidence,
    ParticipantEvidence,
    TraceEvidence,
    load,
)
from benchmarking.results.usage import UsageEvidence, summarize_usage


def collect_result(client, sid, output):
    result = wait_result(client, sid)
    if not (output / "analysis" / "manifest.json").exists():
        if (output / "analysis").exists():
            (output / "analysis").rename(output / ("partial-analysis-" + uuid.uuid4().hex))
        export_session_result(result, output / "analysis")
    elif json.loads((output / "analysis" / "result.json").read_text()) != result:
        raise ValueError("Terminal service result changed during recovery")
    traces = [p for p in output.iterdir() if p.is_file() and p.name != 'session.json']
    traces.extend((output / 'dsh-sessions').rglob('*.jsonl'))
    if not (output / "observation" / "manifest.json").exists():
        if (output / "observation").exists():
            (output / "observation").rename(output / ("partial-observation-" + uuid.uuid4().hex))
        private = output / ".private"
        state = ParticipantAttempt.read_state(output)
        export_traces = private / "export-traces"
        export_traces.mkdir(mode=0o700, exist_ok=True)
        redacted = []
        for source in traces:
            content = source.read_bytes()
            for secret in sorted(state.redactions, key=len, reverse=True):
                content = content.replace(secret.encode(), b"<REDACTED>")
            destination = export_traces / source.name
            atomic_write(destination, content)
            redacted.append(destination)
        native = read_traces(output).native
        if native:
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
                for name, raw in native.items():
                    bundle.writestr(name, raw)
            destination = export_traces / 'native-traces.zip'
            atomic_write(destination, archive.getvalue())
            redacted.append(destination)
        export_observation(client, sid, output / 'observation', participant_files=redacted)
    return result


def read_traces(participant):
    condition = _optional(participant / 'conditions.json') or {}
    harness = condition.get('selection', {}).get('harness')
    values = set(ParticipantAttempt.read_state(participant).redactions
                 if ParticipantAttempt.exists(participant) else [])
    if harness:
        values.update(adapters.credential_redactions(harness, participant))

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
    native = {name: redact(raw) for name, raw in adapters.native_traces(harness, participant).items()} if harness else {}
    return TraceEvidence(agent, stderr.decode('utf-8', errors='replace'), native)


def _optional(path):
    return load(path) if path.is_file() else None


def read_model_usage(participant, traces, execution):
    conditions = _optional(participant / "conditions.json") or {}
    selection = conditions.get("selection") or {}
    if not selection.get("harness"):
        return None
    error = None
    try:
        evidence = adapters.usage(selection["harness"], traces.agent, traces.native)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        evidence, error = UsageEvidence(), type(exc).__name__
    report = summarize_usage(evidence, model=selection.get("model"), pricing=conditions.get("pricing"),
                             wall_seconds=(execution or {}).get("elapsed_seconds"))
    if error:
        report["collection_error"] = error
    return report


def read_participant_evidence(runtime):
    participant = runtime / 'participant'
    path = participant / 'analysis/result.json'
    if not path.is_file():
        raise ValueError('Terminal service result is missing; runtime retained')
    evaluation = load(path)
    archive = RunArchive.for_session(runtime / 'service/service-store', evaluation['session_id'])
    events = participant / 'observation/service-events.jsonl'
    traces = read_traces(participant)
    execution = _optional(participant / 'harness-summary.json')
    return ParticipantEvidence(
        evaluation, archive.final_evidence(evaluation) if archive is not None else None,
        traces, execution,
        tuple(json.loads(line) for line in events.read_text().splitlines() if line.strip())
        if events.is_file() else (), read_model_usage(participant, traces, execution),
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
    traces = read_traces(runtime / 'participant')
    metadata['model_usage'] = read_model_usage(runtime / 'participant', traces, metadata.get('execution'))
    runs = tuple(AttemptRunEvidence(archive.root.parent.name, archive.candidate(), tuple(archive.feedback()))
                 for archive in RunArchive.recorded_sessions(runtime / 'service/service-store'))
    return AttemptEvidence(runtime.name, metadata, traces, runs)
