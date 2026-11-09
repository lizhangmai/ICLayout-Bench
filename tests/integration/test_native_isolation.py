"""Common native launch policy, using local probes and no model services."""

import json
import os
import subprocess
import sys

import pytest
from helpers.participant import ServiceFixture

from benchmarking.participants.attempt.runner import run_participant
from benchmarking.participants.harnesses.contracts import (
    HARNESSES,
    LaunchContext,
    ParticipantSelection,
)
from benchmarking.participants.isolation import NativeRuntime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('harness', HARNESSES)
def test_every_runner_denies_host_files_and_undeclared_environment(tmp_path, monkeypatch, harness):
    fixture = ServiceFixture()
    host_file = tmp_path / 'unreviewed-host-context.txt'
    host_file.write_text('unreviewed-host-context-249cc')
    monkeypatch.setattr('benchmarking.participants.attempt.runner.Client', lambda *a, **kw: fixture)
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.stage_credentials', lambda *a: set())
    probe = ('import json,os,pathlib; print(json.dumps({"visible":pathlib.Path(' + repr(str(host_file))
             + ').exists(), "inherited":os.environ.get("UNREVIEWED_CONTEXT")}))')
    monkeypatch.setattr('benchmarking.participants.harnesses.registry.prepare',
                        lambda context: [sys.executable, '-I', '-c', probe])
    selected = ParticipantSelection({'harness': harness, 'model': 'fixture', 'effort_resolved': 'low'},
                                    {**os.environ, 'UNREVIEWED_CONTEXT': 'unreviewed-environment-935cd'}, {})
    output = tmp_path / 'repository/results/participant'
    output.parent.mkdir(parents=True)
    result, error = run_participant(fixture, {'harness': harness, 'task': 'fixture',
                                            'scheme': {'version': 'fixture'} if harness == 'command' else {}},
                                     output, selected)
    assert error is None and result['outcome'] == 'no_submission'
    assert json.loads((output / 'harness.jsonl').read_text()) == {'visible': False, 'inherited': None}


def test_explicit_mcp_works_without_exposing_its_host_files(tmp_path):
    private = tmp_path / 'result/.private'
    work = private / 'workspace'
    work.mkdir(parents=True)
    server = tmp_path / 'reviewed-mcp.py'
    server.write_text('import sys,json\nfor line in sys.stdin:\n'
                      ' r=json.loads(line);print(json.dumps({"id":r["id"],"result":r["method"]}),flush=True)\n')
    mcp = work / 'mcp.json'
    original = {'mcpServers': {'declared': {'command': sys.executable, 'args': ['-I', str(server)]}}}
    mcp.write_text(json.dumps(original))
    context = LaunchContext(ParticipantSelection({'harness': 'command'}, dict(os.environ), {}),
                            mcp, work, private.parent, server, 'fixture')
    with NativeRuntime(context) as runtime:
        spec = runtime.context.selection.settings['mcp_servers']['declared']
        relay = [spec['command'], *spec['args']]
        code = ('import json,pathlib,subprocess; '
                f'assert not pathlib.Path({str(server)!r}).exists(); '
                f'p=subprocess.run({relay!r}, input=\'{{"id":7,"method":"ping"}}\\n\', '
                'capture_output=True,text=True,timeout=5); assert p.returncode==0,p.stderr;print(p.stdout)')
        argv, env = runtime.command([sys.executable, '-I', '-c', code])
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {'id': 7, 'result': 'ping'}
    assert json.loads(mcp.read_text())['mcpServers']['declared'] == original['mcpServers']['declared']


def test_missing_isolation_backend_never_falls_back_to_host_execution(tmp_path, monkeypatch):
    from types import SimpleNamespace

    context = SimpleNamespace(selection=SimpleNamespace(condition={'harness': 'command'}))
    runtime = NativeRuntime(context)
    monkeypatch.setattr('benchmarking.participants.isolation.shutil.which', lambda _: None)
    with pytest.raises(ValueError, match='refusing host execution'):
        runtime.__enter__()


def test_unisolated_native_history_is_not_silently_imported(tmp_path):
    from types import SimpleNamespace

    original = tmp_path / 'original-history.jsonl'
    original.write_text('undeclared_skill_from_old_run\n')
    context = SimpleNamespace(output=tmp_path, selection=SimpleNamespace(
        condition={'harness': 'codex'}, environment={'ICLAYOUT_BENCH_RESUME_ID': 'old-session'}))
    with pytest.raises(ValueError, match='no isolated origin'):
        NativeRuntime(context).__enter__()
    assert original.read_text() == 'undeclared_skill_from_old_run\n'
