"""Stopping recorded owners must cover detached children and reject stale PIDs."""

import json
import os
import signal
import subprocess
import sys

import pytest

from benchmarking.execution.process import process_start, stop_process_tree
from benchmarking.participants import cli

pytestmark = pytest.mark.unit


@pytest.fixture
def tree(tmp_path):
    processes = []

    def launch(*, stubborn=False):
        marker = tmp_path / 'child-stopped'
        child = (
            "import signal,time,pathlib; "
            + ("signal.signal(signal.SIGINT,signal.SIG_IGN); " if stubborn else
               f"signal.signal(signal.SIGINT,lambda *a: (pathlib.Path({str(marker)!r}).touch(),exit(0))); ")
            + "print('ready',flush=True); time.sleep(60)"
        )
        script = (
            "import subprocess,sys,time,signal; "
            + ("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if stubborn else '')
            + f"p=subprocess.Popen([sys.executable,'-I','-c',{child!r}],start_new_session=True,stdout=subprocess.PIPE); "
            "p.stdout.readline(); print(p.pid,flush=True); time.sleep(60)"
        )
        parent = subprocess.Popen([sys.executable, '-I', '-c', script], start_new_session=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        child_pid = int(parent.stdout.readline())
        owner = {'pid': parent.pid, 'start': process_start(parent.pid)}
        processes.append((parent, owner, child_pid, process_start(child_pid)))
        return parent, owner, child_pid, marker

    yield launch
    for parent, owner, child_pid, child_start in processes:
        for pid, start in ((owner['pid'], owner['start']), (child_pid, child_start)):
            if process_start(pid) == start:
                os.kill(pid, signal.SIGKILL)
        parent.wait(timeout=5)
        parent.stdout.close()


@pytest.mark.parametrize('frozen', [False, True])
def test_stop_ends_detached_child_after_coordinator_exit(tree, frozen):
    parent, owner, child_pid, marker = tree()
    if frozen:
        os.kill(parent.pid, signal.SIGSTOP)
    report = stop_process_tree(owner, timeout=2)
    parent.wait(timeout=5)
    assert report['state'] == 'stopped'
    assert process_start(child_pid) is None
    assert marker.exists()  # The child's normal interruption handler ran.
    assert not report['forced_pids']
    assert stop_process_tree(owner)['state'] == 'not_running'


def test_stale_start_identity_never_signals_a_live_process(tree):
    parent, owner, _, _ = tree()
    stale = dict(owner, start=dict(owner['start'], ticks='0'))
    assert stop_process_tree(stale)['state'] == 'not_running'
    assert parent.poll() is None


def test_stubborn_processes_are_killed_after_bounded_grace(tree):
    parent, owner, child_pid, _ = tree(stubborn=True)
    report = stop_process_tree(owner, timeout=.1)
    parent.wait(timeout=5)
    assert process_start(child_pid) is None
    assert set(report['forced_pids']) == {parent.pid, child_pid}


def test_public_cli_stop_uses_recorded_owners_without_configuration(tree, tmp_path, capsys):
    parent, owner, child_pid, _ = tree()
    scheduler = tmp_path / '.scheduler'
    scheduler.mkdir()
    (scheduler / 'owner.json').write_text(json.dumps(dict(owner, state='running')))
    assert cli.main(['--stop', '--output', str(tmp_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['state'] == 'stopped'
    assert parent.poll() is not None and process_start(child_pid) is None


def test_public_stop_finds_retained_worker_without_coordinator(tree, tmp_path):
    from benchmarking.participants.batch.coordinator import stop_batch

    parent, owner, child_pid, _ = tree()
    run = tmp_path / 'task/run'
    (run / '.runtime').mkdir(parents=True)
    (run / 'result.json').write_text('{"identity":{},"state":"suspended"}')
    (run / '.runtime/worker.json').write_text(json.dumps(owner))
    assert stop_batch(tmp_path)['state'] == 'stopped'
    assert parent.poll() is not None and process_start(child_pid) is None


def test_completed_coordinator_may_be_running_a_different_condition(tree, tmp_path):
    from benchmarking.participants.batch.coordinator import stop_batch

    parent, owner, _, _ = tree()
    scheduler = tmp_path / '.scheduler'
    scheduler.mkdir()
    (scheduler / 'owner.json').write_text(json.dumps(dict(owner, state='complete')))
    assert stop_batch(tmp_path)['owners'] == []
    assert parent.poll() is None


@pytest.mark.parametrize('options', [['--resume'], ['--status'], ['--case', 'task'], ['--concurrency', '0']])
def test_public_stop_rejects_execution_options(tmp_path, options):
    with pytest.raises(SystemExit) as error:
        cli.main(['--stop', '--output', str(tmp_path), *options])
    assert error.value.code == 2


def test_stop_rejects_self_and_missing_start_identity():
    with pytest.raises(ValueError, match='start identity'):
        stop_process_tree({'pid': 1234})
    with pytest.raises(ValueError, match='itself'):
        stop_process_tree({'pid': os.getpid(), 'start': process_start(os.getpid())})
