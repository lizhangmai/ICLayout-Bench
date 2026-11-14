"""Bounded, idempotent removal of an explicitly owned Docker container."""

import json
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path


def remove_container(container_id):
    result = {'state': 'error', 'attempts': []}
    deadline = time.monotonic() + 30
    try:
        while True:
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
            selector = ('id=' + container_id if re.fullmatch(r'[a-f0-9]{12,64}', container_id)
                        else 'name=^/' + re.escape(container_id) + '$')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            inspected = subprocess.run(['docker', 'ps', '-aq', '--no-trunc', '--filter', selector],
                                       capture_output=True, timeout=min(10, remaining), check=False)
            result['inspect_exit_code'] = inspected.returncode
            if inspected.returncode == 0 and not inspected.stdout.strip():
                return dict(result, state='absent')
            # Shutdown can interrupt the Docker client before the daemon has
            # removed its container. Retry once, only after confirming it exists.
            interrupted = removed.returncode in {
                -signal.SIGINT, -signal.SIGTERM, 128 + signal.SIGINT, 128 + signal.SIGTERM}
            removing = b'already in progress' in removed.stderr.lower()
            if inspected.returncode or not (removing or interrupted and len(result['attempts']) < 2):
                break
            if removing:
                time.sleep(min(.05, max(0, deadline - time.monotonic())))
    except (OSError, subprocess.SubprocessError) as error:
        result['error_type'] = type(error).__name__
    return result


class ContainerLease:
    """A separate host process owns creation and removal across owner death.

    The private pipe is the lease. Its EOF survives abrupt termination of the
    caller, including while Docker is creating the container. No Docker socket
    or host supervision capability is exposed inside the container.
    """

    def __init__(self, arguments, *, kind):
        self.process = subprocess.Popen(
            [sys.executable, '-I', str(Path(__file__).resolve()), '--guard'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True)
        self.result = None
        try:
            request = {'arguments': list(arguments), 'name': 'iclayout-' + uuid.uuid4().hex, 'kind': kind}
            self.process.stdin.write(json.dumps(request).encode() + b'\n')
            self.process.stdin.flush()
            response = json.loads(self.process.stdout.readline())
            if 'id' not in response:
                raise subprocess.SubprocessError(response.get('error', 'Docker container creation failed'))
            self.id = response['id']
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        result = self.close()
        if result['state'] == 'error' and exception_type is None:
            raise subprocess.SubprocessError('Container cleanup failed: ' + json.dumps(result))
        return False

    def close(self):
        """Release once and retain the same bounded cleanup diagnostic."""
        if self.result is not None:
            return self.result
        self.process.stdin.close()
        self.process.stdin = None
        try:
            output, _ = self.process.communicate(timeout=70)
            self.result = json.loads(output)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            # Never interrupt the independent remover because the caller's
            # bounded wait expired. Its pipe is closed and it owns no new work.
            self.result = {'state': 'error', 'error_type': type(error).__name__}
        return self.result


def cleanup_containers(container_ids, *, apply=False):
    """Inspect or remove only explicitly selected, unambiguous container IDs."""
    results = []
    for selected in container_ids:
        if not re.fullmatch(r'[a-f0-9]{12,64}', selected):
            raise ValueError('Cleanup requires explicit hexadecimal container IDs of at least 12 characters')
        matched = subprocess.check_output(
            ['docker', 'ps', '-aq', '--no-trunc', '--filter', 'id=' + selected], text=True, timeout=10).split()
        if not matched:
            results.append({'id': selected, 'state': 'absent'})
            continue
        if len(matched) != 1:
            raise ValueError('Ambiguous container ID: ' + selected)
        container = json.loads(subprocess.check_output(
            ['docker', 'inspect', matched[0]], text=True, timeout=10))[0]
        record = {'id': container['Id'], 'name': container['Name'].lstrip('/'),
                  'image': container['Image'], 'status': container['State']['Status'], 'state': 'selected'}
        if apply:
            record.update(remove_container(container['Id']))
        results.append(record)
    return results


def _guard():
    # Coordinated host shutdown may signal all descendants after their owner
    # exits. Let the small, bounded remover finish instead of interrupting it.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    request = json.loads(sys.stdin.buffer.readline())
    target = request['name']
    try:
        created = subprocess.run(
            ['docker', 'create', '--name', target,
             '--label', 'org.iclayout.bench.managed=true',
             '--label', 'org.iclayout.bench.kind=' + request['kind'], *request['arguments']],
            capture_output=True, timeout=30, check=False)
        if created.returncode:
            raise RuntimeError(created.stderr[:2048].decode(errors='replace'))
        target = created.stdout.decode().strip()
        print(json.dumps({'id': target}), flush=True)
        sys.stdin.buffer.read()  # Parent closes the pipe after exports or on death.
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
        try:
            print(json.dumps({'error': str(error)}), flush=True)
        except BrokenPipeError:
            pass
    finally:
        result = remove_container(target)
        try:
            print(json.dumps(result), flush=True)
        except BrokenPipeError:
            pass


if __name__ == '__main__' and sys.argv[1:] == ['--guard']:
    _guard()
