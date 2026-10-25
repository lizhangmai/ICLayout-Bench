"""Exercise the actual bounded checkpoint pipe with synthetic subprocess output."""

import json
import subprocess
import sys
import time

import pytest

from benchmarking.execution.checkpoints import CheckpointPolicy
from benchmarking.execution.workspace.access import SessionWorkspace

pytestmark = pytest.mark.unit


def checkpoint_process(tmp_path, monkeypatch, body, policy):
    script = tmp_path / 'transport.py'
    script.write_text('import sys,time\n' + body)
    workspace = SessionWorkspace('unused', tmp_path, [], time.monotonic()+60)
    workspace.checkpoint_policy = policy
    monkeypatch.setattr(workspace, 'reader', lambda: [sys.executable, '-I', str(script)])
    monkeypatch.setattr(workspace, 'access_timeout', lambda: .01)
    return workspace


def test_progressing_checkpoint_has_its_own_total_budget(tmp_path, monkeypatch):
    metadata = json.dumps({'workspace_digest': 'a'*64, 'unchanged': False}) + '\n'
    workspace = checkpoint_process(tmp_path, monkeypatch,
        f'sys.stdout.buffer.write({metadata.encode()!r});sys.stdout.buffer.flush()\n'
        'for chunk in (b"a",b"b",b"c"):\n'
        ' sys.stdout.buffer.write(chunk);sys.stdout.buffer.flush()\n',
        CheckpointPolicy(total_seconds=30, idle_seconds=10))
    # Ordinary file access must not supply the checkpoint's transport budget.
    monkeypatch.setattr(workspace, 'access_timeout', lambda: pytest.fail('Used file-access budget'))
    archive = tmp_path/'checkpoint.tar.gz'
    result = workspace.checkpoint(archive, 1024)
    assert archive.read_bytes() == b'abc'
    assert result['workspace_digest'] == 'a'*64


def test_checkpoint_stall_is_bounded_independently_of_total_budget(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from benchmarking.execution.workspace import access

    workspace = checkpoint_process(tmp_path, monkeypatch, 'time.sleep(60)\n',
                                   CheckpointPolicy(total_seconds=30, idle_seconds=10))
    clock = [0]
    monkeypatch.setattr(access, 'time', SimpleNamespace(monotonic=lambda: clock[0]))

    def stalled(selector, timeout):
        assert timeout == 10  # The idle allowance expires before the total budget.
        clock[0] += timeout
        return []

    monkeypatch.setattr(access.selectors.DefaultSelector, 'select', stalled)
    with pytest.raises(subprocess.TimeoutExpired) as failure:
        workspace.checkpoint(tmp_path/'checkpoint.tar.gz', 1024)
    assert failure.value.timeout == 30
    assert failure.value.elapsed_seconds == 10
