"""Durable HTTP metadata and restart reconciliation for the local service.

Run journals remain authoritative for accepted submissions. This module stores
only the service's credentials, idempotency responses and execution summaries.
"""

import json
from pathlib import Path

from benchmarking.engine.sessions.archive import RunArchive
from benchmarking.files import atomic_write
from benchmarking.protocol import PROTOCOL, json_bytes


class ServiceState:
    """Own the on-disk HTTP records for one service root."""

    def __init__(self, root, task):
        self.root = Path(root)
        self.task = task
        self.abandoned_containers = []
        self.runs = self._reconcile()

    def archive(self, sid):
        return RunArchive(self.root / sid / 'run')

    def run_events(self, sid, *, partial=False):
        """Read authoritative run events, allowing an unfinished final append."""
        return self.archive(sid).journal(partial=partial, missing_ok=partial).events

    def register(self, data):
        """Persist a creation key before provisioning can start."""
        self.runs[data['session_id']] = data
        self.save(data)

    def remember_request(self, data, route, key, body, status, response):
        """Cache the exact HTTP response; the next observation persists it."""
        data['requests'][route + ':' + key] = {
            'body': body, 'status': status, 'response': response,
        }

    def save(self, data):
        atomic_write(self.root / data['session_id'] / 'http.json', json_bytes(data))

    def accept_event(self, data, event):
        """Project one committed run-journal submission into HTTP state."""
        receipt = event['data']['receipt']
        key = receipt.get('idempotency_key')
        # Container-side helpers submit directly; HTTP requests require keys.
        submission_id = str(receipt['sequence'])
        data['submissions'][submission_id] = {
            'submission_id': submission_id,
            'sequence': receipt['sequence'],
            'candidate_sha256': receipt['sha256'],
            'size_bytes': receipt['bytes'],
            'accepted_at': event['time'],
        }
        if key:
            replay_key = 'submissions:' + key
            data['requests'].setdefault(replay_key, {
                'body': {'path': self.task.output.path},
                'status': 200,
                'response': data['submissions'][submission_id] | {'protocol': PROTOCOL},
            })

    def observe(self, data, kind, detail, timestamp):
        events = data.setdefault('observations', [])
        events.append({'sequence': len(events), 'timestamp': timestamp,
                       'kind': kind, 'data': detail})
        self.save(data)

    def write_startup(self, sid, record):
        atomic_write(self.root / sid / 'startup.json', json_bytes(record))

    def _reconcile(self):
        runs = {}
        for meta in self.root.glob('*/http.json'):
            data = json.loads(meta.read_bytes())
            runs[data['session_id']] = data
            # A finished run report is durable even if the HTTP reply was lost.
            report = self.archive(data['session_id']).completed_report()
            if report is not None:
                data['report'] = report
            finished = 'report' in data
            if not finished:
                # Never restart a model or infer that a running command succeeded.
                data['interrupted'] = True
                for execution in data.get('executions', {}).values():
                    if execution['state'] == 'running':
                        execution.update(state='error', exit_code=None)
            # The final report can precede the HTTP projection of journal receipts.
            # Replay accepted submissions even when evaluation already completed.
            for event in self.run_events(data['session_id'], partial=True):
                if event['kind'] == 'session.created' and not finished:
                    self.abandoned_containers.append(event['data']['container_id'])
                if (event['kind'] == 'submission'
                        and event['data']['receipt'].get('accepted')):
                    self.accept_event(data, event)
            self.save(data)
        return runs
