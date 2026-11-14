"""Cleanup must tolerate a removed container and retain daemon failures."""

import json
import re
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


def test_failed_named_creation_cleanup_checks_the_exact_name(monkeypatch):
    from benchmarking.execution.tools.cleanup import remove_container

    def run(command, **kwargs):
        if command[:3] == ['docker', 'rm', '-f']:
            return subprocess.CompletedProcess(command, 1, b'', b'daemon failure')
        pattern = command[-1].removeprefix('name=')
        assert re.fullmatch(pattern, '/iclayout-owned')
        assert not re.fullmatch(pattern, '/iclayout-owned-other')
        return subprocess.CompletedProcess(command, 0, b'present\n', b'')

    monkeypatch.setattr(subprocess, 'run', run)
    assert remove_container('iclayout-owned')['state'] == 'error'


def test_competing_removal_is_retried_within_the_cleanup_deadline(monkeypatch):
    from benchmarking.execution.tools.cleanup import remove_container

    calls = []

    def run(command, **kwargs):
        if command[:3] == ['docker', 'rm', '-f']:
            calls.append(command[-1])
            return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0, b'',
                                               b'removal of container is already in progress')
        return subprocess.CompletedProcess(command, 0, b'present\n', b'')

    monkeypatch.setattr(subprocess, 'run', run)
    result = remove_container('a' * 64)
    assert result['state'] == 'removed'
    assert calls == ['a' * 64, 'a' * 64]


@pytest.mark.parametrize('apply', [False, True])
def test_explicit_cleanup_never_selects_other_containers(monkeypatch, apply):
    from benchmarking.execution.tools.cleanup import cleanup_containers

    target, other = 'a' * 64, 'b' * 64
    removed = []

    def output(command, **kwargs):
        if command[:3] == ['docker', 'ps', '-aq']:
            assert command[-1] == 'id=' + target[:12]
            return target + '\n'
        assert command == ['docker', 'inspect', target]
        return json.dumps([{'Id': target, 'Name': '/selected', 'Image': 'image',
                            'State': {'Status': 'running'}}])

    def run(command, **kwargs):
        assert command == ['docker', 'rm', '-f', target]
        removed.append(command[-1])
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(subprocess, 'check_output', output)
    monkeypatch.setattr(subprocess, 'run', run)
    records = cleanup_containers([target[:12]], apply=apply)
    assert records[0]['id'] == target
    assert records[0]['state'] == ('removed' if apply else 'selected')
    assert removed == ([target] if apply else [])
    assert other not in removed


@pytest.mark.parametrize('matches', ['', 'a' * 64 + '\n' + 'b' * 64])
def test_cleanup_absence_or_ambiguity_never_removes_a_container(monkeypatch, matches):
    from benchmarking.execution.tools.cleanup import cleanup_containers

    monkeypatch.setattr(subprocess, 'check_output', lambda *a, **kw: matches)
    if matches:
        with pytest.raises(ValueError, match='Ambiguous'):
            cleanup_containers(['a' * 12], apply=True)
    else:
        assert cleanup_containers(['a' * 12], apply=True) == [{'id': 'a' * 12, 'state': 'absent'}]
