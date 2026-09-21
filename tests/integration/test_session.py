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

from benchmarking.engine.inference import InferenceConfig, InferenceGateway
from benchmarking.engine.model_config import RunConfig
from benchmarking.engine.recorder import (
    RecordingError,
    RunRecorder,
    recover_submissions,
)
from benchmarking.engine.session import (
    CONSOLE_PREVIEW_BYTES,
    DockerSession,
    task_message,
)
from benchmarking.files import Asset
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY, HarnessSpec
from benchmarking.tasks import load_task

IMAGE = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")

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

    from benchmarking.dataset import Dataset, process_manifest

    cases = [case for case in Dataset(PUBLIC_ROOT, {}).cases().values()
             if process_manifest(case) == manifest]
    assert cases, "A published process must have an executable witness"
    from benchmarking.engine.runtime import load_case

    runtime = load_case(cases[0], image=IMAGE)
    bundle = runtime.agent
    # Case metadata, rather than a process-wide wish list, owns runtime profiles.
    from benchmarking.engine.preparation import support_bindings

    backends = tomllib.loads(cases[0].read_text())["toolchain"]["backends"]
    required = {profile for name, backend in backends.items() for _, profile in support_bindings(name, backend)}
    assert {name.split("/")[1] for name, _ in bundle.files if name.startswith("support/")} == required
    assert not any("/verilog-a/" in name or "/compilation/" in name for name, _ in bundle.files)

    from benchmarking.files import ReadOnlyMount

    roots = {name: value for name, value in bundle.files if name.startswith("pdks/")}
    assert len(roots) == 1
    assert all(isinstance(value, ReadOnlyMount) and value.path.is_dir() for value in roots.values())
    assert all(not item.path.startswith("reference/") for item in runtime.task.inputs)
    resources = {**dict(bundle.files), "manifest.json": bundle.manifest}
    code = '''
info = json.loads(Path('/protocol/resources.json').read_text())
assert os.environ['ICLAYOUT_BENCH_PDK'] == info['pdk']
assert Path(os.environ['PDK_PATH']).is_dir()
assert not Path('/resources/tasks').exists()
assert not Path('/task/reference').exists()
assert not Path('/var/run/docker.sock').exists()
assert not Path('/resources/tasks').exists()
for source in Path('/resources/pdks').iterdir():
    try:
        (source / 'forbidden').write_text('must be read-only')
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
def test_process_feedback_is_opt_in_and_uses_a_frozen_snapshot(tmp_path):
    task = session_task()
    config = replace(configuration('''
output.write_bytes(b'feedback-candidate')
feedback = subprocess.run(['python', '-I', '/protocol/process_check.py'],
                          capture_output=True, text=True, check=True)
print(feedback.stdout, flush=True)
feedback = subprocess.run(['python', '-I', '/protocol/process_check.py'],
                          capture_output=True, text=True, check=True)
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
    assert seen == [(b"feedback-candidate", 1), (b"feedback-candidate", 2)]
    assert result.process_feedback[0]["accepted"] is True
    assert result.process_feedback[0]["candidate"]["sha256"] == Asset(b"feedback-candidate", "gds").sha256
    assert result.process_feedback[1]["outcome"] == "error"
    assert "synthetic feedback error" in result.process_feedback[1]["error"]
    assert recover_submissions(recorder.root)["candidate"] is None
    kinds = [json.loads(line)["kind"] for line in (recorder.root / "events.jsonl").read_text().splitlines()]
    assert kinds.count("process_feedback.request") == kinds.count("process_feedback.result") == 2


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
from benchmarking.engine.execution import run_session
from benchmarking.engine.session import DockerSession
from benchmarking.tasks import load_task
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
        command = subprocess.run([sys.executable, "-m", "benchmarking.engine.cli", "recover", str(run)], capture_output=True, check=True)
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
    monkeypatch.setattr("benchmarking.engine.session.MAX_CONSOLE_BYTES", 8192)
    task = session_task()
    config = configuration("print('x'*100000, flush=True); time.sleep(30)")
    recorder = RunRecorder(tmp_path / "run")
    result = DockerSession(config.image).run(task, config, {}, task_message(task, config), recorder=recorder)
    assert result.termination == "infrastructure_error"
    assert result.environment["console_limit_bytes"] == 8192
    journal = [json.loads(line) for line in (recorder.root / "events.jsonl").read_text().splitlines()]
    assert any(e["kind"] == "console.limit" for e in journal)
    assert journal[-1]["data"]["console_complete"] is False
