"""Local HTTP adapter over DockerSession, RunRecorder and run_session.

One live session per process. Existing run artifacts remain authoritative;
http.json stores only API credentials, request replay and execution metadata.
"""
import base64
import hashlib
import json
import math
import secrets
import subprocess
import threading
import time
import traceback
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from benchmarking.engine.execution import run_session
from benchmarking.engine.identity import evaluation_identity
from benchmarking.engine.model_config import RunConfig
from benchmarking.engine.recorder import BatchLease, atomic_write
from benchmarking.engine.session import DockerSession
from benchmarking.files import Asset, relative
from benchmarking.harnesses import HarnessSpec
from benchmarking.protocol import (
    PROTOCOL,
    SESSION_STARTUP_TIMEOUT_SECONDS,
    USAGE_FIELDS,
    condition,
    identifier,
    json_bytes,
)


def utc(epoch):
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace('+00:00', 'Z')


class APIError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def fields(body, expected):
    if not isinstance(body, dict) or set(body) != set(expected):
        raise ValueError('Unexpected request fields')


def session_limits(task, seconds=None):
    if task.hours is not None:
        if seconds is not None and not math.isclose(seconds, task.wall_seconds):
            raise ValueError("Service budget cannot override task hours")
        seconds = task.wall_seconds
    if seconds is None:
        raise ValueError("Task must explicitly declare hours before serving a solve")
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Session budget must be positive and finite')
    return {'wall_seconds': seconds, 'cpus': 4, 'memory_mb': 8192, 'pids': 512, 'workspace_mb': 2048,
                           'max_file_bytes': 4*1024*1024, 'max_response_bytes': 8*1024*1024,
                           'max_candidate_bytes': task.output.max_bytes, 'max_command_seconds': seconds,
                           'max_log_bytes': 4*1024*1024, 'diagnostic_requests': 0, 'opinion_requests': 0}


class AttachedSession(DockerSession):
    def __init__(self, image, ready):
        super().__init__(image)
        self.ready = ready

    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs, on_ready=self.ready)


class LocalService:
    def __init__(self, root, task, resources, backends, image, token, *, seconds=None, revision='unknown'):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.lease = BatchLease(self.root).__enter__()
        self.task, self.resources, self.backends = task, resources, backends
        self.image, self.token, self.revision = image, token, revision
        self.evaluator_identity = evaluation_identity(task, backends)
        self.lock = threading.RLock()
        self.runs, self.live, self.workspaces, self.threads = {}, {}, {}, {}
        self.limits = session_limits(task, seconds)
        for meta in self.root.glob('*/http.json'):
            data = json.loads(meta.read_bytes())
            self.runs[data['session_id']] = data
            # Never restart a model or silently replay an execution after interruption.
            report = meta.parent/'run/run.json'
            if report.exists():
                raw = json.loads(report.read_bytes())
                if raw.get('phase') == 'finished':
                    data['report'] = raw
            if 'report' not in data:
                data['interrupted'] = True
                for execution in data.get('executions', {}).values():
                    if execution['state'] == 'running':
                        execution.update(state='error', exit_code=None)
                journal = meta.parent/'run/events.jsonl'
                if journal.exists():
                    for line in journal.read_bytes().splitlines():
                        try:
                            event = json.loads(line)
                        except ValueError:
                            break
                        if event['kind'] == 'session.created':
                            subprocess.run(['docker', 'rm', '-f', event['data']['container_id']],
                                           capture_output=True, timeout=30, check=False)
                        if event['kind'] == 'submission' and event['data']['receipt'].get('accepted'):
                            self._accept_event(data, event)
                self._save(data)

    def _save(self, data):
        atomic_write(self.root/data['session_id']/'http.json', json_bytes(data))

    def _accept_event(self, data, event):
        receipt = event['data']['receipt']
        key = receipt.get('idempotency_key')
        # Container-side unkeyed helpers are compatibility submissions, not HTTP requests.
        sub = str(receipt['sequence'])
        data['submissions'][sub] = {'submission_id': sub, 'sequence': receipt['sequence'],
            'candidate_sha256': receipt['sha256'], 'size_bytes': receipt['bytes'], 'accepted_at': event['time']}
        if key:
            replay_key = 'submissions:' + key
            data['requests'].setdefault(replay_key, {'body': {'path': self.task.output.path}, 'status': 200,
                'response': data['submissions'][sub] | {'protocol': PROTOCOL}})

    def _status(self, data):
        if data.get('interrupted'):
            state = 'error'
        elif 'report' in data:
            state = 'error' if data['report']['outcome'] == 'error' else 'complete'
        elif data.get('closing') or data['session_id'] in self.workspaces and not self.workspaces[data['session_id']].active:
            state = 'evaluating'
        else:
            state = 'active'
        subs = data['submissions']
        return {'session_id': data['session_id'], 'state': state, 'created_at': data['created_at'],
                    'deadline': data['deadline'], 'remaining_seconds': max(0, data['deadline_epoch']-time.time())
                    if state == 'active' else 0,
                    'active_execution_id': next((k for k, v in data['executions'].items() if v['state']=='running'), None),
                    'last_submission': max(subs.values(), key=lambda s:s['sequence']) if subs else None,
                    'diagnostics_remaining': 0, 'opinions_remaining': 0}

    def _result(self, data):
        status = self._status(data)
        report = data.get('report', {})
        verdict = {'passed':'pass', 'failed':'fail', 'no_submission':'no_submission', 'error':'error'}.get(report.get('outcome'))
        if data.get('interrupted'):
            verdict = 'error'
        metrics = {}
        failure_reason = report.get('evaluation_error')
        evaluation = self.root/data['session_id']/'run/evaluation/report.json'
        if report.get('evaluation') and evaluation.exists():
            judged = json.loads(evaluation.read_bytes())
            metrics = judged.get('metrics', {})
            rejected = [name + ': ' + job['status']
                        for name, job in judged.get('jobs', {}).items() if job['status'] != 'passed']
            if verdict in ('fail', 'error'):
                failure_reason = '; '.join(rejected) or 'Task requirements not satisfied'
        elif verdict in ('no_submission', 'error'):
            failure_reason = failure_reason or report.get('reason') or report.get('termination')
        return {'session_id': data['session_id'], 'state': status['state'], 'task_id': data['task_id'],
                    'task_sha256': data['task_sha256'], 'condition': data['condition'], 'tool_identity': data['tool_identity'],
                    'limits': data['limits'], 'verification_level': 'local_development',
                    'provenance': {'candidate': 'server_observed' if status['last_submission'] else 'unknown',
                                    'interaction': 'server_observed', 'condition': 'participant_reported', 'usage': 'unknown'},
                    'usage': dict.fromkeys(USAGE_FIELDS), 'submission': status['last_submission'], 'outcome': verdict,
                    'task_success': report.get('task_success'), 'score': report.get('score'), 'metrics': metrics,
                    'failure_category': ('service_failure' if data.get('interrupted') or report.get('termination') == 'infrastructure_error'
                                         else 'evaluation_tool_error' if verdict == 'error' and report.get('evaluation_error')
                                         else 'unknown' if verdict == 'error' else None),
                    'failure_reason': data.get('startup_failure', 'service_interrupted') if data.get('interrupted') else failure_reason, 'evidence': []}

    def handle(self, method, path, query, token, body, key):
        with self.lock:
            parts = path.strip('/').split('/')
            if parts[:2] != ['v1', 'sessions']:
                raise APIError(404, 'not_found', 'Route not found')
            if not token:
                raise APIError(401, 'unauthorized', 'Bearer token required')
            if method == 'POST':
                identifier(key)
                json_bytes(body)
            if parts == ['v1', 'sessions']:
                if not secrets.compare_digest(token, self.token):
                    raise APIError(401, 'unauthorized', 'Invalid access token')
                if method != 'POST' or query:
                    raise APIError(404, 'not_found', 'Route not found')
                fields(body, ('task_id','condition'))
                for data in self.runs.values():
                    if data['creation_key'] == key:
                        if data['creation_body'] != body:
                            raise APIError(409, 'conflict', 'Idempotency key conflict')
                        if 'creation_response' not in data:
                            raise APIError(500, 'infrastructure_error', 'Session creation was interrupted')
                        return 201, data['creation_response']
                status, response = self._create(body, key)
                self._observe(self.runs[response['session_id']], 'session.created',
                              {'task_id': body['task_id'], 'limits': response['limits']})
                return status, response
            if len(parts) < 3:
                raise APIError(404, 'not_found', 'Route not found')
            data = self.runs.get(parts[2])
            if data is None or not secrets.compare_digest(token, data['token']):
                raise APIError(404, 'not_found', 'Session not found')
            route = '/'.join(parts[3:])
            if time.time() > data['retained_epoch']:
                raise APIError(410, 'session_closed', 'Retention period ended')
            if method == 'POST':
                if query:
                    raise ValueError('POST does not accept query parameters')
                cached = data['requests'].get(route+':'+key)
                if cached:
                    if cached['body'] != body:
                        raise APIError(409, 'conflict', 'Idempotency key conflict')
                    return cached['status'], cached['response']
                self._active(data)
                status, result = self._post(data, route, body, key)
                result['protocol'] = PROTOCOL
                data['requests'][route+':'+key] = {'body': body, 'status': status, 'response': result}
                detail = {k: v for k, v in result.items() if k != 'protocol'}
                if route == 'executions':
                    detail.update(command=body['command'], timeout_seconds=body['timeout_seconds'])
                self._observe(data, route, detail)
                return status, result
            if method != 'GET':
                raise ValueError('Unsupported method')
            result = self._get(data, route, query)
            if route == 'file':
                self._observe(data, 'file.read', {k: result[k] for k in ('path', 'sha256', 'size_bytes')})
            return 200, result | {'protocol': PROTOCOL}

    def _observe(self, data, kind, detail):
        # Only API-visible material belongs here; internal judge journals stay private.
        events = data.setdefault('observations', [])
        events.append({'sequence': len(events), 'timestamp': utc(time.time()),
                       'kind': kind, 'data': detail})
        self._save(data)

    def _active(self, data, idle=False):
        status = self._status(data)
        if status['state'] != 'active' or time.time() >= data['deadline_epoch']:
            raise APIError(410, 'session_closed', 'Session closed')
        if idle and status['active_execution_id']:
            raise APIError(409, 'conflict', 'Execution in progress')

    def _create(self, body, key):
        if body['task_id'] != self.task.id:
            raise APIError(404, 'not_found', 'Task not found')
        cond = condition(body['condition'])
        if len(self.runs) >= 100 or any(self._status(d)['state'] not in ('complete','error') for d in self.runs.values()):
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
        self.runs[sid] = data
        self._save(data)
        started = time.monotonic()
        startup = {'state': 'starting', 'timeout_seconds': SESSION_STARTUP_TIMEOUT_SECONDS}
        startup_path = self.root/sid/'startup.json'
        atomic_write(startup_path, json_bytes(startup))
        ready = threading.Event()
        abandoned = threading.Event()
        startup_lock = threading.Lock()
        config = RunConfig(cond['harness_id'], self.image, ('/bin/sleep','infinity'), self.limits['wall_seconds'],
                           self.limits['memory_mb'], self.limits['cpus'], self.limits['pids'],
                           self.limits['workspace_mb'], {}, {}, Asset(json_bytes(cond), 'json'),
                           HarnessSpec(id=cond['harness_id'], version=cond['harness_version']))
        def attach(workspace, recorder):
            with startup_lock:
                if abandoned.is_set():
                    raise RuntimeError("Session startup abandoned")
                now = time.time()
                data.update(created_at=utc(now), deadline=utc(now+workspace.remaining()),
                            deadline_epoch=now+workspace.remaining(), retained_epoch=now+7*86400,
                            retained_until=utc(now+7*86400),
                            tool_identity={'image_id': session.image_id, 'public_revision': self.revision,
                                           'evaluator': self.evaluator_identity,
                                           'solver_resources': {k: v.sha256 for k, v in self.resources.items()}})
                self.workspaces[sid] = workspace
                ready.set()
        session = None
        def run():
            nonlocal session
            try:
                session = AttachedSession(self.image, attach)
                report = run_session(self.task, config, self.resources, self.backends, self.root/sid/'run',
                                   session=session, execution={'interface':PROTOCOL, 'condition':cond})
                if sid not in self.workspaces:
                    ready.set()
                    return
                with self.lock:
                    data['report'] = report
                    for line in (self.root/sid/'run/events.jsonl').read_bytes().splitlines():
                        event = json.loads(line)
                        if event['kind'] == 'submission' and event['data']['receipt'].get('accepted'):
                            self._accept_event(data, event)
                    self._save(data)
            except Exception as error:  # noqa: BLE001 -- persist worker failures and return sanitized HTTP errors
                traceback.print_exc()
                if sid not in self.workspaces:
                    startup['exception_type'] = type(error).__name__
                    ready.set()
                    return
                with self.lock:
                    data['interrupted'] = True
                    self._save(data)
            finally:
                ready.set()
        self.runs[sid] = data
        self.threads[sid] = threading.Thread(target=run, daemon=True)
        self.threads[sid].start()
        signaled = ready.wait(SESSION_STARTUP_TIMEOUT_SECONDS)
        with startup_lock:
            if sid not in self.workspaces:
                abandoned.set()
                reason = 'startup_failed' if signaled else 'startup_timeout'
                data.update(interrupted=True, startup_failure=reason)
                startup.update(state='failed', reason=reason, elapsed_seconds=time.monotonic()-started)
                atomic_write(startup_path, json_bytes(startup))
                self._save(data)
                raise APIError(500, 'infrastructure_error', 'Session startup failed; see startup.json')
            startup.update(state='ready', elapsed_seconds=time.monotonic()-started)
            atomic_write(startup_path, json_bytes(startup))
        response = self._status(data) | {'protocol': PROTOCOL, 'session_token': data['token'],
            'task': {'id': self.task.id, 'sha256': self.task.digest, 'description': self.task.description(),
                      'input_paths': [f'/task/{i.path}' for i in self.task.inputs], 'workspace_root': '/workspace'},
            'limits': data['limits'], 'capabilities': [], 'tool_identity': data['tool_identity'], 'retained_until': data['retained_until']}
        data['creation_response'] = response
        self._save(data)
        return 201, response

    def _get(self, data, route, query):
        if route == '' and not query:
            return self._status(data)
        if route == 'result' and not query:
            return self._result(data)
        if route == 'observations' and set(query) <= {'offset'}:
            if len(query.get('offset', ['0'])) != 1:
                raise ValueError('Expected one observation offset')
            offset = int(query.get('offset', ['0'])[0])
            events = data.get('observations', [])
            if offset < 0 or offset > len(events):
                raise ValueError('Invalid observation offset')
            page, size = [], 0
            for event in events[offset:offset + 100]:
                size += len(json_bytes(event))
                if page and size > 256 * 1024:
                    break
                page.append(event)
            return {'session_id': data['session_id'], 'provenance': 'server_observed',
                    'available': 'observations' in data, 'events': page,
                    'next_offset': offset + len(page), 'has_more': offset + len(page) < len(events)}
        if route.startswith('submissions/') and not query:
            receipt = data['submissions'].get(route.split('/')[1])
            if receipt:
                return dict(receipt)
        if route.startswith('executions/') and set(query) <= {'offset'}:
            eid = route.removeprefix('executions/')
            execution = data['executions'].get(eid)
            if execution:
                offset = int(query.get('offset',['0'])[0])
                if offset < 0 or offset > execution['log_size']:
                    raise ValueError('Invalid log offset')
                with (self.root/data['session_id']/(eid+'.log')).open('rb') as stream:
                    stream.seek(offset)
                    content = stream.read(min(256*1024, execution['log_size']-offset))
                return {k:execution[k] for k in ('execution_id','state','exit_code','truncated')} | {
                    'log_base64': base64.b64encode(content).decode(), 'next_offset': offset+len(content)}
        if route == 'file' and set(query) == {'path'} and len(query['path']) == 1:
            self._active(data, idle=True)
            path = relative(query['path'][0], 'file path')
            raw = self.workspaces[data['session_id']].read(path, self.limits['max_file_bytes'])
            return {'path': path, 'content_base64': base64.b64encode(raw).decode(),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}
        raise APIError(404, 'not_found', 'Route not found')

    def _post(self, data, route, body, key):
        sid = data['session_id']
        workspace = self.workspaces[sid]
        if route == 'close':
            fields(body, ())
            active = self._status(data)['active_execution_id']
            data['closing'] = True
            if active:
                workspace.cancel(active)
            else:
                workspace.request({'action':'close'})
            return 202, {k:self._status(data)[k] for k in ('session_id','state','last_submission')}
        if route.startswith('executions/') and route.endswith('/cancel'):
            fields(body, ())
            eid = route.split('/')[1]
            if eid not in data['executions']:
                raise APIError(404, 'not_found', 'Execution not found')
            if eid in self.live:
                workspace.cancel(eid)
            return 200, {'execution_id': eid, 'state': data['executions'][eid]['state']}
        self._active(data, idle=True)
        if route == 'files':
            fields(body, ('path','content_base64'))
            path = relative(body['path'], 'file path')
            raw = base64.b64decode(body['content_base64'], validate=True)
            if len(raw) > self.limits['max_file_bytes']:
                raise APIError(413, 'too_large', 'File exceeds limit')
            workspace.write(path, raw, self.limits['max_file_bytes'])
            return 200, {'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}
        if route == 'submissions':
            fields(body, ('path',))
            if body['path'] != self.task.output.path:
                raise ValueError('Submit the declared task output path')
            receipt = workspace.request({'action':'submit', 'key':key})
            if not receipt.get('accepted'):
                raise ValueError('Candidate was not accepted')
            # Read the authoritative durable submission, not the mutable workspace.
            for line in (self.root/sid/'run/events.jsonl').read_bytes().splitlines():
                event = json.loads(line)
                if event['kind']=='submission' and event['data']['receipt'].get('idempotency_key')==key:
                    self._accept_event(data, event)
            return 200, dict(data['submissions'][str(receipt['sequence'])])
        if route == 'executions':
            fields(body, ('command','timeout_seconds'))
            command, timeout = body['command'], body['timeout_seconds']
            if not isinstance(command,str) or not command.strip() or '\x00' in command or len(command.encode())>128*1024:
                raise ValueError('Invalid command')
            if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:
                raise ValueError('Invalid timeout')
            eid = uuid.uuid4().hex
            process = workspace.execute(eid, command, min(timeout, self.limits['max_command_seconds']))
            self.live[eid] = process
            (self.root/sid/(eid+'.log')).touch(mode=0o600)
            data['executions'][eid] = {'execution_id': eid, 'state': 'running', 'exit_code': None, 'log_size': 0, 'truncated': False}
            def collect():
                size, truncated = 0, False
                try:
                    process.stdin.write(command.encode())
                    process.stdin.close()
                    with (self.root/sid/(eid+'.log')).open('ab', buffering=0) as log:
                        while chunk := process.stdout.read1(8192):
                            room = max(0,self.limits['max_log_bytes']-size)
                            log.write(chunk[:room])
                            truncated |= len(chunk)>room
                            size += min(len(chunk),room)
                            with self.lock:
                                data['executions'][eid].update(log_size=size,truncated=truncated)
                    code = process.wait()
                except Exception:  # noqa: BLE001 -- persist worker failures and return sanitized HTTP errors
                    traceback.print_exc()
                    code = 126
                with self.lock:
                    data['executions'][eid].update(state={124:'timed_out',125:'cancelled',126:'error',137:'error'}.get(code,'complete'),
                                                  exit_code=code,log_size=size,truncated=truncated)
                    self._observe(data, 'execution.completed', dict(data['executions'][eid]))
                    self.live.pop(eid,None)
                    if data.get('closing') and workspace.active:
                        workspace.request({'action':'close'})
                    self._save(data)
            threading.Thread(target=collect,daemon=True).start()
            return 202, {'execution_id': eid,'state': 'running'}
        raise APIError(404,'not_found','Route not found')


    def shutdown(self):
        for sid, workspace in self.workspaces.items():
            if workspace.active:
                try:
                    with self.lock:
                        self._post(self.runs[sid], 'close', {}, 'shutdown')
                except (OSError, TimeoutError, APIError):
                    pass
        for thread in self.threads.values():
            thread.join(timeout=60)
        self.lease.__exit__(None, None, None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Avoid credentials, query paths and candidate data in access logs.

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def _dispatch(self):
        self.connection.settimeout(30)
        try:
            url = urlsplit(self.path)
            body = None
            if self.command == 'POST':
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 6*1024*1024:
                    raise APIError(413,'too_large','Request size exceeds limit')
                body = json.loads(self.rfile.read(size))
            auth = self.headers.get('Authorization','')
            token = auth[7:] if auth.startswith('Bearer ') else ''
            status,result = self.server.service.handle(self.command,url.path,parse_qs(url.query),token,body,
                                                       self.headers.get('Idempotency-Key'))
        except APIError as error:
            status,result = error.status, {'error':{'code': error.code,'message': str(error),'retryable': error.status==503}}
        except (ValueError,TypeError,KeyError):
            status,result = 400, {'error':{'code': 'invalid_request','message': 'Invalid request','retryable': False}}
        except Exception:  # noqa: BLE001 -- persist worker failures and return sanitized HTTP errors
            traceback.print_exc()
            status,result = 500, {'error':{'code': 'infrastructure_error','message': 'Service operation failed','retryable': False}}
        raw = json_bytes(result | {'protocol':PROTOCOL})
        try:
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            if status == 503:
                self.send_header('Retry-After','1')
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):
            pass  # Acknowledged state is already durable; retry with the same key.


def serve(service, port=0):
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.service = service
    return server
