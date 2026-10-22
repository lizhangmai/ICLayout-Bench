"""Durable coordinator ownership, detached execution and read-only worker adoption."""

import fcntl
import json
import os
import signal
import subprocess
import sys
import threading
from dataclasses import asdict
from pathlib import Path

from benchmarking.execution.leases import BatchLease, BatchLeaseError
from benchmarking.execution.process import process_start, stop_process_tree
from benchmarking.files import append_event, write_json
from benchmarking.participants.attempt.storage import (
    CaseLease,
    CaseRecord,
    case_lease_root,
)
from benchmarking.results.package import verify


class SchedulerLease(BatchLease):
    # The detached child retains this same open file description after launch.
    unlock_on_exit = False


def stop_batch(output):
    """Stop recorded owners, including workers left behind by a coordinator."""
    root = Path(output).resolve()
    paths = [root / '.scheduler/owner.json']
    for record in CaseRecord.discover(root):
        paths.extend((record.runtime / 'worker.json', record.service / '.private/owner.json'))
    recorded = [(path, json.loads(path.read_text())) for path in paths if path.is_file()]
    if not recorded:
        raise ValueError('No recorded process owners at --output')
    # One Python launcher may move on to another condition after completing
    # this one; its old journal must not authorize stopping that later work.
    owners = [owner for path, owner in recorded
              if path != paths[0] or owner.get('state') == 'running']
    stopped = [stop_process_tree(owner) for owner in owners]
    return {'output': str(root), 'state': 'stopped', 'owners': stopped}


class Coordinator:
    def __init__(self, output, row, inherited_fd=None):
        self.root = Path(output) / '.scheduler'
        self.row = row
        self.inherited_fd = inherited_fd
        self.exit_code = None
        self.handlers = {}

    def event(self, kind, **fields):
        append_event(self.root / 'events.jsonl', kind, durable=True, **fields)

    def __enter__(self):
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.lease = SchedulerLease(self.root)
        if self.inherited_fd is None:
            self.lease.__enter__()
        else:
            expected = self.lease.path.stat()
            actual = os.fstat(self.inherited_fd)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise ValueError('Inherited scheduler lease does not match this output')
            fcntl.flock(self.inherited_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lease._stream = os.fdopen(self.inherited_fd, 'ab')
        try:
            return self._start()
        except BaseException:
            self.lease.__exit__(*sys.exc_info())
            raise

    def _start(self):
        previous_path = self.root / 'owner.json'
        if previous_path.exists():
            previous = json.loads(previous_path.read_text())
            if previous.get('state') == 'running':
                self.event('scheduler_recovered', previous_pid=previous['pid'])
        self.owner = {'pid': os.getpid(), 'start': process_start(os.getpid()), 'state': 'running',
                      'concurrency': self.row['concurrency'], 'tasks': self.row['tasks'],
                      'repetitions': self.row['repetitions']}
        write_json(previous_path, self.owner)
        self.event('scheduler_started', pid=self.owner['pid'], concurrency=self.row['concurrency'])
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGINT):
                self.handlers[signum] = signal.signal(signum, self.interrupted)
        return self

    def interrupted(self, signum, frame):
        self.event('scheduler_interrupted', signal=signum)
        write_json(self.root / 'owner.json', dict(self.owner, state='interrupted', exit_code=128 + signum))
        # Case/native children keep their own inherited leases and settlement.
        os._exit(128 + signum)

    def __exit__(self, kind, error, traceback):
        try:
            state = 'failed' if kind is not None else 'complete'
            self.event('scheduler_stopped', state=state, exit_code=self.exit_code,
                       error_type=kind.__name__ if kind else None)
            write_json(self.root / 'owner.json', dict(self.owner, state=state, exit_code=self.exit_code))
        finally:
            for signum, handler in self.handlers.items():
                signal.signal(signum, handler)
            self.lease.__exit__(kind, error, traceback)


def live_worker(root):
    path = Path(root) / '.runtime/worker.json'
    try:
        owner = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    if not owner['start'] or process_start(owner['pid']) != owner['start']:
        return None
    parent = owner.get('scheduler')
    if parent:
        if process_start(parent['pid']) == parent['start']:
            raise BatchLeaseError('Case still belongs to a live scheduler: ' + str(root))
    else:
        # Older journals did not name the scheduler. Only a reparented worker
        # establishes orphanhood; do not guess from the result's running state.
        try:
            fields = Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(') ', 1)[1].split()
        except FileNotFoundError:
            return None
        if fields[1] != '1':
            raise BatchLeaseError('Cannot establish orphaned worker ownership: ' + str(root))
    return owner


def live_slots(output):
    slots = {}
    unowned = []
    for record in CaseRecord.discover(output):
        value = record.read()
        if value['state'] in {'pending', 'running', 'finalizing'}:
            owner = live_worker(record.root)
            if owner is not None:
                slots[str(record.root.relative_to(output))] = owner
            else:
                unowned.append((record, value))
    roots = {case_lease_root(output / name, CaseRecord(output / name).read()['identity']['plan'][0]['repetitions'])
             for name in slots}
    for record, value in unowned:
        root = case_lease_root(record.root, value['identity']['plan'][0]['repetitions'])
        # Pending repetitions share the known worker's root lease. A running
        # slot without its own verified worker could still hold a native solve.
        if value['state'] == 'pending' and root in roots:
            continue
        try:
            with CaseLease(root):
                pass
        except BatchLeaseError as error:
            raise BatchLeaseError('Unverified live case owner; wait for exit and use --collect-only: ' + str(record.root)) from error
    return slots


def observe_worker(root, owner, cancelled):
    """Observe committed output; never take a live worker's lease or restart it."""
    record = CaseRecord(root)
    while not cancelled.is_set():
        value = record.read()
        if value['state'] == 'finished':
            verify(record.root, value)
            return value['summary']
        if value['state'] in {'suspended', 'blocked'} and value.get('summary'):
            return value['summary']
        if process_start(owner['pid']) != owner['start']:
            # Re-read after observing exit to close the final commit/exit race.
            value = record.read()
            if value['state'] == 'finished':
                verify(record.root, value)
                return value['summary']
            raise RuntimeError('Retained worker exited before terminal commit; use --collect-only: ' + str(root))
        cancelled.wait(.05)
    return None


def detach(options, prepared):
    """Transfer the frozen plan and coordinator lease over private inherited pipes."""
    output = prepared.output
    control = output / '.scheduler'
    control.mkdir(parents=True, mode=0o700, exist_ok=True)
    data = asdict(options)
    data['results_data'] = str(options.results_data) if options.results_data else None
    payload = {'options': data, 'row': prepared.planned.row,
               'selection': prepared.planned.selection.launch_payload(),
               'output': str(output), 'identity': prepared.identity}
    with SchedulerLease(control) as lease, (control / 'runner.log').open('a') as log:
        os.chmod(control / 'runner.log', 0o600)
        process = subprocess.Popen([sys.executable, '-I', '-m', 'benchmarking.participants.batch', str(lease.fileno())],
            stdin=subprocess.PIPE, stdout=log, stderr=log, text=True,
            start_new_session=True, pass_fds=(lease.fileno(),))
        try:
            process.stdin.write(json.dumps(payload))
            process.stdin.close()
        except BaseException:
            process.terminate()
            process.wait(timeout=10)
            raise
        receipt = {'pid': process.pid, 'start': process_start(process.pid),
                   'output': str(output), 'log': str(control / 'runner.log'), 'state': 'starting'}
        write_json(control / 'launch.json', receipt)
        append_event(control / 'events.jsonl', 'scheduler_detached', durable=True, pid=process.pid)
    print(json.dumps(receipt), flush=True)
    return 0


def status(output):
    """Inspect public scheduling fields without reading session tokens or native homes."""
    from benchmarking.participants.attempt.progress import inspect_run
    output = Path(output).resolve()
    rows = []
    for record in CaseRecord.discover(output):
        value = record.read()
        summary = value.get('summary') or {}
        worker = record.runtime / 'worker.json'
        try:
            owner = json.loads(worker.read_text())
        except FileNotFoundError:
            owner = None
        rows.append({'task': value['identity']['plan'][0]['tasks'][0], 'state': value['state'],
                     'directory': str(record.root.relative_to(output)),
                     'score': summary.get('score'), 'outcome': summary.get('outcome'),
                     'worker_alive': bool(owner and process_start(owner['pid']) == owner['start'])})
        progress = inspect_run(record.root)
        rows[-1].update({key: progress[key] for key in
                        ('runner_status', 'evaluation_status', 'evidence_status', 'preview_status')})
    control = output / '.scheduler'
    path = control / 'owner.json'
    launch = control / 'launch.json'
    owner = json.loads(path.read_text()) if path.exists() else json.loads(launch.read_text()) if launch.exists() else {}
    if launch.exists():
        receipt = json.loads(launch.read_text())
        if receipt['pid'] != owner.get('pid') and receipt['start'] and process_start(receipt['pid']) == receipt['start']:
            owner = receipt
    if not rows and not owner:
        raise ValueError('No recorded cases or scheduler at --output')
    return {'output': str(output), 'scheduler': {key: owner.get(key) for key in
            ('pid', 'state', 'exit_code', 'concurrency')},
            'scheduler_alive': bool(owner and process_start(owner['pid']) == owner['start']),
            'states': {state: sum(row['state'] == state for row in rows) for state in sorted({r['state'] for r in rows})},
            'cases': rows}
