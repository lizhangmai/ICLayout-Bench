"""Real isolated sessions. Scripted clients verify protocol, not model ability."""

import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest
from helpers.protocol import write_protocol_task

from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.evidence.journal import (
    RecordingError,
    RunRecorder,
    recover_submissions,
)
from benchmarking.execution.budgets import PhaseBudgets
from benchmarking.execution.harness import PROCESS_FEEDBACK_CAPABILITY, HarnessSpec
from benchmarking.execution.inference import InferenceConfig, InferenceGateway
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.execution.workspace.config import RunConfig
from benchmarking.execution.workspace.docker import CONSOLE_PREVIEW_BYTES, DockerSession
from benchmarking.execution.workspace.environment import task_message
from benchmarking.files import Asset, ReadOnlyMount
from benchmarking.tasks.contract import load_task

IMAGE = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
from helpers.catalog import ROOT as PUBLIC_ROOT

PREAMBLE = '''import json, os, subprocess, time
from pathlib import Path
task = json.loads(Path('/protocol/task.json').read_text())
output = Path(task['output']['path'])
output.parent.mkdir(parents=True, exist_ok=True)
def submit():
    p = subprocess.run(['python', '-I', '/protocol/submit.py'], capture_output=True, text=True)
    print(p.stdout, flush=True)
    return json.loads(p.stdout)
'''


def session_task():
    with tempfile.TemporaryDirectory(prefix="protocol-task-") as directory:
        return load_task(write_protocol_task(Path(directory)))


def configuration(code, seconds=10):
    return RunConfig("protocol-test", IMAGE, ("python", "/agent/cli.py"),
                     seconds, 256, 1, 32, 16, {"cli.py": Asset((PREAMBLE+code).encode(), "python")},
                     {}, Asset(b"test-only programmatic configuration", "text"))


def execute(code, seconds=10, task=None):
    task = task or session_task()
    config = configuration(code, seconds)
    return DockerSession(config.image).run(task, config, {}, task_message(task, config))


@pytest.mark.acceptance_container
@pytest.mark.parametrize('cleanup_overlap', [False, True])
def test_mcp_long_execution_can_be_cancelled_and_session_cleanup_finishes(tmp_path, monkeypatch, cleanup_overlap):
    import threading
    from types import SimpleNamespace

    from benchmarking.client import Client
    from benchmarking.participants.mcp import Bridge, dispatch
    from benchmarking.service.application import LocalService
    from benchmarking.service.server import serve

    if cleanup_overlap:
        # A cancellation helper can be descheduled after publishing its marker.
        # Let real command cleanup overlap that helper before its receipt exits.
        original_run = subprocess.run
        delayed_receipt = '''import pathlib, runpy, sys, time
original_touch = pathlib.Path.touch
def touch(self, *args, **kwargs):
    result = original_touch(self, *args, **kwargs)
    time.sleep(.3)
    return result
pathlib.Path.touch = touch
sys.argv = ['/protocol/workspace.py', 'cancel', sys.argv[1]]
runpy.run_path('/protocol/workspace.py', run_name='__main__')
'''

        def run(command, **kwargs):
            if command[-3:-1] == ['/protocol/workspace.py', 'cancel']:
                command = [*command[:-3], '-c', delayed_receipt, command[-1]]
            return original_run(command, **kwargs)

        monkeypatch.setattr(subprocess, 'run', run)

    task = session_task()
    def unexpected(*args):
        raise AssertionError('No evaluation without an accepted candidate')
    backends = {job.operation: SimpleNamespace(identity={'fixture': 'unused'}, run=unexpected)
                for job in task.evaluation.jobs}
    service = LocalService(tmp_path / 'store', task, {}, backends, IMAGE, 'operator', seconds=60, recoverable=False)
    server = serve(service)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        endpoint = f'http://127.0.0.1:{server.server_port}'
        created = Client(endpoint, 'operator').create(task.id, {
            'harness_kind': 'agent', 'harness_id': 'fixture', 'harness_version': '1', 'model': 'none',
            'prompt_sha256': None, 'configuration_sha256': None}, key='create')
        sid = created['session_id']
        client = Client(endpoint, created['session_token'])
        bridge = Bridge(client, sid, tmp_path / 'tools.jsonl')
        running = bridge.call('execute', {'command': 'python -c "import time; time.sleep(60)"', 'wait_seconds': 0})
        assert running['state'] == 'running'
        rejected = dispatch(bridge, {'id': 1, 'method': 'tools/call', 'params': {
            'name': 'execute', 'arguments': {'command': 'tail diagnostic.log', 'wait_seconds': 0}}})
        assert rejected['result']['isError'] is True
        assert rejected['result']['content'][0]['text'].startswith('conflict:')
        bridge.call('cancel', {'execution_id': running['execution_id']})
        polled = bridge.call('poll', {'execution_id': running['execution_id'], 'wait_seconds': 10})
        assert polled['state'] == 'cancelled'
        recovered = bridge.call('execute', {'command': 'printf recovered', 'wait_seconds': 10})
        assert recovered['state'] == 'complete' and recovered['exit_code'] == 0
        assert recovered['output'] == 'recovered'
        client.close(sid, key='close')
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            result = client.result(sid)
            if result['state'] in {'complete', 'error'}:
                break
            time.sleep(.1)
        assert result['state'] == 'complete', result
        assert result['outcome'] == 'no_submission'
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=5)


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_cancelled_check_stops_host_eda_and_keeps_session_usable(tmp_path):
    import threading
    from types import SimpleNamespace

    from benchmarking.client import Client
    from benchmarking.eda.environment import ExternalRuntime
    from benchmarking.evaluation.contracts import JobResult
    from benchmarking.execution.tools.native import NativeTool
    from benchmarking.participants.mcp import Bridge
    from benchmarking.service.application import LocalService
    from benchmarking.service.server import serve

    started = tmp_path / 'native-started'
    finished = threading.Event()
    observed = []
    tool = NativeTool(ExternalRuntime('fixture', {'image': 'unused', 'environment': {}, 'mounts': []}))

    def evaluate(job, assets):
        if job.id == 'artifact' and not observed:
            result = tool.run([sys.executable, '-c',
                ('import os,time; from pathlib import Path; '
                f'Path({str(started)!r}).write_text(str(os.getpid())); '
                'print("Quantus terminated normally", flush=True); time.sleep(4)')], {}, {})
            observed.append(result)
            finished.set()
            return JobResult('error', result.reason or 'Synthetic tool finished', evidence=result.evidence)
        return JobResult('failed', 'Synthetic candidate rejection', evidence={'log': Asset(b'fixture', 'text')})

    task = session_task()
    backend = SimpleNamespace(identity={'fixture': 'native-cancellation'}, run=evaluate)
    service = LocalService(tmp_path / 'store', task, {},
        {job.operation: backend for job in task.evaluation.jobs}, IMAGE, 'operator', seconds=60,
        recoverable=False)
    server = serve(service)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        endpoint = f'http://127.0.0.1:{server.server_port}'
        created = Client(endpoint, 'operator').create(task.id, {
            'harness_kind': 'agent', 'harness_id': 'fixture', 'harness_version': '1', 'model': 'none',
            'prompt_sha256': None, 'configuration_sha256': None}, key='create')
        sid = created['session_id']
        client = Client(endpoint, created['session_token'])
        client.write(sid, task.output.path, b'frozen-candidate', key='candidate')
        bridge = Bridge(client, sid, tmp_path / 'tools.jsonl')
        execution = bridge.call('execute', {'command': 'python -I /protocol/process_check.py', 'wait_seconds': 0})
        deadline = time.monotonic() + 10
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert started.exists(), 'Host EDA did not start'
        bridge.call('cancel', {'execution_id': execution['execution_id']})
        assert bridge.call('poll', {'execution_id': execution['execution_id'], 'wait_seconds': 10})['state'] == 'cancelled'
        assert finished.wait(1), 'Cancelled process_check left its host EDA running'
        assert 'cancel' in observed[0].reason.lower()
        assert b'Quantus terminated normally' in observed[0].evidence['console'].content
        assert not Path(f'/proc/{started.read_text()}').exists()
        recovered = bridge.call('execute', {'command': 'python -I /protocol/process_check.py', 'wait_seconds': 10})
        assert recovered['exit_code'] == 0
        assert json.loads(recovered['output'])['accepted']
        client.close(sid, key='close')
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=5)


@pytest.mark.acceptance
@pytest.mark.acceptance_container
@pytest.mark.parametrize('entry', ['solver', 'tool'])
def test_unrestricted_execution_preserves_container_isolation(monkeypatch, entry):
    observed = []
    original_output = subprocess.check_output
    scratch = '''from pathlib import Path
import tempfile
for name in ('/tmp', '/var/tmp'):
    assert Path(name).stat().st_mode & 0o1777 == 0o1777
    with tempfile.TemporaryDirectory(dir=name) as directory:
        path = Path(directory) / 'scratch.txt'
        path.write_text('temporary data')
        assert path.read_text() == 'temporary data'
'''

    def output(command, **kwargs):
        result = original_output(command, **kwargs)
        if command[:2] == ['docker', 'create']:
            host = json.loads(original_output(
                ['docker', 'inspect', '--format', '{{json .HostConfig}}', result.strip()], text=True))
            observed.append({name: host[name] for name in
                             ('Memory', 'MemorySwap', 'NanoCpus', 'CpuQuota', 'PidsLimit',
                              'NetworkMode', 'CapDrop', 'SecurityOpt', 'ReadonlyRootfs')})
        return result

    monkeypatch.setattr(subprocess, 'check_output', output)
    if entry == 'solver':
        config = replace(configuration(scratch + '''
output.write_bytes(b'unlimited-default')
assert submit()['accepted']
'''), memory_mb=None, cpus=None, pids=None)
        task = session_task()
        result = DockerSession(IMAGE).run(task, config, {}, task_message(task, config))
        assert result.termination == 'completed', result.console.content
        assert result.candidate.content == b'unlimited-default'
        assert observed[0]['ReadonlyRootfs'] is True
    else:
        tool = DockerTool(IMAGE, ['python', '--version'], 10)
        result = tool.run(['python', '-c', scratch + "Path('out.txt').write_text('unlimited-default')"],
                          {}, {'out.txt': 'text'})
        assert result.returncode == 0, result.reason
        assert result.files['out.txt'].content == b'unlimited-default'
        assert observed[0]['ReadonlyRootfs'] is True
    host, = observed
    assert all(host[name] == 0 for name in ('Memory', 'MemorySwap', 'NanoCpus', 'CpuQuota'))
    assert host['PidsLimit'] in (None, 0, -1)
    assert host['NetworkMode'] == 'none'
    assert host['CapDrop'] == ['ALL']
    assert 'no-new-privileges' in host['SecurityOpt']


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_direct_container_jobs_share_the_unlimited_eda_default():
    tool = DockerTool(IMAGE, ['python', '--version'], 10)
    tool.timeout_seconds = .02
    result = tool.run(['python', '-c', 'import time; time.sleep(.1); print("complete")'], {}, {})
    assert result.returncode == 0 and not result.reason
    assert result.evidence['console'].content.strip() == b'complete'


@pytest.mark.acceptance
@pytest.mark.acceptance_container
@pytest.mark.parametrize('diagnostic', [
    'Fatal error (signal SIGSEGV) - crash handler invoked',
    'FLEXnet ERROR(-5, 0, 0): No such feature exists.'])
def test_container_infrastructure_retries_use_fresh_containers_and_keep_failed_outputs(monkeypatch, diagnostic):
    created = []
    original = subprocess.check_output

    def create(command, **kwargs):
        result = original(command, **kwargs)
        if command[:2] == ['docker', 'create']:
            created.append(result.strip())
        return result

    monkeypatch.setattr(subprocess, 'check_output', create)
    tool = DockerTool(IMAGE, ['python', '--version'], 10)
    script = ('from pathlib import Path; '
              'Path("output.gds").write_bytes(Path("input.gds").read_bytes()); '
              f'print({diagnostic!r},flush=True); '
              'raise SystemExit(1)')
    result = tool.run(['python', '-c', script], {'input.gds': Asset(b'frozen input', 'gds')},
                      {'output.gds': 'gds'})
    expected = tool.identity['retry_policy']['max_attempts']
    assert len(created) == len(set(created)) == expected
    assert result.returncode == 1 and result.reason
    attempts = json.loads(result.evidence['tool-attempts.json'].content)
    assert attempts['termination'] == 'exhausted'
    assert len(attempts['attempts']) == expected
    for i in range(1, expected):
        assert result.evidence[f'tool-attempts/{i}/outputs/output.gds'].content == b'frozen input'
    for container in created:
        assert subprocess.run(['docker', 'inspect', container], capture_output=True, check=False).returncode != 0


@pytest.mark.acceptance
@pytest.mark.acceptance_container
@pytest.mark.parametrize('ending', ['complete', 'error', 'timeout', 'cancel'])
def test_tool_memory_workspace_retains_private_outputs_after_failure(tmp_path, monkeypatch, ending):
    model = tmp_path / 'model.txt'
    model.write_bytes(b'mounted model')
    model.chmod(0o444)
    tool = DockerTool(IMAGE, ['python', '--version'], 10)
    if ending == 'timeout':
        tool.timeout_seconds = .5
    script = '''import os, sys, time
from pathlib import Path
source = Path('inputs/source.txt')
model = Path('models/model.txt')
for path in (source, model):
    try:
        path.write_bytes(b'overwrite')
    except OSError:
        pass
    else:
        raise AssertionError('Frozen input is writable')
Path('models/derived.txt').write_bytes(source.read_bytes() + b' / ' + model.read_bytes())
Path('models/derived.txt').chmod(0o600)
os.link('models/derived.txt', 'linked-output.txt')
print('tool evidence', flush=True)
if sys.argv[1] in ('timeout', 'cancel'):
    time.sleep(5)
elif sys.argv[1] == 'error':
    sys.exit(9)
'''
    def execute_tool():
        return tool.run(['python', '-c', script, ending],
                        {'inputs/source.txt': Asset(b'frozen input', 'text'),
                         'models/model.txt': ReadOnlyMount(model, Asset(b'model recipe', 'text'))},
                        {'models/derived.txt': 'text', 'linked-output.txt': 'text'})

    if ending == 'cancel':
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        from benchmarking.execution.tools.budget import (
            tool_cancellation,
            tool_time_limits,
        )

        cancellation = Event()
        containers = []
        original = subprocess.Popen

        def observe(command, **kwargs):
            process = original(command, **kwargs)
            if command[:3] == ['docker', 'exec', '-i'] and not command[3].startswith('-'):
                containers.append(command[3])
            return process

        monkeypatch.setattr(subprocess, 'Popen', observe)

        def check():
            with tool_cancellation(cancellation), tool_time_limits(False):
                return execute_tool()

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(check)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if containers:
                        ready = subprocess.run(['docker', 'exec', containers[0], 'test', '-f',
                                                '/workspace/linked-output.txt'], capture_output=True, check=False)
                        if ready.returncode == 0:
                            break
                    time.sleep(.02)
                else:
                    pytest.fail('Tool did not write its output before cancellation')
            finally:
                cancellation.set()
            result = pending.result(timeout=3)
        assert subprocess.run(['docker', 'inspect', containers[0]], capture_output=True, check=False).returncode != 0
    else:
        if ending == 'timeout':
            from benchmarking.execution.tools.budget import tool_time_limits

            with tool_time_limits(True):
                result = execute_tool()
        else:
            result = execute_tool()
    assert 'models/derived.txt' in result.files, (result.reason, result.evidence)
    assert result.files['models/derived.txt'].content == b'frozen input / mounted model'
    assert result.files['linked-output.txt'].content == b'frozen input / mounted model'
    assert b'tool evidence' in result.evidence['console'].content
    assert model.read_bytes() == b'mounted model'
    if ending == 'complete':
        assert result.returncode == 0 and not result.reason
    elif ending == 'error':
        assert result.returncode == 9 and result.reason
    elif ending == 'cancel':
        assert result.returncode is None and 'cancel' in result.reason
        assert 'execution_error' in result.evidence
    else:
        assert result.returncode is None and 'time limit' in result.reason


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_private_inference_socket_and_submission_with_non_root_agent():
    """Both private host sockets must be usable across daemon UID mappings."""
    profile = InferenceConfig("https://example.invalid/v1", "test-model", "UNUSED", 2, 10,
                              Asset(b"socket regression", "text"), "responses")
    gateway = InferenceGateway(profile, transport=lambda *args: (
        200, "application/json", b'{"status":"completed"}'))
    config = configuration('''
import socket
assert os.getuid() != 0
for name in ('control.sock', 'inference.sock'):
    info = Path('/protocol', name).stat()
    assert info.st_uid == os.getuid()
    assert info.st_mode & 0o777 == 0o600
body = b'{"model":"test-model"}'
with socket.socket(socket.AF_UNIX) as connection:
    connection.settimeout(2)
    connection.connect('/protocol/inference.sock')
    header = {'path': '/responses', 'bytes': len(body)}
    connection.sendall(json.dumps(header).encode() + b'\\n' + body)
    stream = connection.makefile('rb')
    response = json.loads(stream.readline())
    assert response['status'] == 200
    assert json.loads(stream.read(response['bytes']))['status'] == 'completed'
output.write_bytes(b'gateway-and-submission')
assert submit()['accepted']
''')
    task = session_task()
    result = DockerSession(config.image).run(
        task, config, {}, task_message(task, config), inference=gateway)
    assert result.termination == "completed", result.console.content
    assert result.candidate.content == b"gateway-and-submission"


# Protect the public preparation -> actual isolated Agent seam. Existing session
# tests have no process resources. Process-owned checks are declared in pdk.toml;
# this test independently asserts successful execution and read-only isolation.
# It uses no witness or model endpoint and makes no circuit-qualification claim.
@pytest.mark.acceptance_eda
@pytest.mark.parametrize("manifest", sorted((PUBLIC_ROOT / "tasks").glob("*/pdk.toml")),
                         ids=lambda path: path.parent.name)
def test_declared_pdks_are_usable_in_agent_container(tmp_path, manifest):

    from benchmarking.tasks.dataset import Dataset, process_manifest

    cases = [case for case in Dataset(PUBLIC_ROOT, {}).cases().values()
             if process_manifest(case) == manifest]
    assert cases, "A published process must declare at least one case"
    from benchmarking.eda.runtime import load_case

    runtime = load_case(cases[0], image=IMAGE)
    bundle = runtime.agent
    # Case metadata, rather than a process-wide wish list, owns runtime profiles.
    from benchmarking.eda.toolchain import support_bindings

    declaration = tomllib.loads(manifest.read_text())
    backends = tomllib.loads(cases[0].read_text())["toolchain"]["backends"]
    required = {profile for name, backend in backends.items() for _, profile in support_bindings(name, backend)}
    assert {name.split("/")[1] for name, _ in bundle.files if name.startswith("support/")} == required
    assert not any("/verilog-a/" in name or "/compilation/" in name for name, _ in bundle.files)

    from benchmarking.files import ReadOnlyMount

    roots = {name: value for name, value in bundle.files if name.startswith("pdks/")}
    # A reviewed source can expose individual files and directories through paths.
    expected_roots = {
        f"pdks/{name}" + (f"/{path}" if path else "")
        for name, source in declaration["agent"]["sources"].items()
        for path in source.get("paths", [""])
    }
    assert set(roots) == expected_roots
    assert all(isinstance(value, ReadOnlyMount) and (value.path.is_dir() or value.path.is_file())
               for value in roots.values())
    assert all(not item.path.startswith("reference/") for item in runtime.task.inputs)
    resources = {**dict(bundle.files), "manifest.json": bundle.manifest}
    code = f"pdk_mounts = {sorted(expected_roots)!r}\n" + '''
info = task['resources']
assert not Path('/protocol/resources.json').exists()
assert os.environ['ICLAYOUT_BENCH_PDK'] == info['pdk']
assert Path(os.environ['PDK_PATH']).is_dir()
assert not Path('/resources/tasks').exists()
assert not Path('/task/reference').exists()
assert not Path('/var/run/docker.sock').exists()
assert not Path('/resources/tasks').exists()
for name in pdk_mounts:
    source = Path('/resources', name)
    try:
        if source.is_dir():
            (source / 'forbidden').touch()
        else:
            with source.open('r+b'):
                pass
    except OSError:
        pass
    else:
        raise AssertionError('Writable PDK mount')
for command in info['checks']:
    check = subprocess.run(command, capture_output=True, text=True, timeout=90)
    print(check.stdout, check.stderr, flush=True)
    assert check.returncode == 0, command
    assert 'in PCellDeclaration.' not in check.stderr, 'PCell generation failed internally'
print('PDK_CHECKS_PASSED', flush=True)
'''
    config = replace(configuration(code, seconds=180), memory_mb=2048, workspace_mb=256, pids=128)
    task = runtime.task
    result = DockerSession(IMAGE).run(task, config, resources, task_message(task, config))
    assert result.termination == "completed", result.console.content.decode(errors="replace")
    assert b"PDK_CHECKS_PASSED" in result.console.content
    assert result.environment["network"] == "none"


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_isolation_last_submission_and_unsubmitted_mutation(monkeypatch):
    monkeypatch.setenv("LB_HOST_SECRET", "must-not-enter-container")
    result = execute('''
assert not Path('/task/reference').exists()
assert not Path('/task/qualification').exists()
assert not Path('/var/run/docker.sock').exists()
assert 'LB_HOST_SECRET' not in os.environ
assert sorted(p.name for p in Path('/workspace').iterdir()) == ['output']
assert os.getuid() != 0
assert Path("/protocol/control.sock").stat().st_mode & 0o777 == 0o600
assert not Path('/protocol/process_check.py').exists()
for path in ['/task/new', '/protocol/new', '/agent/new', '/etc/new']:
    try:
        Path(path).write_text('forbidden')
    except OSError:
        pass
    else:
        raise AssertionError(path)
import socket
with socket.socket() as s:
    s.settimeout(.1)
    assert s.connect_ex(('1.1.1.1', 443)) != 0
output.write_bytes(b'first')
assert submit()['accepted']
output.write_bytes(b'second')
assert submit()['accepted']
output.write_bytes(b'not submitted')
''')
    assert result.termination == "completed", result.console.content
    assert result.candidate.content == b"second"
    assert len(result.submissions) == 2
    assert result.environment["network"] == "none"


@pytest.mark.acceptance
@pytest.mark.acceptance_container
@pytest.mark.parametrize(("code", "termination", "content"), [
    ("output.write_bytes(b'unsubmitted')", "completed", None),
    ("output.write_bytes(b'accepted'); submit(); raise RuntimeError('agent failure')", "agent_error", b"accepted"),
    ("output.write_bytes(b'accepted'); submit(); time.sleep(30)", "budget_exhausted", b"accepted"),
    ("time.sleep(30)", "budget_exhausted", None),
])
def test_stop_and_submission_are_independent(code, termination, content):
    result = execute(code, seconds=3)
    assert result.termination == termination, result.console.content
    expected_reason = {
        "budget_exhausted": "Wall-clock limit reached",
        "agent_error": "Agent exited with code 1",
        "completed": "",
    }[termination]
    assert result.reason == expected_reason, result.console.content
    assert (result.candidate.content if result.candidate is not None else None) == content
    assert result.elapsed_seconds < 6


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_invalid_submissions_do_not_replace_last_accepted():
    task = session_task()
    task = replace(task, output=replace(task.output, max_bytes=16))
    result = execute('''
output.write_bytes(b'good'); assert submit()['accepted']
output.write_bytes(b'x'*17); assert not submit()['accepted']
output.unlink(); output.symlink_to('/task/input.spice'); assert not submit()['accepted']
output.unlink(); os.mkfifo(output); assert not submit()['accepted']
output.unlink(); output.parent.rmdir()
output.parent.symlink_to('/task'); assert not submit()['accepted']
''', task=task)
    assert result.termination == "completed", result.console.content
    assert result.candidate.content == b"good"
    assert [r["accepted"] for r in result.submissions] == [True, False, False, False, False]


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_duplicate_submission_keeps_last_accepted_snapshot():
    result = execute('''
output.write_bytes(b'first'); assert submit()['accepted']; assert submit()['accepted']
output.write_bytes(b'last'); assert submit()['accepted']; assert submit()['accepted']
''')
    assert result.termination == "completed", result.console.content
    assert result.candidate.content == b"last"
    assert [receipt["sequence"] for receipt in result.submissions] == [1, 2, 3, 4]


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_submission_must_be_durable_before_deadline(tmp_path):
    # The running guide requires the deadline decision after durable storage.
    # Existing timeout tests only delay the Agent, not host artifact I/O. Delay
    # that boundary and verify the prior receipt remains authoritative; this
    # is a protocol regression, not evidence of layout correctness.
    task = session_task()
    config = configuration('''
output.write_bytes(b'on-time'); assert submit()['accepted']
output.write_bytes(b'late-storage'); submit()
''', seconds=3)

    class SlowArchive(RunRecorder):
        def archive(self, asset):
            if asset.content == b'late-storage':
                time.sleep(config.wall_seconds)
            return super().archive(asset)

    recorder = SlowArchive(tmp_path / 'run')
    result = DockerSession(config.image).run(
        task, config, {}, task_message(task, config), recorder=recorder)
    assert result.candidate.content == b'on-time'
    assert result.submissions[-1]['accepted'] is False
    assert recover_submissions(recorder.root)['candidate']['sha256'] == result.candidate.sha256


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_process_feedback_cannot_extend_solver_deadline(tmp_path):
    # Existing feedback coverage uses immediate callbacks. A delayed trusted
    # evaluator must not extend the documented solve budget. Inspect the real
    # container during that callback; a late return alone cannot prove isolation.
    task = session_task()
    config = replace(configuration('''
output.write_bytes(b'accepted'); assert submit()['accepted']
subprocess.run(['python', '-I', '/protocol/process_check.py'])
time.sleep(30)
''', seconds=2), harness=HarnessSpec(capabilities=(PROCESS_FEEDBACK_CAPABILITY,)))
    recorder = RunRecorder(tmp_path / 'run')
    running_during_late_feedback = []

    def feedback(candidate, sequence):
        time.sleep(config.wall_seconds + 1)
        events = [json.loads(line) for line in (recorder.root / 'events.jsonl').read_text().splitlines()]
        cid = next(event['data']['container_id'] for event in events if event['kind'] == 'session.created')
        state = subprocess.run(['docker', 'inspect', '--format', '{{.State.Running}}', cid],
                               capture_output=True, text=True, check=False)
        running_during_late_feedback.append(state.returncode == 0 and state.stdout.strip() == 'true')
        return {'report': {'outcome': 'failed'}}

    result = DockerSession(config.image).run(
        task, config, {}, task_message(task, config), recorder=recorder, feedback=feedback)
    assert running_during_late_feedback == [False]
    assert result.termination == 'budget_exhausted'
    assert result.candidate.content == b'accepted'
    assert result.process_feedback[-1]['outcome'] == 'error'


@pytest.mark.acceptance
@pytest.mark.acceptance_container
@pytest.mark.parametrize('expires', [False, True])
def test_feedback_eda_has_only_the_enclosing_command_deadline(tmp_path, expires):
    task = session_task()
    config = replace(configuration('''
output.write_bytes(b'accepted'); assert submit()['accepted']
subprocess.run(['python', '-I', '/protocol/process_check.py'])
output.write_bytes(b'final'); assert submit()['accepted']
''', seconds=1.5 if expires else 6),
        harness=HarnessSpec(capabilities=(PROCESS_FEEDBACK_CAPABILITY,)), budgets=PhaseBudgets(1.5 if expires else 6, command_seconds=2, settlement_seconds=2))
    tool = DockerTool(IMAGE, ['python', '--version'], 60)
    # A short backend probe limit must not cut off EDA feedback. An explicitly
    # bounded workspace operation still owns its command deadline.
    tool.timeout_seconds = 10 if expires else .1
    seen = []

    def feedback(candidate, sequence):
        result = tool.run(['python', '-c',
            f'import time; print("started", flush=True); time.sleep({4 if expires else .4}); print("done")'],
            {}, {})
        seen.append(result)
        return {'report': {'outcome': 'error' if result.reason else 'passed'}}

    result = DockerSession(config.image).run(
        task, config, {}, task_message(task, config),
        recorder=RunRecorder(tmp_path / 'run'), feedback=feedback)
    assert result.candidate.content == b'final'
    assert len(seen) == 1
    assert result.termination == 'completed'
    assert result.process_feedback[-1]['outcome'] == ('error' if expires else 'passed'), seen[0].reason
    assert (b'done' in seen[0].evidence['console'].content) is (not expires)
    assert result.submissions[-1]['after_budget'] is expires


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_process_feedback_is_opt_in_and_uses_a_frozen_snapshot(tmp_path):
    task = session_task()
    config = replace(configuration('''
output.write_bytes(b'feedback-candidate')
# Regression: checks after the former sixteen-request ceiling remain available.
for _ in range(18):
    feedback = subprocess.run(['python', '-I', '/protocol/process_check.py'],
                              capture_output=True, text=True, check=True)
    assert json.loads(feedback.stdout)['accepted']
print(feedback.stdout, flush=True)
'''), harness=HarnessSpec(capabilities=(PROCESS_FEEDBACK_CAPABILITY,)))
    seen = []

    def feedback(candidate, sequence):
        seen.append((candidate.content, sequence))
        if sequence == 2:
            raise RuntimeError("synthetic feedback error")
        return {"report": {"outcome": "failed", "physical_valid": True,
                            "specs_pass": False, "task_success": False,
                            "backends": {"synthetic": {"version": "1"}}}}

    recorder = RunRecorder(tmp_path / "run")
    result = DockerSession(config.image).run(
        task, config, {}, task_message(task, config), recorder=recorder, feedback=feedback)
    assert result.termination == "completed", result.console.content
    assert result.candidate is None
    assert seen == [(b"feedback-candidate", i) for i in range(1, 19)]
    assert result.process_feedback[-1]["outcome"] == "failed"
    assert result.process_feedback[0]["accepted"] is True
    assert result.process_feedback[0]["candidate"]["sha256"] == Asset(b"feedback-candidate", "gds").sha256
    assert result.process_feedback[1]["outcome"] == "error"
    assert "synthetic feedback error" in result.process_feedback[1]["error"]
    assert recover_submissions(recorder.root)["candidate"] is None
    kinds = [json.loads(line)["kind"] for line in (recorder.root / "events.jsonl").read_text().splitlines()]
    assert kinds.count("process_feedback.request") == kinds.count("process_feedback.result") == len(seen)


# The participant-opinion protocol must preserve arbitrary observed text without
# accepting a layout or changing a grade. Existing process feedback is the
# opposite direction. Exercise the real socket, archive and report verification;
# the synthetic opinion is a protocol fixture, not a confirmed benchmark defect.


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_workspace_and_log_limits():
    result = execute('''
try:
    with open('/workspace/fill', 'wb') as f:
        for _ in range(40): f.write(b'x'*1024*1024)
except OSError:
    pass
else:
    raise AssertionError('workspace limit not enforced')
print('y'*100000)
''')
    assert result.termination == "completed", result.console.content
    assert result.console_truncated and len(result.console.content) == CONSOLE_PREVIEW_BYTES


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_complete_console_and_failed_acceptance_persistence(tmp_path, monkeypatch):
    task = session_task()
    config = configuration("print('x'*100000); output.write_bytes(b'good'); submit()")
    recorder = RunRecorder(tmp_path / "run")
    result = DockerSession(config.image).run(task, config, {}, task_message(task, config), recorder=recorder)
    assert result.termination == "completed"
    journal = [json.loads(line) for line in (recorder.root / "events.jsonl").read_text().splitlines()]
    chunks = [e["data"] for e in journal if e["kind"] == "console.chunk"]
    content = bytearray()
    for chunk in chunks:
        assert chunk["offset"] == len(content)
        content.extend((recorder.root / chunk["content"]["path"]).read_bytes())
    assert content.startswith(b'x'*100000 + b'\n')
    assert b'"accepted": true' in content
    assert result.console_truncated and len(result.console.content) == CONSOLE_PREVIEW_BYTES
    assert recover_submissions(recorder.root)["candidate"]["sha256"] == result.candidate.sha256

    failed = RunRecorder(tmp_path / "failed")
    original = failed.event
    def reject(kind, **data):
        if kind == "submission":
            raise RecordingError("injected storage failure")
        return original(kind, **data)
    monkeypatch.setattr(failed, "event", reject)
    result = DockerSession(config.image).run(task, config, {}, task_message(task, config), recorder=failed)
    assert result.termination == "infrastructure_error"
    assert result.candidate is None
    assert b'"accepted": true' not in result.console.content
    assert recover_submissions(failed.root)["candidate"] is None


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_killed_host_retains_acknowledged_candidate(tmp_path):
    # Run the actual host/session in a child, then kill it after the CLI observed its receipt.
    run = tmp_path / "run"
    code = """
import sys
from pathlib import Path
from benchmarking.service.session import run_session
from benchmarking.execution.workspace.docker import DockerSession
from benchmarking.tasks.contract import load_task
sys.path.insert(0, str(Path.cwd() / "tests"))
from integration.test_session import session_task, configuration
config = configuration("output.write_bytes(b'durable'); assert submit()['accepted']; print('ACK_OBSERVED', flush=True); time.sleep(60)", seconds=60)
task = session_task()
run_session(task, config, {}, {job.operation: object() for job in task.evaluation.jobs}, Path(sys.argv[1]), session=DockerSession(config.image))
"""
    staging = tempfile.TemporaryDirectory(prefix="lb-crash-")
    process = subprocess.Popen([sys.executable, "-c", code, str(run)],
                               env={**os.environ, "TMPDIR": staging.name}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cid = None
    try:
        deadline = time.monotonic() + 15
        acknowledged = False
        while time.monotonic() < deadline and process.poll() is None:
            journal = run / "events.jsonl"
            if journal.exists():
                for line in journal.read_bytes().splitlines(keepends=True):
                    if not line.endswith(b'\n'):
                        continue
                    event = json.loads(line)
                    if event["kind"] == "session.created":
                        cid = event["data"]["container_id"]
                    if event["kind"] == "console.chunk":
                        acknowledged |= b'ACK_OBSERVED' in (run / event["data"]["content"]["path"]).read_bytes()
            if acknowledged:
                break
            time.sleep(.05)
        assert acknowledged, process.stderr.read() if process.poll() is not None else "No durable receipt"
        process.kill()
        process.wait(timeout=5)
        recovered = recover_submissions(run)
        assert (run / recovered["candidate"]["path"]).read_bytes() == b"durable"
        assert json.loads((run / "run.json").read_text())["phase"] == "running"
        command = subprocess.run([sys.executable, "-m", "benchmarking.execution", "recover", str(run)], capture_output=True, check=True)
        assert json.loads(command.stdout)["candidate"] == recovered["candidate"]
        # The bind source's parent is private on the host; only individual inputs are mounted.
        temporary = list(Path(staging.name).glob("lb-session-*"))
        assert len(temporary) == 1 and temporary[0].stat().st_mode & 0o777 == 0o700
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        if cid:
            subprocess.run(["docker", "rm", "-f", cid], check=True, capture_output=True, timeout=30)
        staging.cleanup()


@pytest.mark.acceptance
@pytest.mark.acceptance_container
def test_console_storage_ceiling_stops_with_incomplete_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr("benchmarking.execution.workspace.docker.MAX_CONSOLE_BYTES", 8192)
    task = session_task()
    config = configuration("print('x'*100000, flush=True); time.sleep(30)")
    recorder = RunRecorder(tmp_path / "run")
    result = DockerSession(config.image).run(task, config, {}, task_message(task, config), recorder=recorder)
    assert result.termination == "infrastructure_error"
    assert result.environment["console_limit_bytes"] == 8192
    journal = [json.loads(line) for line in (recorder.root / "events.jsonl").read_text().splitlines()]
    assert any(e["kind"] == "console.limit" for e in journal)
    assert journal[-1]["data"]["console_complete"] is False
