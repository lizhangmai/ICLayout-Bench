"""Supervise an operator-selected participant process without choosing its actions."""

import os

from benchmarking.client import Client
from benchmarking.files import atomic_write
from benchmarking.observe import export_observation
from benchmarking.participants.lifecycle import (
    participant_timeout,
    settle_session,
    wait_result,
)
from benchmarking.participants.process import execute
from benchmarking.protocol import json_bytes
from benchmarking.results.analysis import export_session_result


def run_command(access, task_id, frozen, output, *, creation_key):
    output.mkdir(mode=0o700)
    created = access.create(task_id, frozen['condition'], key=creation_key)
    sid = created['session_id']
    client = Client(access.endpoint, created['session_token'], timeout=60)
    atomic_write(output / 'session.json', json_bytes({k: v for k, v in created.items() if k != 'session_token'}))
    atomic_write(output / 'conditions.json', json_bytes(frozen))
    env = {k: v for k, v in os.environ.items() if not k.startswith('ICLAYOUT_BENCH_')}
    env.update(ICLAYOUT_BENCH_ENDPOINT=access.endpoint, ICLAYOUT_BENCH_TOKEN=created['session_token'],
               ICLAYOUT_BENCH_SESSION=sid, ICLAYOUT_BENCH_TASK_FILE=str(output / 'session.json'))
    error, exit_code = None, None
    try:
        with (output / 'stdout.jsonl').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
            exit_code, timed_out = execute(frozen['command'], cwd=frozen['cwd'], env=env,
                                            stdout=stdout, stderr=stderr,
                                            timeout=participant_timeout(created, client.session(sid)))
            if timed_out:
                error = 'participant_timeout'
            elif exit_code:
                error = 'participant_exit_' + str(exit_code)
    except OSError:
        error = 'participant_start_failed'
    finally:
        try:
            settle_session(client, sid, None, output, snapshot=False)
        finally:
            atomic_write(output / 'harness.json', json_bytes({'condition': frozen['condition'],
                                                            'error': error, 'exit_code': exit_code}))
    result = wait_result(client, sid)
    export_session_result(result, output / 'analysis')
    export_observation(client, sid, output / 'observation',
                       participant_files=[p for p in output.iterdir() if p.is_file() and p.name != 'session.json'])
    return result
