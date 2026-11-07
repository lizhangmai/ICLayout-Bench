"""Verify and export portable evaluation evidence without participant runtime policy."""

import copy
import json
from dataclasses import dataclass, field
from urllib.parse import quote

from benchmarking.evidence.archive import FeedbackEvidence, FinalRunEvidence
from benchmarking.files import atomic_write, checked, read_file

__all__ = [
    "AttemptEvidence", "AttemptRunEvidence", "ParticipantEvidence", "TraceEvidence",
    "checked", "compact_report", "compact_result", "evaluation_export", "export_attempts",
    "export_run", "load", "put", "traces", "verify", "without_hashes",
]


def load(path):
    return json.loads(read_file(path.parent, path.name))


def put(root, name, raw, files):
    destination = root / name
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        existing = read_file(root, name)
    except FileNotFoundError:
        existing = None
    if existing is not None and existing != raw:
        raise ValueError('Refusing to replace different result artifact: ' + name)
    if existing is None:
        atomic_write(destination, raw)
    if name not in files:
        files.append(name)


def without_hashes(value):
    """Drop redundant structured digests; preserve raw diagnostic text verbatim."""
    if isinstance(value, dict):
        return {k: without_hashes(v) for k, v in value.items()
                if k != 'sha256' and not k.endswith('_sha256') and k != 'public_revision'}
    if isinstance(value, list):
        return [without_hashes(v) for v in value]
    return value


def compact_result(result):
    evaluation_identity = result.get('evaluation') or {}
    original_identity = result["identity"]
    history = {k: result[k] for k in ('attempts', 'prior_plans') if k in result}
    result = without_hashes(result)
    result["identity"] = dict(original_identity)
    result.update(history)
    # Preserve measurement identities even when reusable file inventories are compacted.
    evaluation = result.get('evaluation')
    if evaluation is not None:
        for key in ('task_sha256', 'condition', 'submission'):
            if key in evaluation_identity:
                evaluation[key] = evaluation_identity[key]
    result['format'] = 'participant-result'
    result['files'] = list(result.get('files', []))
    result.pop('resources', None)
    if 'tool_identity' in evaluation_identity:
        result['evaluation']['tool_identity'] = evaluation_identity['tool_identity']
    result.get('image', {}).pop('image_id', None)
    return result


def compact_report(report):
    report = without_hashes(report)
    for job in report['jobs'].values():
        for group in ('outputs', 'evidence'):
            job[group] = {k: v for k, v in job[group].items()
                          if 'content' in v or 'path' in v or 'retention' in v}
    return report


def verify(root, result):
    for name in result.get('files', []):
        if name != 'layout.png':  # A derived image may be regenerated.
            read_file(root, name)


def evaluation_export(evidence, root, files, prefix='evaluation', *, process=False):
    from benchmarking.evaluation.plans import parse_evaluation
    from benchmarking.evaluation.scoring import recompute_score
    from benchmarking.results.retention import EvidenceUnavailable, process_omissions

    report = evidence.report
    omissions = process_omissions(report) if process else {}
    plan_raw = evidence.plan.content
    plan = parse_evaluation(plan_raw, file_format=evidence.plan.format)
    if recompute_score(plan, report) != report.get('score'):
        raise ValueError('Evaluation measurements do not reproduce the stored score')
    put(root, prefix + '/plan.json', plan_raw, files)
    report['plan']['path'] = 'plan.json'
    # Freeze exactly the evaluated inputs. These are declared task materials,
    # not author workspaces or complete PDK installations.
    for ref in report['inputs'].values():
        original = dict(ref)
        if ref.get('path'):
            name = 'inputs/' + ref['sha256']
            put(root, prefix + '/' + name, evidence.artifact(original), files)
            ref['path'] = name
    retained = {}
    for job_id, job in report['jobs'].items():
        for group in ('outputs', 'evidence'):
            for name, ref in job[group].items():
                path = ref.pop('path', None)
                if path is None:
                    continue
                original = dict(ref, path=path)
                if path in omissions:
                    ref['retention'] = 'successful_process_check'
                    continue
                try:
                    raw = evidence.artifact(original)
                except EvidenceUnavailable:
                    if not process:
                        raise
                    ref['retention'] = 'successful_process_check'
                    continue
                sha = ref['sha256']
                if sha not in retained:
                    filename = quote(job_id + '-' + name, safe='-_.')
                    put(root, prefix + '/' + filename, raw, files)
                    retained[sha] = filename
                ref['path'] = retained[sha]
    put(root, prefix + '/report.json', (json.dumps(compact_report(report), indent=2) + '\n').encode(), files)


@dataclass(frozen=True)
class TraceEvidence:
    agent: bytes = field(repr=False)
    stderr: str = field(repr=False)
    native: dict[str, bytes] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ParticipantEvidence:
    evaluation: dict
    final: FinalRunEvidence | None
    traces: TraceEvidence
    execution: dict | None
    events: tuple[dict, ...]
    model_usage: dict | None = None
    checks: tuple[FeedbackEvidence, ...] = ()


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
    for name, raw in evidence.native.items():
        put(root, prefix + 'native/' + name, raw, files)
    return evidence.stderr


def export_run(root, evidence: ParticipantEvidence, result):
    files = result['files']
    if evidence.evaluation.get('state') not in {'complete', 'error'}:
        raise ValueError('Service evaluation is not terminal')
    result['evaluation'] = copy.deepcopy(evidence.evaluation)
    if evidence.final is not None:
        if evidence.final.termination is not None:
            result['evaluation']['termination'] = evidence.final.termination
        if evidence.final.candidate is not None:
            put(root, 'final.gds', evidence.final.candidate, files)
            result['top_cell'] = evidence.final.top_cell
        if evidence.final.evaluation is not None:
            evaluation_export(evidence.final.evaluation, root, files)
    result['harness_stderr'] = traces(evidence.traces, root, files)
    if evidence.execution is not None:
        result['execution'] = copy.deepcopy(evidence.execution)
    if evidence.model_usage is not None:
        result['model_usage'] = copy.deepcopy(evidence.model_usage)
    if evidence.events:
        raw = ''.join(json.dumps(without_hashes(event)) + '\n' for event in evidence.events)
        put(root, 'evaluation/events.jsonl', raw.encode(), files)
    result['checks'] = export_checks(root, evidence.checks, files)


def export_checks(root, checks, files, prefix='checks/'):
    """Keep every observed candidate and reply, with purpose-based raw retention."""
    records = []
    for check in checks:
        record = copy.deepcopy(check.record)
        directory = prefix + 'check-' + str(record['sequence']) + '/'
        for key, filename in (('candidate', 'candidate.gds'), ('report', 'report.json')):
            if key in check.assets:
                name = directory + filename
                put(root, name, check.assets[key], files)
                record[key] = dict(record[key], path=name)
        if check.reply is not None:
            put(root, directory + 'participant-report.json', check.reply, files)
        if check.evaluation is not None:
            evaluation_export(check.evaluation, root, files, directory + 'evaluation', process=True)
        records.append(record)
    return records


def export_attempts(root, evidence_records, files):
    attempts = []
    for evidence in evidence_records:
        prefix = 'attempts/' + evidence.name + '/'
        entry = {'name': evidence.name, **copy.deepcopy(evidence.metadata)}
        entry['harness_stderr'] = traces(evidence.traces, root, files, prefix)
        entry['sessions'] = []
        for run in evidence.runs:
            run_prefix = prefix + 'sessions/' + run.session_id + '/'
            session = {'session_id': run.session_id}
            if run.candidate is not None:
                name = run_prefix + 'final.gds'
                put(root, name, run.candidate, files)
                session['candidate'] = name
            session['checks'] = export_checks(root, run.checks, files, run_prefix)
            entry['sessions'].append(session)
        attempts.append(entry)
    return attempts
