"""Durable HTTP metadata and restart reconciliation for the local service.

Run journals remain authoritative for accepted submissions. This module stores
the service's credentials, idempotency responses, execution summaries and
workspace checkpoint commits.
"""

import hashlib
import json
import uuid
from pathlib import Path

from benchmarking.engine.sessions.archive import RunArchive
from benchmarking.files import atomic_write, sync_directory
from benchmarking.protocol import PROTOCOL, json_bytes


class ServiceState:
    """Own the on-disk HTTP records for one service root."""

    def __init__(self, root, task, *, recoverable=True):
        self.root = Path(root)
        self.task = task
        self.abandoned_containers = []
        self.recoverable = recoverable
        self.resumptions = {}
        self.runs = self._reconcile()

    def checkpoint(self, data, workspace):
        """Commit workspace bytes and the matching HTTP state before acknowledgment."""
        if not self.recoverable:
            return
        root = self.root / data['session_id'] / '.private'
        root.mkdir(mode=0o700, exist_ok=True)
        manifest = root / 'checkpoint.json'
        previous = json.loads(manifest.read_bytes()) if manifest.exists() else None
        archive = root / (uuid.uuid4().hex + '.tar.gz')
        try:
            identity = previous.get('workspace_digest') if previous and (root / previous['archive']).is_file() else None
            result = workspace.checkpoint(archive, data['limits']['workspace_mb'] * 1024 * 1024,
                                          previous=identity)
        except Exception:
            archive.unlink(missing_ok=True)
            raise
        name = previous['archive'] if result['unchanged'] else archive.name
        digest = previous['sha256'] if result['unchanged'] else result['sha256']
        atomic_write(manifest, json_bytes({'archive': name, 'sha256': digest,
                                         'workspace_digest': result['workspace_digest'], 'state': data}))
        if previous is not None and previous['archive'] != name:
            (root / previous['archive']).unlink(missing_ok=True)
            sync_directory(root)

    def _checkpoint(self, sid):
        root = self.root / sid / '.private'
        path = root / 'checkpoint.json'
        if not path.exists():
            return None
        if path.is_symlink():
            raise ValueError('Invalid workspace checkpoint manifest link')
        frozen = json.loads(path.read_bytes())
        name = frozen['archive']
        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.tar.gz'):
            raise ValueError('Invalid workspace checkpoint path')
        archive = root / name
        if archive.is_symlink():
            raise ValueError('Invalid workspace checkpoint link')
        with archive.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != frozen['sha256']:
            raise ValueError('Workspace checkpoint integrity mismatch')
        if frozen['state']['session_id'] != sid:
            raise ValueError('Workspace checkpoint session changed')
        return frozen | {'workspace_archive': str(archive)}

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
                checkpoint = self._checkpoint(data['session_id']) if self.recoverable and not data.get('closing') else None
                if checkpoint is not None:
                    restored = checkpoint['state']
                    if restored['task_sha256'] != self.task.digest:
                        raise ValueError('Recovery task changed')
                    if any(restored.get(key) != data.get(key) for key in
                           ('session_id', 'task_sha256', 'token', 'condition', 'limits',
                            'created_at', 'deadline', 'deadline_epoch', 'tool_identity')):
                        raise ValueError('Recovery session identity or deadline changed')
                    interrupted = []
                    # A command beyond the last checkpoint has no committed
                    # workspace effects. Keep its creation receipt and error.
                    for eid, execution in data.get('executions', {}).items():
                        if eid not in restored['executions'] or restored['executions'][eid]['state'] == 'running':
                            entry = dict(execution, state='error', exit_code=None, rolled_back=True)
                            log = self.root / data['session_id'] / (eid + '.log')
                            log.touch(mode=0o600, exist_ok=True)
                            entry['log_size'] = log.stat().st_size
                            restored['executions'][eid] = entry
                            interrupted.append(eid)
                    for key, request in data['requests'].items():
                        if key.startswith('executions:'):
                            restored['requests'][key] = request
                    if 'creation_response' in data:
                        restored['creation_response'] = data['creation_response']
                    if 'observations' in data:
                        restored['observations'] = data['observations']
                    restored['recovery'] = {'workspace_restored': True, 'interrupted_executions': interrupted}
                    restored.pop('interrupted', None)
                    data.clear()
                    data.update(restored)
                    self.resumptions[data['session_id']] = checkpoint
                else:
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
