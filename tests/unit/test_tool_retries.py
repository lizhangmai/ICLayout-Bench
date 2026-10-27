"""Infrastructure recovery replays frozen EDA inputs, never candidate failures."""

import json
import sys
import time
from threading import Event

import pytest

from benchmarking.eda.environment import ExternalRuntime
from benchmarking.execution.tools.budget import tool_cancellation, tool_deadline
from benchmarking.execution.tools.native import NativeTool
from benchmarking.files import Asset

pytestmark = pytest.mark.unit

PVS_CRASH = 'CleanupERROR: Process 123 terminated unexpectedly, signal num: 11. Exiting.'
BUSY_LICENSE = ('ERROR (ELI-00111) Failed to check out license.\n'
                'FLEXnet Licensing error:-4,132. Licensed number of users already reached.')
MISSING_LICENSE = ('ERROR (LMF-02005): License call failed for feature CICNG_129, version 1.000 and quantity 1.\n'
                   'FLEXnet ERROR(-5, 0, 0): No such feature exists.\n'
                   "ERROR (ELI-00111) Failed to check out license 'CICNG_129'.")


def native_tool():
    return NativeTool(ExternalRuntime('fixture', {'image': 'unused', 'environment': {}, 'mounts': []}))


def command(marker, diagnostic, *, recover=True):
    script = f'''import sys
from pathlib import Path
marker=Path({str(marker)!r})
count=int(marker.read_text())+1 if marker.exists() else 1
marker.write_text(str(count))
assert Path('input.gds').read_bytes()==b'frozen input'
assert not Path('output.gds').exists()
if count==1 or not {recover!r}:
    Path('output.gds').write_bytes(b'partial failed output')
    print({diagnostic!r},flush=True)
    raise SystemExit(1)
Path('output.gds').write_bytes(Path('input.gds').read_bytes())
print('tool completed normally',flush=True)
'''
    return [sys.executable, '-c', script]


@pytest.mark.parametrize('diagnostic', [PVS_CRASH, BUSY_LICENSE, MISSING_LICENSE])
def test_native_recovers_known_infrastructure_failure_with_fresh_frozen_inputs(tmp_path, diagnostic):
    marker = tmp_path / 'attempt-count'
    result = native_tool().run(command(marker, diagnostic), {'input.gds': Asset(b'frozen input', 'gds')},
                               {'output.gds': 'gds'})
    assert result.returncode == 0 and not result.reason
    assert marker.read_text() == '2'
    assert result.files['output.gds'].content == b'frozen input'
    assert result.evidence['tool-attempts/1/outputs/output.gds'].content == b'partial failed output'
    assert diagnostic.encode() in result.evidence['tool-attempts/1/evidence/console'].content
    attempts = json.loads(result.evidence['tool-attempts.json'].content)
    assert [a['returncode'] for a in attempts['attempts']] == [1, 0]


@pytest.mark.parametrize('diagnostic', [MISSING_LICENSE+'\nFeature has expired',
                                      MISSING_LICENSE+'\nInvalid license file', 'Run Result : MISMATCH',
                                      'Invalid source netlist', 'Too few complete waveform cycles'])
def test_native_does_not_retry_permanent_or_candidate_failures(tmp_path, diagnostic):
    marker = tmp_path / 'attempt-count'
    result = native_tool().run(command(marker, diagnostic, recover=False),
                               {'input.gds': Asset(b'frozen input', 'gds')}, {'output.gds': 'gds'})
    assert result.returncode == 1
    assert marker.read_text() == '1'
    assert 'tool-attempts.json' not in result.evidence


@pytest.mark.parametrize(('diagnostic', 'failure_code'), [
    (PVS_CRASH, 'native_crash'), (MISSING_LICENSE, 'license_checkout_failed')])
def test_native_stops_retrying_persistent_infrastructure_failure_and_keeps_all_failures(
        tmp_path, diagnostic, failure_code):
    tool = native_tool()
    marker = tmp_path / 'attempt-count'
    result = tool.run(command(marker, diagnostic, recover=False),
                      {'input.gds': Asset(b'frozen input', 'gds')}, {'output.gds': 'gds'})
    assert result.returncode == 1 and result.reason
    expected = tool.identity['retry_policy']['max_attempts']
    assert int(marker.read_text()) == expected
    attempts = json.loads(result.evidence['tool-attempts.json'].content)
    assert len(attempts['attempts']) == expected
    assert attempts['termination'] == 'exhausted'
    assert all(a['failure']['code'] == failure_code for a in attempts['attempts'])


def test_native_retry_wait_obeys_existing_deadline(tmp_path):
    marker = tmp_path / 'attempt-count'
    with tool_deadline(time.monotonic()+.3):
        result = native_tool().run(command(marker, PVS_CRASH), {'input.gds': Asset(b'frozen input', 'gds')},
                                   {'output.gds': 'gds'})
    assert marker.read_text() == '1'
    assert result.returncode is None and not result.files
    attempts = json.loads(result.evidence['tool-attempts.json'].content)
    assert attempts['termination'] == 'deadline'


def test_native_retry_wait_honors_cancellation(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    import benchmarking.execution.tools as shared

    marker = tmp_path / 'attempt-count'
    cancelled, waiting = Event(), Event()
    original = shared.wait_for_retry
    def wait(seconds):
        if seconds > 0:
            waiting.set()
        return original(seconds)
    monkeypatch.setattr(shared, 'wait_for_retry', wait)
    def run():
        with tool_cancellation(cancelled):
            return native_tool().run(command(marker, PVS_CRASH), {'input.gds': Asset(b'frozen input', 'gds')},
                                      {'output.gds': 'gds'})

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(run)
        assert waiting.wait(5)
        cancelled.set()
        result = pending.result(timeout=2)
    assert marker.read_text() == '1'
    assert result.returncode is None and not result.files
    attempts = json.loads(result.evidence['tool-attempts.json'].content)
    assert attempts['termination'] == 'cancelled'


def test_positive_exit_139_does_not_trigger_crash_recovery(tmp_path):
    marker = tmp_path / 'attempt-count'
    argv = command(marker, 'ordinary tool error', recover=False)
    argv[-1] = argv[-1].replace('raise SystemExit(1)', 'raise SystemExit(139)')
    result = native_tool().run(argv, {'input.gds': Asset(b'frozen input', 'gds')}, {'output.gds': 'gds'})
    assert result.returncode == 139
    assert marker.read_text() == '1'
    assert 'tool-attempts.json' not in result.evidence


def test_failed_native_driver_does_not_leave_workers_alive_for_retry(tmp_path):
    from benchmarking.execution.process import process_start

    marker, worker = tmp_path / 'attempt-count', tmp_path / 'worker-pid'
    argv = command(marker, PVS_CRASH)
    spawn = ('import subprocess\n'
             'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])\n'
             f'Path({str(worker)!r}).write_text(str(p.pid))\n')
    argv[-1] = argv[-1].replace("    Path('output.gds').write_bytes(b'partial failed output')",
                              '\n'.join('    '+line for line in spawn.splitlines()) +
                              "\n    Path('output.gds').write_bytes(b'partial failed output')")
    result = native_tool().run(argv, {'input.gds': Asset(b'frozen input', 'gds')}, {'output.gds': 'gds'})
    assert result.returncode == 0
    assert process_start(int(worker.read_text())) is None


@pytest.mark.parametrize('stop', ['cancelled', 'deadline'])
def test_stopped_owner_cannot_launch_an_initial_attempt(tmp_path, stop):
    cancelled = Event()
    if stop == 'cancelled':
        cancelled.set()
    marker = tmp_path / 'attempt-count'
    with tool_cancellation(cancelled), tool_deadline(time.monotonic()-1 if stop == 'deadline' else None):
        result = native_tool().run(command(marker, PVS_CRASH), {'input.gds': Asset(b'frozen input', 'gds')},
                                   {'output.gds': 'gds'})
    assert not marker.exists()
    assert result.returncode is None and not result.files
    metadata = json.loads(result.evidence['tool-attempts.json'].content)
    assert metadata['attempts'] == [] and metadata['termination'] == stop
