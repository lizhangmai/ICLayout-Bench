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


@pytest.mark.parametrize('persistent', [False, True])
def test_interrupted_removal_retries_only_the_owned_container(monkeypatch, persistent):
    from benchmarking.execution.tools.cleanup import remove_container

    removals = []

    def run(command, **kwargs):
        if command[:3] == ['docker', 'rm', '-f']:
            removals.append(command[-1])
            return subprocess.CompletedProcess(command, 130 if persistent or len(removals) == 1 else 0, b'', b'')
        return subprocess.CompletedProcess(command, 0, b'container\n', b'')

    monkeypatch.setattr(subprocess, 'run', run)
    result = remove_container('container')
    assert result['state'] == ('error' if persistent else 'removed')
    assert result['attempts'][0]['remove_exit_code'] == 130
    assert removals == ['container', 'container']


def test_interrupted_removal_does_not_renew_cleanup_budget(monkeypatch):
    from types import SimpleNamespace

    from benchmarking.execution.tools.cleanup import remove_container

    clock, removals = [0], []
    monkeypatch.setattr('benchmarking.execution.tools.cleanup.time', SimpleNamespace(monotonic=lambda: clock[0]))

    def run(command, **kwargs):
        if command[:3] == ['docker', 'rm', '-f']:
            removals.append(command[-1])
            clock[0] += kwargs['timeout']
            return subprocess.CompletedProcess(command, 130, b'', b'')
        return subprocess.CompletedProcess(command, 0, b'container\n', b'')

    monkeypatch.setattr(subprocess, 'run', run)
    assert remove_container('container')['state'] == 'error'
    assert removals == ['container']
