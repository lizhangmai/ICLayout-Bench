"""Commit immutable workspace snapshots without blocking session status or cancellation."""

import copy
import threading
import time

from benchmarking.execution.checkpoints import (
    DEFAULT_CHECKPOINT_POLICY,
    checkpoint_failure,
)


class CheckpointJobs:
    """The controller serializes mutations; this module owns snapshot jobs and commit receipts."""

    def __init__(self, state, lock, on_finish):
        self.state, self.lock, self.on_finish = state, lock, on_finish
        self.jobs = {}

    def busy(self, sid):
        job = self.jobs.get(sid)
        return job is not None and not job['done'].is_set()

    def status(self, sid):
        job = self.jobs.get(sid)
        return ({'state': job['state'], 'elapsed_seconds': round(time.monotonic()-job['started'], 3),
                 **job.get('metrics', {})} if job else None)

    def start(self, data, workspace, commit):
        sid = data['session_id']
        if self.busy(sid):
            raise RuntimeError('Workspace checkpoint already in progress')
        frozen = copy.deepcopy(data)
        commit(frozen)
        job = {'done': threading.Event(), 'state': 'running', 'started': time.monotonic()}
        self.jobs[sid] = job

        def run():
            try:
                metrics = self.state.checkpoint(frozen, workspace)
                with self.lock:
                    commit(data)
                    self.state.save(data)
                    job.update(state='complete', metrics=metrics or {})
            except Exception as error:  # noqa: BLE001 -- persist a sanitized background failure
                with self.lock:
                    data.update(interrupted=True, checkpoint_error=True,
                                checkpoint_failure=checkpoint_failure(error))
                    job['state'] = 'error'
                    try:
                        self.state.save(data)
                    except OSError as storage_error:
                        job['metrics'] = {'persistence_error': type(storage_error).__name__}
            finally:
                with self.lock:
                    job['metrics'] = dict(job.get('metrics', {}), elapsed_seconds=round(time.monotonic()-job['started'], 3))
                    try:
                        self.on_finish(sid)
                    finally:
                        job['done'].set()

        job['thread'] = threading.Thread(target=run, daemon=True)
        job['thread'].start()
        return job['done']

    def join(self):
        for job in list(self.jobs.values()):
            job['thread'].join(DEFAULT_CHECKPOINT_POLICY.total_seconds + 30)
            if job['thread'].is_alive():
                raise TimeoutError('Workspace checkpoint did not stop within its budget')
