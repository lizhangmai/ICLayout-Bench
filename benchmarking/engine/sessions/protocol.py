"""Durable solver submissions, diagnostic snapshots and benchmark feedback."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

from benchmarking.engine.container_scripts import benchmark_feedback as opinions
from benchmarking.engine.tools.budget import tool_time_limits
from benchmarking.files import Asset
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY

from .recorder import RecordingError


class SessionProtocol:
    def __init__(self, task, config, workspace, started, deadline, *, recorder, record, feedback, on_ready):
        self.task, self.config, self.workspace = task, config, workspace
        self.started, self.deadline = started, deadline
        self.recorder, self.record, self.feedback = recorder, record, feedback
        self.on_ready = on_ready
        self.feedback_enabled = feedback is not None and PROCESS_FEEDBACK_CAPABILITY in config.harness.capabilities
        self.opinions_enabled = opinions.CAPABILITY in config.harness.capabilities
        self.feedback_worker = ThreadPoolExecutor(max_workers=1) if self.feedback_enabled else None
        self.feedback_sequence = 0
        self.submissions, self.process_feedback, self.benchmark_feedback = [], [], []
        self.submission_keys = {}
        self.candidate = None
        self.remote_closed = self.expired = False

    def snapshot_candidate(self, remaining):
        return Asset(self.workspace.read(self.task.output.path, self.task.output.max_bytes), "gds")

    def close(self):
        # Container removal must precede this drain; final judging must follow it.
        if self.feedback_worker:
            self.feedback_worker.shutdown(wait=True)

    def _feedback(self, candidate, sequence):
        with tool_time_limits(not self.config.soft_budget):
            return self.feedback(candidate, sequence)

    def check(self):
        self.feedback_sequence += 1
        sequence = self.feedback_sequence
        requested_at = time.monotonic()
        self.record('process_feedback.request', sequence=sequence, request={'action': 'process_check'})
        entry = {'sequence': sequence, 'accepted': False, 'candidate': None, 'tool_identity': None, 'elapsed_seconds': 0.0, 'outcome': 'denied', 'physical_valid': None, 'specs_pass': None, 'task_success': None, 'report': None, 'report_id': None, 'error': None}
        try:
            remaining = self.deadline - requested_at
            if remaining <= 0:
                entry['error'] = 'budget_exhausted'
                return {'accepted': False, 'sequence': sequence, 'feedback': entry}
            frozen = self.snapshot_candidate(remaining)
            entry['candidate'] = self.recorder.archive(frozen) if self.recorder else frozen.identity()
            remaining = self.deadline - time.monotonic()
            if remaining <= 0 and not self.config.soft_budget:
                raise TimeoutError('Process feedback snapshot missed the deadline')
            pending = self.feedback_worker.submit(self._feedback, frozen, sequence)
            try:
                result = pending.result(timeout=None if self.config.soft_budget else max(0, self.deadline - time.monotonic()))
            except TimeoutError:
                if time.monotonic() >= self.deadline:
                    raise TimeoutError('Process feedback exceeded the session deadline') from None
                raise
            if not isinstance(result, dict) or not isinstance(result.get('report'), dict):
                raise TypeError('Process feedback callback must return a report')
            evaluated = result['report']
            entry.update(accepted=True, outcome=evaluated.get('outcome', 'error'), physical_valid=evaluated.get('physical_valid'), specs_pass=evaluated.get('specs_pass'), task_success=evaluated.get('task_success'), tool_identity=result.get('evaluator_identity', evaluated.get('backends')), report=result.get('report_ref'), report_id=result.get('report_id'), details=result.get('details'))
            if entry['report'] is not None and (not isinstance(entry['report'], dict)):
                raise ValueError('Process feedback report reference is invalid')
        except RecordingError:
            raise
        except Exception as error:  # noqa: BLE001 -- feedback failures are durable diagnostics
            entry.update(accepted=True, outcome='error', error=f'{type(error).__name__}: {error}'[:1024])
        finally:
            if time.monotonic() >= self.deadline and not self.config.soft_budget:
                self.expired = True
            entry['elapsed_seconds'] = time.monotonic() - requested_at
            self.process_feedback.append(entry)
            self.record('process_feedback.result', **entry)
        return {'accepted': entry['accepted'], 'sequence': sequence, 'feedback': entry}

    def dispatch(self, action):
        if isinstance(action, dict) and action.get('action') == 'benchmark_feedback':
            try:
                if not self.opinions_enabled:
                    raise ValueError('Benchmark feedback capability is not declared')
                if set(action) != {'action', 'feedback'}:
                    raise ValueError('Invalid benchmark feedback request')
                if len(self.benchmark_feedback) >= opinions.MAX_REPORTS:
                    raise ValueError('Benchmark feedback limit reached')
                if time.monotonic() >= self.deadline:
                    raise ValueError('Benchmark feedback deadline passed')
                opinion = opinions.validate_feedback(action['feedback'])
                content = Asset(json.dumps(opinion, ensure_ascii=False, sort_keys=True).encode(), 'json')
                reference = self.recorder.archive(content) if self.recorder else content.identity()
                received = time.monotonic()
                if received >= self.deadline:
                    raise ValueError('Benchmark feedback missed the storage deadline')
                item = {'sequence': len(self.benchmark_feedback) + 1, 'elapsed_seconds': received - self.started, 'task_sha256': self.task.digest, 'harness': self.config.harness.identity(), 'content': reference}
                self.record('benchmark_feedback.submitted', **item)
                self.benchmark_feedback.append(item)
                receipt = {'accepted': True, 'sequence': item['sequence'], 'sha256': content.sha256}
            except RecordingError:
                raise
            except (TypeError, ValueError) as error:
                receipt = {'accepted': False, 'reason': str(error)}
                self.record('benchmark_feedback.rejected', **receipt)
        elif self.on_ready is not None and action == {'action': 'close'}:
            self.remote_closed = True
            receipt = {'accepted': True}
        elif action == {'action': 'submit'} or (self.on_ready is not None and isinstance(action, dict) and (set(action) == {'action', 'key'}) and (action['action'] == 'submit')):
            key = action.get('key')
            if key is not None:
                from benchmarking.protocol import identifier
                identifier(key)
            if key is not None and key in self.submission_keys:
                return self.submission_keys[key]
            remaining = self.deadline - time.monotonic()
            frozen = self.snapshot_candidate(remaining)
            archived = self.recorder.archive(frozen) if self.recorder else None
            accepted_at = time.monotonic()
            if accepted_at >= self.deadline and not self.config.soft_budget:
                raise ValueError('Submission snapshot missed the deadline')
            receipt = {'accepted': True, 'sequence': len(self.submissions) + 1, 'elapsed_seconds': accepted_at - self.started, **frozen.identity()}
            if self.config.soft_budget:
                receipt['after_budget'] = accepted_at >= self.deadline
            if key is not None:
                receipt['idempotency_key'] = key
            # Persist acceptance before publishing the candidate or replay receipt.
            self.record('submission', receipt=receipt, candidate=archived)
            if key is not None:
                self.submission_keys[key] = receipt
            self.candidate = frozen
            self.submissions.append(receipt)
        elif action == {'action': 'process_check'} and self.feedback_enabled:
            receipt = self.check()
        elif action == {'action': 'process_check'}:
            raise ValueError('Process feedback capability is not declared')
        else:
            raise ValueError('Expected a submit or process_check action')
        return receipt
