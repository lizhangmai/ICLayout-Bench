"""Cleanup must tolerate a removed container and retain daemon failures."""

import subprocess

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('present', [False, True])
def test_failed_remove_checks_absence_before_reporting_cleanup_failure(monkeypatch, present):
    from benchmarking.execution.tools.cleanup import remove_container

    def run(command, **kwargs):
        if command[:3] == ['docker', 'rm', '-f']:
            return subprocess.CompletedProcess(command, 1, b'', b'removal race')
        return subprocess.CompletedProcess(command, 0, b'container\n' if present else b'', b'')
    monkeypatch.setattr(subprocess, 'run', run)
    result = remove_container('container')
    assert result['state'] == ('error' if present else 'absent')
    assert result['remove_exit_code'] == 1
    assert result['stderr'] == 'removal race'


def test_cleanup_timeout_is_diagnostic_instead_of_replacing_primary_exception(monkeypatch):
    from benchmarking.execution.tools.cleanup import remove_container

    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired('docker', 30)
    monkeypatch.setattr(subprocess, 'run', run)
    assert remove_container('container')['error_type'] == 'TimeoutExpired'
