"""Durable identity of the local service process, independent of its launcher."""

import math
import os
import signal
import subprocess
import time
from pathlib import Path


def _stat(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return fields[0], int(fields[1]), fields[19]
    except (OSError, ValueError, IndexError):
        return None


def process_start(pid):
    """Linux process identity: a recycled PID must never authorize adoption/stop."""
    try:
        fields = _stat(pid)
        if fields is None or fields[0] in {"Z", "X"}:
            return None
        return {"ticks": fields[2], "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    except (OSError, IndexError):
        return None


def _descendants(owners):
    """Discover descendants only while their recorded parent identities match."""
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    table = {int(path.name): value for path in Path('/proc').iterdir()
             if path.name.isdigit() and (value := _stat(int(path.name))) is not None}
    selected = {pid for pid, start in owners.items() if pid in table
                and start == {'ticks': table[pid][2], 'boot': boot}}
    while True:
        children = {pid for pid, fields in table.items() if fields[1] in selected}
        if children <= selected:
            break
        selected.update(children)
    return {pid: {'ticks': table[pid][2], 'boot': boot} for pid in selected
            if table[pid][0] not in {'Z', 'X'}}


def _signal(owner, signum):
    """Check the recorded identity; use pidfds when this Python supports them."""
    pid = owner['pid']
    if pid == os.getpid():
        raise ValueError('Cannot stop the controlling process itself')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        if process_start(pid) != owner['start']:
            return False
        try:
            os.kill(pid, signum)
            return True
        except ProcessLookupError:
            return False
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return False
    try:
        if process_start(pid) != owner['start']:
            return False
        signal.pidfd_send_signal(fd, signum)
        return True
    except ProcessLookupError:
        return False
    finally:
        os.close(fd)


def stop_process_tree(owner, *, timeout=60):
    """Stop an owned coordinator and detached descendants, without new work.

    Give the coordinator's normal shutdown handler the grace period. If it
    exits first, interrupt the captured children directly. Discover children
    throughout cleanup and retain their identities after reparenting. Remaining
    processes are killed after the grace period; stale identities are untouched.
    """
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError('Stop timeout must be finite and nonnegative')
    pid, start = owner.get('pid'), owner.get('start')
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or not isinstance(start, dict):
        raise ValueError('Stopping requires a recorded PID and process start identity')
    if not start.get('ticks') or not start.get('boot'):
        raise ValueError('Stopping requires a recorded PID and process start identity')
    if pid == os.getpid():
        raise ValueError('Cannot stop the controlling process itself')
    if process_start(pid) != start:
        return {'state': 'not_running', 'pid': pid, 'stopped_pids': [], 'forced_pids': []}
    known = _descendants({pid: start})
    _signal(owner, signal.SIGTERM)
    if (value := _stat(pid)) and value[0] in {'T', 't'}:
        _signal(owner, signal.SIGCONT)
    interrupted, forced = set(), []
    deadline = time.monotonic() + timeout
    while True:
        known.update(_descendants(known))
        live = {p: s for p, s in known.items() if process_start(p) == s}
        if not live:
            break
        if process_start(pid) != start:
            for child, identity in live.items():
                if child not in interrupted:
                    _signal({'pid': child, 'start': identity}, signal.SIGINT)
                    if (value := _stat(child)) and value[0] in {'T', 't'}:
                        _signal({'pid': child, 'start': identity}, signal.SIGCONT)
                    interrupted.add(child)
        if time.monotonic() >= deadline:
            for child, identity in live.items():
                if _signal({'pid': child, 'start': identity}, signal.SIGKILL):
                    forced.append(child)
            break
        time.sleep(.05)
    deadline = time.monotonic() + 5
    while any(process_start(p) == s for p, s in known.items()):
        if time.monotonic() >= deadline:
            raise TimeoutError('Owned processes did not exit after forced shutdown')
        time.sleep(.05)
    return {'state': 'stopped', 'pid': pid, 'stopped_pids': sorted(known), 'forced_pids': forced}


def execute(argv, *, cwd, env, stdout, stderr, timeout, prompt=None, pass_fds=(), expired=None):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                               stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
                               text=True, start_new_session=True, pass_fds=pass_fds)
    timed_out = False
    deadline = time.monotonic() + max(.001, timeout) if timeout is not None else None
    try:
        while True:
            remaining = max(.001, deadline-time.monotonic()) if deadline is not None else None
            try:
                process.communicate(prompt, timeout=min(.5, remaining) if remaining is not None
                                    else .5 if expired is not None else None)
                break
            except subprocess.TimeoutExpired:
                prompt = None
                if (deadline is not None and time.monotonic() >= deadline
                        or expired is not None and expired()):
                    timed_out = True
                    break
        return process.returncode, timed_out
    finally:
        # Descendants must stop even when the original process already exited.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            if sig == signal.SIGTERM:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        process.wait(timeout=10)
