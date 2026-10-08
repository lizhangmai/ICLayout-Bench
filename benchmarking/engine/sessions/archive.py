"""Read frozen run evidence without starting tools or changing its archive."""

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from benchmarking.files import Asset, EvidenceError, checked, read_file


def _report(raw):
    try:
        report = json.loads(raw)
    except ValueError as error:
        raise EvidenceError('Invalid archived report') from error
    if not isinstance(report, dict):
        raise EvidenceError('Archived report must be an object')
    return report


def _read_report(root, name):
    try:
        return _report(read_file(root, name))
    except ValueError as error:
        raise EvidenceError('Invalid archived report: ' + name) from error


@dataclass(frozen=True)
class RunJournal:
    events: tuple[dict, ...]
    incomplete_tail: bool = False


def read_journal(root, *, partial=False, missing_ok=False):
    """Read ordered committed events; only an unfinished final line is optional."""
    try:
        raw = read_file(Path(root), 'events.jsonl')
    except FileNotFoundError:
        if missing_ok:
            return RunJournal(())
        raise
    except ValueError as error:
        raise EvidenceError('Invalid archived journal') from error
    lines = raw.split(b'\n')
    events = []
    for line in lines[:-1]:
        try:
            event = json.loads(line)
        except ValueError as error:
            raise EvidenceError('Invalid committed journal event') from error
        if (not isinstance(event, dict) or type(event.get('sequence')) is not int
                or event['sequence'] != len(events) + 1
                or not isinstance(event.get('kind'), str) or not event['kind']
                or not isinstance(event.get('data'), dict)):
            raise EvidenceError('Invalid event journal sequence or schema')
        events.append(event)
    incomplete_tail = bool(lines[-1])
    if incomplete_tail and not partial:
        raise EvidenceError('Cannot read an event journal with an incomplete tail')
    return RunJournal(tuple(events), incomplete_tail)


class EvaluationArchive:
    """Read a frozen evaluation through its report, plan and declared artifacts."""

    def __init__(self, root):
        self._root = Path(root)
        self._report = _read_report(self._root, 'report.json')
        reference = self._report['plan']
        self.plan = Asset(checked(self._root, reference), reference['format'])

    @property
    def report(self):
        return copy.deepcopy(self._report)

    def artifact(self, reference):
        return checked(self._root, reference)


@dataclass(frozen=True)
class FinalRunEvidence:
    candidate: bytes | None
    top_cell: str | None
    evaluation: EvaluationArchive | None


@dataclass(frozen=True)
class FeedbackEvidence:
    record: dict
    assets: dict[str, bytes]
    evaluation: EvaluationArchive | None


class RunArchive:
    """Own interpretation of run.json and its content-addressed references."""

    def __init__(self, root):
        self.root = Path(root)

    @property
    def report(self):
        return _read_report(self.root, 'run.json')

    def journal(self, *, partial=False, missing_ok=False):
        return read_journal(self.root, partial=partial, missing_ok=missing_ok)

    def completed_report(self):
        try:
            report = self.report
        except FileNotFoundError:
            return None
        return report if report.get('phase') == 'finished' else None

    def evaluation_report(self):
        report = self.report
        if not report.get('evaluation'):
            return None
        return _report(checked(self.root, report['evaluation']))

    def participant_report(self, report_id):
        if not re.fullmatch(r'check-[1-9][0-9]*', report_id):
            raise ValueError('Invalid report ID')
        try:
            return read_file(self.root, f'feedback/{report_id}/participant-report.json').decode('utf-8')
        except ValueError as error:
            raise EvidenceError('Invalid archived participant report') from error

    @classmethod
    def for_session(cls, store, sid):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
            raise ValueError('Invalid session ID')
        root = Path(store) / sid / 'run'
        return cls(root) if root.exists() else None

    @classmethod
    def recorded_sessions(cls, store):
        for report in Path(store).glob('*/run/run.json'):
            yield cls(report.parent)

    def candidate(self):
        ref = self.report.get('candidate')
        return checked(self.root, ref) if ref else None

    def final_evidence(self, result):
        candidate, top_cell, evaluation = None, None, None
        if result.get('submission'):
            candidate = checked(self.root, self.report['candidate'])
            if hashlib.sha256(candidate).hexdigest() != result['submission']['candidate_sha256']:
                raise EvidenceError('Final candidate differs from scored submission')
            task = _report(checked(self.root, self.report['task']))
            if task['task_sha256'] != result['task_sha256']:
                raise EvidenceError('Frozen task differs from evaluated task')
            top_cell = task['output']['top_cell']
        if self.report.get('evaluation'):
            checked(self.root, self.report['evaluation'])
            evaluation = EvaluationArchive(self.root / 'evaluation')
            judged = evaluation.report
            if judged.get('score') != result.get('score'):
                raise EvidenceError('Service score differs from independent evaluator report')
        return FinalRunEvidence(candidate, top_cell, evaluation)

    def feedback(self):
        for check in self.report.get('process_feedback', {}).get('checks', []):
            assets = {key: checked(self.root, check[key]) for key in ('candidate', 'report') if check.get(key)}
            source = self.root / 'feedback' / ('check-' + str(check['sequence']))
            yield FeedbackEvidence(dict(check), assets,
                                   EvaluationArchive(source) if (source / 'report.json').exists() else None)
