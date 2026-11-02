"""Bounded, idempotent removal of an explicitly owned Docker container."""

import signal
import subprocess
import time


def remove_container(container_id):
    result = {'state': 'error', 'attempts': []}
    deadline = time.monotonic() + 30
    try:
        for _ in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            removed = subprocess.run(['docker', 'rm', '-f', container_id], capture_output=True,
                                     timeout=remaining, check=False)
            attempt = {'remove_exit_code': removed.returncode,
                       'stderr': removed.stderr[:2048].decode(errors='replace')}
            result['attempts'].append(attempt)
            result.update(attempt)
            if not removed.returncode:
                return dict(result, state='removed')
            # A competing shutdown may already have removed the same owned ID.
            # A successful daemon query with no matching ID proves cleanup complete.
            inspected = subprocess.run(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'id=' + container_id],
                                       capture_output=True, timeout=10, check=False)
            result['inspect_exit_code'] = inspected.returncode
            if inspected.returncode == 0 and not inspected.stdout.strip():
                return dict(result, state='absent')
            # Shutdown can interrupt the Docker client before the daemon has
            # removed its container. Retry once, only after confirming it exists.
            if inspected.returncode or removed.returncode not in {
                -signal.SIGINT, -signal.SIGTERM, 128 + signal.SIGINT, 128 + signal.SIGTERM,
            }:
                break
    except (OSError, subprocess.SubprocessError) as error:
        result['error_type'] = type(error).__name__
    return result
