"""Supervise a participant process group; interpretation belongs to the caller."""

import os
import signal
import subprocess


def execute(argv, *, cwd, env, stdout, stderr, timeout, prompt=None, pass_fds=()):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                               stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,
                               text=True, start_new_session=True, pass_fds=pass_fds)
    timed_out = False
    try:
        try:
            process.communicate(prompt, timeout=max(.001, timeout))
        except subprocess.TimeoutExpired:
            timed_out = True
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
