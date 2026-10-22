"""Bounded, idempotent removal of an explicitly owned Docker container."""

import subprocess


def remove_container(container_id):
    result = {'state': 'error'}
    try:
        removed = subprocess.run(['docker', 'rm', '-f', container_id], capture_output=True, timeout=30, check=False)
        result['remove_exit_code'] = removed.returncode
        if not removed.returncode:
            return dict(result, state='removed')
        result['stderr'] = removed.stderr[:2048].decode(errors='replace')
        # A competing shutdown may already have removed the same owned ID.
        # A successful daemon query with no matching ID proves cleanup complete.
        inspected = subprocess.run(['docker', 'ps', '-aq', '--no-trunc', '--filter', 'id=' + container_id],
                                   capture_output=True, timeout=10, check=False)
        if inspected.returncode == 0 and not inspected.stdout.strip():
            result['state'] = 'absent'
    except (OSError, subprocess.SubprocessError) as error:
        result['error_type'] = type(error).__name__
    return result
