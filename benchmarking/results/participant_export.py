"""Export explicit participant evidence without inspecting its runtime directory."""

import copy
import json
from dataclasses import dataclass, field

from benchmarking.engine.sessions.archive import FeedbackEvidence, FinalRunEvidence

from .export import evaluation_export, put, without_hashes


@dataclass(frozen=True)
class TraceEvidence:
    agent: bytes = field(repr=False)
    stderr: str = field(repr=False)


@dataclass(frozen=True)
class ParticipantEvidence:
    evaluation: dict
    final: FinalRunEvidence | None
    traces: TraceEvidence
    execution: dict | None
    events: tuple[dict, ...]


@dataclass(frozen=True)
class AttemptRunEvidence:
    session_id: str
    candidate: bytes | None = field(repr=False)
    checks: tuple[FeedbackEvidence, ...]


@dataclass(frozen=True)
class AttemptEvidence:
    name: str
    metadata: dict
    traces: TraceEvidence
    runs: tuple[AttemptRunEvidence, ...]


def traces(evidence: TraceEvidence, root, files, prefix=''):
    if evidence.agent:
        put(root, prefix + 'agent.jsonl', evidence.agent, files)
    return evidence.stderr


def export_run(root, evidence: ParticipantEvidence, result):
    files = result['files']
    if evidence.evaluation.get('state') not in {'complete', 'error'}:
        raise ValueError('Service evaluation is not terminal')
    result['evaluation'] = copy.deepcopy(evidence.evaluation)
    if evidence.final is not None:
        if evidence.final.candidate is not None:
            put(root, 'final.gds', evidence.final.candidate, files)
            result['top_cell'] = evidence.final.top_cell
        if evidence.final.evaluation is not None:
            evaluation_export(evidence.final.evaluation, root, files)
    result['harness_stderr'] = traces(evidence.traces, root, files)
    if evidence.execution is not None:
        result['execution'] = copy.deepcopy(evidence.execution)
    if evidence.events:
        raw = ''.join(json.dumps(without_hashes(event)) + '\n' for event in evidence.events)
        put(root, 'evaluation/events.jsonl', raw.encode(), files)


def export_attempts(root, evidence_records, files):
    attempts = []
    for evidence in evidence_records:
        prefix = 'attempts/' + evidence.name + '/'
        entry = {'name': evidence.name, **copy.deepcopy(evidence.metadata)}
        entry['harness_stderr'] = traces(evidence.traces, root, files, prefix)
        entry['sessions'] = []
        for run in evidence.runs:
            run_prefix = prefix + 'sessions/' + run.session_id + '/'
            session = {'session_id': run.session_id, 'checks': []}
            if run.candidate is not None:
                name = run_prefix + 'final.gds'
                put(root, name, run.candidate, files)
                session['candidate'] = name
            for check in run.checks:
                retained = copy.deepcopy(check.record)
                check_prefix = run_prefix + 'check-' + str(retained['sequence']) + '/'
                for key, filename in (('candidate', 'candidate.gds'), ('report', 'report.json')):
                    if key in check.assets:
                        name = check_prefix + filename
                        put(root, name, check.assets[key], files)
                        retained[key] = dict(retained[key], path=name)
                session['checks'].append(retained)
                if check.evaluation is not None:
                    evaluation_export(check.evaluation, root, files, check_prefix + 'evaluation')
            entry['sessions'].append(session)
        attempts.append(entry)
    return attempts
