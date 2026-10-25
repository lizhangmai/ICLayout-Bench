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
        ' time.sleep(.04);sys.stdout.buffer.write(chunk);sys.stdout.buffer.flush()\n',
        CheckpointPolicy(total_seconds=1, idle_seconds=.5))
    archive = tmp_path/'checkpoint.tar.gz'
    result = workspace.checkpoint(archive, 1024)
    assert archive.read_bytes() == b'abc'
    assert result['workspace_digest'] == 'a'*64


def test_checkpoint_stall_is_bounded_independently_of_total_budget(tmp_path, monkeypatch):
    workspace = checkpoint_process(tmp_path, monkeypatch, 'time.sleep(5)\n',
                                   CheckpointPolicy(total_seconds=1, idle_seconds=.1))
    with pytest.raises(subprocess.TimeoutExpired):
        workspace.checkpoint(tmp_path/'checkpoint.tar.gz', 1024)
