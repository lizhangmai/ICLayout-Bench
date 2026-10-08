"""Own local sessions, execution supervision and durable state transitions."""

import base64
import hashlib
import math
import secrets
import threading
import time
import uuid
from pathlib import Path

from benchmarking.engine.sessions.config import RunConfig
from benchmarking.engine.sessions.control import SessionControl
from benchmarking.engine.source import evaluation_identity
from benchmarking.files import Asset, relative
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY, HarnessSpec
from benchmarking.locking import BatchLease
from benchmarking.protocol import (
    PROTOCOL,
    SESSION_STARTUP_TIMEOUT_SECONDS,
    condition,
    json_bytes,
)

from . import views
from .contracts import APIError, fields, session_limits, utc
from .state import ServiceState


class SessionController:
    """Session operations shared by the HTTP adapter, under one runtime lock."""

    def __init__(self, root, task, resources, backends, image, token, *, seconds=None,
                 revision='unknown', solver_runtime=None, session_control=None):
        self.solver_runtime = solver_runtime
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.lease = BatchLease(self.root).__enter__()
        self.task, self.resources, self.backends = task, resources, backends
        self.image, self.token, self.revision = image, token, revision
        self.evaluator_identity = evaluation_identity(task, backends)
        self.lock = threading.RLock()
        self.limits = session_limits(task, seconds)
        self.state = ServiceState(self.root, task)
        self.session_control = session_control if session_control is not None else SessionControl()
        self.session_control.reap_abandoned(self.state.abandoned_containers)


    def create(self, token, body, key):
        """Authenticate and replay creation while holding the runtime lock."""
        with self.lock:
            if not secrets.compare_digest(token, self.token):
                raise APIError(401, 'unauthorized', 'Invalid access token')
            fields(body, ('task_id', 'condition'))
            for data in self.state.runs.values():
                if data['creation_key'] == key:
                    if data['creation_body'] != body:
                        raise APIError(409, 'conflict', 'Idempotency key conflict')
                    if 'creation_response' not in data:
                        raise APIError(500, 'infrastructure_error', 'Session creation was interrupted')
                    return 201, data['creation_response']
            status, response = self._create(body, key)
            self._observe(self.state.runs[response['session_id']], 'session.created',
                          {'task_id': body['task_id'], 'limits': response['limits']})
            return status, response

    def _session(self, sid, token):
        data = self.state.runs.get(sid)
        if data is None or not secrets.compare_digest(token, data['token']):
            raise APIError(404, 'not_found', 'Session not found')
        if time.time() > data['retained_epoch']:
            raise APIError(410, 'session_closed', 'Retention period ended')
        return data

    def read(self, sid, token, operation, *, target=None, offset=0):
        """Return a bounded projection; never expose the mutable session record."""
        with self.lock:
            data = self._session(sid, token)
            result = self._read(data, operation, target, offset)
            if operation == 'file':
                self._observe(data, 'file.read', {k: result[k] for k in ('path', 'sha256', 'size_bytes')})
            return 200, result | {'protocol': PROTOCOL}

    def mutate(self, sid, token, operation, body, key, *, target=None):
        """Replay, execute and persist a mutation as one locked operation."""
        with self.lock:
            data = self._session(sid, token)
            namespace = (operation or '') if target is None else f'{operation}/{target}'
            cached = data['requests'].get(namespace + ':' + key)
            if cached:
                if cached['body'] != body:
                    raise APIError(409, 'conflict', 'Idempotency key conflict')
                return cached['status'], cached['response']
            self._active(data, allow_expired=operation in {'close', 'cancel', 'submissions'})
            status, result = self._mutate(data, operation, body, key, target)
            result['protocol'] = PROTOCOL
            self.state.remember_request(data, namespace, key, body, status, result)
            detail = {k: v for k, v in result.items() if k != 'protocol'}
            if operation == 'executions':
                detail.update(command=body['command'], timeout_seconds=body['timeout_seconds'])
            self._observe(data, namespace, detail)
            return status, result

    def _read(self, data, operation, target, offset):
        sid = data['session_id']
        if operation == 'status':
            return self._status(data)
        if operation == 'result':
            return self._result(data)
        if operation == 'report':
            try:
                content = self.state.archive(sid).participant_report(target)
            except FileNotFoundError:
                raise APIError(404, 'not_found', 'Report not available')
            if offset < 0 or offset > len(content):
                raise ValueError('Invalid report offset')
            page = content[offset:offset + 16000]
            return {'session_id': sid, 'report_id': target, 'content': page,
                    'next_offset': offset + len(page), 'has_more': offset + len(page) < len(content)}
        if operation == 'observations':
            events = data.get('observations', [])
            if offset < 0 or offset > len(events):
                raise ValueError('Invalid observation offset')
            page, size = [], 0
            for event in events[offset:offset + 100]:
                size += len(json_bytes(event))
                if page and size > 256 * 1024:
                    break
                page.append(event)
            return {'session_id': sid, 'provenance': 'server_observed',
                    'available': 'observations' in data, 'events': page,
                    'next_offset': offset + len(page), 'has_more': offset + len(page) < len(events)}
        if operation == 'submission':
            receipt = data['submissions'].get(target)
            if receipt:
                return dict(receipt)
        if operation == 'execution':
            execution = data['executions'].get(target)
            if execution:
                if offset < 0 or offset > execution['log_size']:
                    raise ValueError('Invalid log offset')
                with (self.root / sid / (target + '.log')).open('rb') as stream:
                    stream.seek(offset)
                    content = stream.read(min(256 * 1024, execution['log_size'] - offset))
                return {k: execution[k] for k in ('execution_id', 'state', 'exit_code', 'truncated')} | {
                    'log_base64': base64.b64encode(content).decode(), 'next_offset': offset + len(content)}
        if operation == 'file':
            self._active(data, idle=True, allow_expired=True)
            return self._read_file(data, relative(target, 'file path'))
        raise APIError(404, 'not_found', 'Route not found')

    def _mutate(self, data, operation, body, key, target):
        if operation == 'close':
            fields(body, ())
            return 202, self._close(data)
        if operation == 'cancel':
            fields(body, ())
            return 200, self._cancel(data, target)
        self._active(data, idle=True, allow_expired=operation == 'submissions')
        if operation == 'files':
            fields(body, ('path', 'content_base64'))
            path = relative(body['path'], 'file path')
            raw = base64.b64decode(body['content_base64'], validate=True)
            return 200, self._write_file(data, path, raw)
        if operation == 'submissions':
            fields(body, ('path',))
            if body['path'] != self.task.output.path:
                raise ValueError('Submit the declared task output path')
            return 200, self._submit(data, key)
        if operation == 'executions':
            fields(body, ('command', 'timeout_seconds'))
            return 202, self._execute(data, body['command'], body['timeout_seconds'])
        raise APIError(404, 'not_found', 'Route not found')

    def _status(self, data):
        return views.status(data, self.session_control.workspace(data['session_id']),
                            self.state.run_events(data['session_id'], partial=True), time.time())

    def _result(self, data):
        judged = (self.state.archive(data['session_id']).evaluation_report()
                  if data.get('report', {}).get('evaluation') else None)
        return views.result(data, self._status(data), judged)

    def _observe(self, data, kind, detail):
        # Only API-visible material belongs here; internal judge journals stay private.
        self.state.observe(data, kind, detail, utc(time.time()))


    def _active(self, data, idle=False, allow_expired=False):
        status = self._status(data)
        if status['state'] != 'active':
            raise APIError(410, 'session_closed', 'Session closed')
        if time.time() >= data['deadline_epoch'] and not allow_expired:
            raise APIError(409, 'budget_exhausted', 'Solve budget exhausted; submit your final candidate without further optimization')
        if idle and status['active_execution_id']:
            raise APIError(409, 'conflict', 'Execution in progress')


    def _create(self, body, key):
        if body['task_id'] != self.task.id:
            raise APIError(404, 'not_found', 'Task not found')
        cond = condition(body['condition'])
        if len(self.state.runs) >= 100 or any(self._status(d)['state'] not in ('complete','error') for d in self.state.runs.values()):
            raise APIError(503, 'unavailable', 'Local service capacity reached')
        sid = uuid.uuid4().hex
        (self.root/sid).mkdir(mode=0o700)
        data = {'session_id': sid, 'token': secrets.token_urlsafe(32), 'creation_key': key, 'creation_body': body,
                    'task_id': self.task.id, 'task_sha256': self.task.digest, 'condition': cond, 'limits': dict(self.limits),
                    'requests': {}, 'submissions': {}, 'executions': {}}
        # Persist the creation key before any provisioning work; an uncertain
        # reply or a restart must never allocate a second session for this key.
        data.update(created_at=None, deadline=None, deadline_epoch=0,
                    retained_epoch=time.time()+7*86400, tool_identity={})
        self.state.register(data)
        started = time.monotonic()
        startup = {'state': 'starting', 'timeout_seconds': SESSION_STARTUP_TIMEOUT_SECONDS}
        self.state.write_startup(sid, startup)
        config = RunConfig(cond['harness_id'], self.image, ('/bin/sleep','infinity'), self.limits['wall_seconds'],
                           self.limits['memory_mb'], self.limits['cpus'], self.limits['pids'],
                           self.limits['workspace_mb'], {}, {}, Asset(json_bytes(cond), 'json'),
                           HarnessSpec(id=cond['harness_id'], version=cond['harness_version'],
                                       capabilities=(PROCESS_FEEDBACK_CAPABILITY,)), soft_budget=True)
        def ready(workspace, recorder, session):
            now = time.time()
            data.update(created_at=utc(now), deadline=utc(now+workspace.remaining()),
                        deadline_epoch=now+workspace.remaining(), retained_epoch=now+7*86400,
                        retained_until=utc(now+7*86400),
                        tool_identity={'image_id': session.image_id, 'public_revision': self.revision,
                                       'evaluator': self.evaluator_identity,
                                       'solver_resources': {k: v.sha256 for k, v in self.resources.items()},
                                       **({'external': self.solver_runtime.identity}
                                          if self.solver_runtime else {})})

        def completed(report):
            with self.lock:
                data['report'] = report
                for event in self.state.run_events(sid):
                    if event['kind'] == 'submission' and event['data']['receipt'].get('accepted'):
                        self.state.accept_event(data, event)
                self.state.save(data)

        def failed(_error):
            with self.lock:
                data['interrupted'] = True
                self.state.save(data)

        handle = self.session_control.start(
            sid, task=self.task, config=config, resources=self.resources,
            backends=self.backends, destination=self.root/sid/'run', image=self.image,
            solver_runtime=self.solver_runtime,
            execution={'interface': PROTOCOL, 'condition': cond},
            on_ready=ready, on_complete=completed, on_error=failed,
        )
        signaled, attached = self.session_control.await_ready(
            handle, SESSION_STARTUP_TIMEOUT_SECONDS)
        if not attached:
            reason = 'startup_failed' if signaled else 'startup_timeout'
            data.update(interrupted=True, startup_failure=reason)
            if handle.startup_exception_type:
                startup['exception_type'] = handle.startup_exception_type
            startup.update(state='failed', reason=reason,
                           elapsed_seconds=time.monotonic()-started)
            self.state.write_startup(sid, startup)
            self.state.save(data)
            raise APIError(500, 'infrastructure_error', 'Session startup failed; see startup.json')
        startup.update(state='ready', elapsed_seconds=time.monotonic()-started)
        self.state.write_startup(sid, startup)
        response = self._status(data) | {'protocol': PROTOCOL, 'session_token': data['token'],
            'task': {'id': self.task.id, 'sha256': self.task.digest, 'description': self.task.description(),
                      'input_paths': [f'/task/{i.path}' for i in self.task.inputs], 'workspace_root': '/workspace'},
            'limits': data['limits'], 'capabilities': [PROCESS_FEEDBACK_CAPABILITY],
            'tool_identity': data['tool_identity'], 'retained_until': data['retained_until']}
        data['creation_response'] = response
        self.state.save(data)
        return 201, response


    def _close(self, data):
        active = self._status(data)['active_execution_id']
        data['closing'] = True
        self.session_control.close_session(data['session_id'], active)
        return {k:self._status(data)[k] for k in ('session_id','state','last_submission')}

    def _cancel(self, data, eid):
        if eid not in data['executions']:
            raise APIError(404, 'not_found', 'Execution not found')
        self.session_control.cancel_execution(data['session_id'], eid)
        return {'execution_id': eid, 'state': data['executions'][eid]['state']}

    def _write_file(self, data, path, raw):
        workspace = self.session_control.workspace(data['session_id'])
        if len(raw) > self.limits['max_file_bytes']:
            raise APIError(413, 'too_large', 'File exceeds limit')
        workspace.write(path, raw, self.limits['max_file_bytes'])
        return {'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}

    def _submit(self, data, key):
        sid = data['session_id']
        workspace = self.session_control.workspace(sid)
        receipt = workspace.request({'action':'submit', 'key':key})
        if not receipt.get('accepted'):
            raise ValueError('Candidate was not accepted')
        # Read the authoritative durable submission, not the mutable workspace.
        for event in self.state.run_events(sid):
            if event['kind']=='submission' and event['data']['receipt'].get('idempotency_key')==key:
                self.state.accept_event(data, event)
        return dict(data['submissions'][str(receipt['sequence'])])

    def _execute(self, data, command, timeout):
        sid = data['session_id']
        if not isinstance(command,str) or not command.strip() or '\x00' in command or len(command.encode())>128*1024:
            raise ValueError('Invalid command')
        if timeout is not None and (type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0):
            raise ValueError('Invalid timeout')
        eid = uuid.uuid4().hex
        def started():
            data['executions'][eid] = {
                'execution_id': eid, 'state': 'running', 'exit_code': None,
                'log_size': 0, 'truncated': False,
            }

        def progress(size, truncated):
            with self.lock:
                data['executions'][eid].update(log_size=size, truncated=truncated)

        def completed(code, size, truncated):
            with self.lock:
                data['executions'][eid].update(
                    state={124: 'timed_out', 125: 'cancelled', 126: 'error',
                           137: 'error'}.get(code, 'complete'),
                    exit_code=code, log_size=size, truncated=truncated,
                )
                self._observe(data, 'execution.completed', dict(data['executions'][eid]))
                self.state.save(data)

        self.session_control.start_execution(
            sid, eid, command, timeout,
            self.root/sid/(eid+'.log'), self.limits['max_log_bytes'],
            should_close=lambda: bool(data.get('closing')),
            on_started=started, on_progress=progress, on_complete=completed,
        )
        return {'execution_id': eid,'state': 'running'}

    def _read_file(self, data, path):
        workspace = self.session_control.workspace(data['session_id'])
        raw = workspace.read(path, self.limits['max_file_bytes'])
        return {'path': path, 'content_base64': base64.b64encode(raw).decode(),
                'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}

    def shutdown(self):
        for sid, handle in self.session_control.active_handles():
            workspace = handle.workspace
            if workspace is not None and workspace.active:
                try:
                    with self.lock:
                        data = self.state.runs[sid]
                        active = self._status(data)['active_execution_id']
                        data['closing'] = True
                        self.session_control.close_session(sid, active)
                except (OSError, TimeoutError, APIError):
                    pass
        for sid, _handle in self.session_control.active_handles():
            self.session_control.join(sid, timeout=60)
        self.lease.__exit__(None, None, None)
