"""Linux tool launcher: wait for the command and any orphaned descendants.

Some batch tools return before their workers. Use a subreaper inside the tool
container so its lifetime includes those workers. The outer evaluator supplies
resource limits and kills the entire container on timeout. This standalone file
also runs with the OS Python supplied by older commercial-tool runtime images.
"""

import argparse
import ctypes
import json
import os
import signal
import sys
import time


def process_snapshot(root_pid):
    """Bounded Linux process/thread diagnostics without argv or environment."""
    processes = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            with open('/proc/' + name + '/stat') as stream:
                raw = stream.read()
            fields = raw[raw.rfind(')') + 2:].split()
            processes[int(name)] = {
                'pid': int(name), 'ppid': int(fields[1]), 'pgrp': int(fields[2]),
                'state': fields[0], 'start_ticks': int(fields[19]),
                'name': raw[raw.find('(') + 1:raw.rfind(')')],
            }
        except (OSError, ValueError, IndexError):
            continue
    selected = {root_pid}
    while True:
        children = {pid for pid, item in processes.items() if item['ppid'] in selected}
        if children <= selected:
            break
        selected.update(children)
    result = []
    for pid in sorted(selected)[:256]:
        if pid not in processes:
            continue
        item = processes[pid]
        item['threads'] = []
        try:
            for tid in sorted(os.listdir('/proc/' + str(pid) + '/task'))[:32]:
                path = '/proc/' + str(pid) + '/task/' + tid
                with open(path + '/wchan') as stream:
                    wait = stream.read().strip()
                with open(path + '/stat') as stream:
                    raw = stream.read()
                item['threads'].append({'tid': int(tid), 'state': raw[raw.rfind(')') + 2:].split()[0],
                                        'wait_channel': wait})
        except (OSError, ValueError, IndexError):
            pass
        result.append(item)
    return result


def kill_descendants(snapshot, root_pid):
    """Kill only captured descendants whose Linux process identity still matches."""
    for item in reversed(snapshot):
        if item['pid'] == root_pid:
            continue
        try:
            with open('/proc/' + str(item['pid']) + '/stat') as stream:
                raw = stream.read()
            if int(raw[raw.rfind(')') + 2:].split()[19]) == item['start_ticks']:
                os.kill(item['pid'], signal.SIGKILL)
        except (OSError, ValueError, IndexError):
            pass


def completion_seen(path, marker, offset, tail):
    """Read a bounded new chunk, including markers split across reads."""
    try:
        with open(path, 'rb') as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() < offset:
                offset, tail = 0, b''
            stream.seek(offset)
            chunk = stream.read(65536)
            marker = marker.encode()
            content = tail + chunk
            return marker in content, stream.tell(), content[-len(marker):]
    except OSError:
        return False, offset, tail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--completion-log')
    parser.add_argument('--completion-marker')
    parser.add_argument('--exit-report')
    parser.add_argument('--exit-grace-seconds', type=float, default=60)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        raise SystemExit('Supply a tool command')
    if bool(args.completion_log) != bool(args.completion_marker) or args.exit_grace_seconds <= 0:
        parser.error('Completion monitoring needs a log, marker and positive exit grace')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot register tool subreaper')
    child = os.fork()
    if child == 0:
        try:
            os.execvp(args.command[0], args.command)
        except OSError as error:
            print(str(error), file=sys.stderr, flush=True)
            os._exit(126)
    status = 0
    command_returncode = None
    snapshot = []
    completed_at = None
    offset, tail = 0, b''
    interrupted = False
    while True:
        try:
            pid, result = os.waitpid(-1, os.WNOHANG if args.completion_log else 0)
        except InterruptedError:
            continue
        except ChildProcessError:
            break
        if not pid:
            if completed_at is None:
                seen, offset, tail = completion_seen(args.completion_log, args.completion_marker, offset, tail)
                if seen:
                    completed_at = time.monotonic()
            if completed_at is not None and time.monotonic() - completed_at >= args.exit_grace_seconds:
                snapshot = process_snapshot(os.getpid())
                print('EDA process did not exit after its completion marker: ' + json.dumps({
                    'exit_grace_seconds': args.exit_grace_seconds, 'processes': snapshot}),
                    file=sys.stderr, flush=True)
                kill_descendants(snapshot, os.getpid())
                status, interrupted = 124, True
                # Reap the captured process tree after forcing its termination.
                args.completion_log = None
            else:
                time.sleep(.05)
            continue
        if os.WIFSIGNALED(result):
            code = 128 + os.WTERMSIG(result)
        elif os.WIFEXITED(result):
            code = os.WEXITSTATUS(result)
        else:
            continue
        if pid == child:
            command_returncode = code
        status = status or code
    code = 124 if interrupted else status
    if args.exit_report:
        # The launcher owns this file. Vendor log rotation or stdout handling
        # must not discard the process-exit decision and its diagnostics.
        temporary = args.exit_report + '.tmp'
        with open(temporary, 'x') as stream:
            json.dump({'schema': 'iclayout-tool-exit-v1', 'returncode': code,
                       'command_returncode': command_returncode,
                       'completion_seen': completed_at is not None,
                       'exit_grace_exceeded': interrupted,
                       'exit_grace_seconds': args.exit_grace_seconds,
                       'processes': snapshot}, stream)
            stream.write('\n')
        os.replace(temporary, args.exit_report)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
