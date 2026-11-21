"""Experiment planning: CLI selections, case paths, recorded identities and reuse."""

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import threading
from contextlib import nullcontext
from datetime import datetime
from functools import partial
from pathlib import Path

import pytest
import tomli_w
from helpers.participant import (
    ServiceFixture,
    attempt_boundaries,
    case_run,
    host_probes,
    in_process,
    terminal_files,
    write_dataset,
)

from benchmarking.execution.leases import CaseLease
from benchmarking.files import read_file
from benchmarking.participants.batch.config import resolve
from benchmarking.participants.batch.runner import BatchBoundaries
from benchmarking.participants.cli import main
from benchmarking.participants.harnesses.contracts import ParticipantSelection

pytestmark = pytest.mark.unit


def recording(outcome='no_submission'):
    """A participant attempt that only writes an independent terminal result."""
    launches = []

    def solve(access, row, output, selection):
        launches.append(output)
        return terminal_files(output, outcome)

    return solve, launches


def test_environment_defaults_and_explicit_runner_overrides(tmp_path, monkeypatch):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture-model"\neffort="medium"\n'
                      'tasks=["library.cell"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    monkeypatch.setenv('ICLAYOUT_BENCH_ENDPOINT', 'https://example.invalid/evaluation')
    monkeypatch.setenv('ICLAYOUT_BENCH_IMAGE', 'tools:configured')
    monkeypatch.setenv('ICLAYOUT_BENCH_OUTPUT', 'results/from-env')
    dispatched = []

    def run_slot(options, row, selection, repetition, name, output, lease):
        dispatched.append((options, output))
        return {'state': 'finished'}

    # Native selection reads the configured CODEX_HOME; only dispatch is replaced.
    run_cli = partial(main, probes=host_probes(resolve=resolve), boundaries=BatchBoundaries(run_slot=run_slot))
    assert run_cli(['--config', str(config)]) == 0
    assert dispatched[-1][0].image == 'tools:configured'
    assert dispatched[-1][1] == tmp_path / 'results/from-env'
    assert run_cli(['--config', str(config), '--image', 'tools:explicit', '--output', 'results/explicit']) == 0
    assert dispatched[-1][0].image == 'tools:explicit'
    assert dispatched[-1][1] == tmp_path / 'results/explicit'
    monkeypatch.setenv('ICLAYOUT_BENCH_OUTPUT', '')
    assert run_cli(['--config', str(config)]) == 0
    assert dispatched[-1][1] == tmp_path / 'results/trial'
    first = dispatched[-1][0].case_paths['library.cell']
    assert Path(first).parent == Path('library.cell')
    datetime.strptime(Path(first).name, '%Y%m%d-%H%M%S-%f').astimezone()
    assert run_cli(['--config', str(config)]) == 0
    assert dispatched[-1][1] == tmp_path / 'results/trial'
    assert dispatched[-1][0].case_paths['library.cell'] != first
    with pytest.raises(SystemExit):
        run_cli(['--config', str(config), '--resume'])
    assert len(dispatched) == 4


def test_cli_case_selection_and_scale_overrides(tmp_path, capsys, monkeypatch):
    """A small invocation must not dispatch the rest of a saved batch."""
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    tasks = ['process.library.small', 'process.library.large', 'other.library.small']
    config = tmp_path / 'batch.toml'
    source = ('harness="codex"\nmodel="fixture-model"\neffort="medium"\n'
              f'tasks={json.dumps(tasks)}\nconcurrency=4\nrepetitions=3\n')
    config.write_text(source)
    base = ['--config', str(config), '--dry-run']
    assert main(base + ['--case', 'large', '--repetitions', '1', '--concurrency', '1']) == 0
    row, = json.loads(capsys.readouterr().out)
    assert row['tasks'] == [tasks[1]]
    assert row['repetitions'] == row['concurrency'] == 1
    assert main(base + ['--case', tasks[0], '--case', 'large', '--case', tasks[0]]) == 0
    row, = json.loads(capsys.readouterr().out)
    assert row['tasks'] == tasks[:2]
    assert main(base) == 0
    row, = json.loads(capsys.readouterr().out)
    assert row['tasks'] == tasks
    assert row['repetitions'] == 3 and row['concurrency'] == 4
    assert config.read_text() == source
    for flags, error in [(['--case', 'small'], 'Ambiguous case'),
                         (['--case', 'missing'], 'Unknown case'),
                         (['--repetitions', '0'], 'positive integer')]:
        with pytest.raises(SystemExit) as raised:
            main(base + flags)
        assert raised.value.code == 2
        assert error in capsys.readouterr().err


@pytest.mark.parametrize('repetitions', [1, 2])
def test_timestamped_results_and_explicit_case_reuse(tmp_path, monkeypatch, capsys, repetitions):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="gpt-6-astra"\neffort="medium"\n'
                      f'tasks=["library.cell", "other.cell"]\nconcurrency=1\nrepetitions={repetitions}\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    solve, launches = recording()
    run_cli = partial(main, probes=host_probes(harness_version=lambda _: ('1.2.3', 'codex-cli 1.2.3')),
                      boundaries=in_process(solve))
    args = ['--config', str(config), '--endpoint', 'http://localhost:1']
    assert run_cli(args) == 0
    root = tmp_path / 'results/trial'
    args += ['--output', str(root)]
    for task in ['library.cell', 'other.cell']:
        directory = case_run(root, task)
        for repetition in range(1, repetitions + 1):
            slot = directory if repetitions == 1 else directory / f'repetition-{repetition}'
            assert json.loads((slot / 'result.json').read_text())['summary']['task'] == task
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'library.cell', 'other.cell'}
    count = len(launches)
    directory = case_run(root, 'library.cell')
    with CaseLease(directory), pytest.raises(SystemExit):
        run_cli(args)
    assert len(launches) == count
    capsys.readouterr()
    assert run_cli(args) == 0
    assert len(launches) == count
    assert 'SKIP case=library.cell' in capsys.readouterr().out
    # A different benchmark version cannot silently reuse this case.
    manifest = directory / ('result.json' if repetitions == 1 else 'repetition-1/result.json')
    original_record = manifest.read_text()
    recorded = json.loads(original_record)
    assert 'inputs' not in recorded['identity']
    recorded['identity']['benchmark']['commit'] = 'different-release'
    manifest.write_text(json.dumps(recorded))
    with pytest.raises(SystemExit):
        run_cli(args)
    assert json.loads(manifest.read_text()) == recorded
    assert len(launches) == count
    manifest.write_text(original_record)
    slot = directory
    if repetitions > 1:
        slot /= 'repetition-1'
    summary_path = slot / 'result.json'
    original = summary_path.read_text()
    suspended = json.loads(original)
    suspended['state'] = 'suspended'
    suspended['identity']['benchmark']['commit'] = 'different-release'
    summary_path.write_text(json.dumps(suspended))
    for flags in ([], ['--resume']):
        with pytest.raises(SystemExit):
            run_cli(args + flags)
    assert len(launches) == count
    summary_path.write_text(original)
    config.write_text(config.read_text().replace('repetitions='+str(repetitions), 'repetitions='+str(repetitions + 1)))
    with pytest.raises(SystemExit):
        run_cli(args)
    assert len(launches) == count


def test_updated_profile_prices_apply_to_new_runs_and_preserve_resumed_run_prices(tmp_path, monkeypatch):
    prices = tmp_path / 'pricing.toml'
    original = {'currency': 'USD', 'source': 'https://provider.example/pricing', 'as_of': '2026-10-16',
                'input_per_million': 2, 'cache_read_per_million': .2,
                'cache_write_per_million': 2.5, 'output_per_million': 10}
    prices.write_text(tomli_w.dumps({'models': {'fixture': original}}))
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["interrupted", "finished"]\nconcurrency=1\nrepetitions=2\n'
                      'pricing_file="pricing.toml"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture-token')
    observed = []

    def run(access, row, output, selection):
        observed.append(copy.deepcopy(row['pricing']))
        if len(observed) == 1:
            raise RuntimeError('synthetic interruption')
        return terminal_files(output)

    run_cli = partial(main, probes=host_probes(), boundaries=in_process(run))
    arguments = ['--config', str(config), '--endpoint', 'https://fixture']
    reuse = arguments + ['--output', str(tmp_path / 'retained')]
    assert run_cli(reuse) == 1
    finished = case_run(tmp_path / 'retained', 'finished') / 'repetition-1/result.json'
    retained = finished.read_bytes()
    updated = dict(original, input_per_million=4, output_per_million=20)
    prices.write_text(tomli_w.dumps({'models': {'fixture': updated}}))
    assert run_cli(reuse + ['--resume']) == 0
    assert observed == [original] * 5
    assert finished.read_bytes() == retained
    assert run_cli(reuse) == 0  # Completed runs continue to use their recorded prices.
    assert observed == [original] * 5
    assert run_cli(arguments) == 0
    assert observed[5:] == [updated] * 4
    for result in (tmp_path / 'results').rglob('result.json'):
        assert json.loads(result.read_text())['identity']['plan'][0]['pricing'] == updated
    config.write_text(config.read_text().replace('effort="medium"', 'effort="low"'))
    with pytest.raises(SystemExit):
        run_cli(reuse + ['--resume'])
    assert len(observed) == 9


def test_new_runs_preserve_task_history_and_reuse_only_the_latest(tmp_path, monkeypatch, capsys):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                      'tasks=["library.cell"]\nconcurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    outcomes = iter(['pass', 'fail'])
    calls = []

    def run(access, row, output, selection):
        calls.append(output)
        return terminal_files(output, next(outcomes))

    run_cli = partial(main, probes=host_probes(), boundaries=in_process(run))
    args = ['--config', str(config), '--endpoint', 'https://fixture']
    root = tmp_path / 'results/trial'
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'fixture')
    assert run_cli(args) == 0
    first = case_run(root, 'library.cell')
    original = {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}
    archived = root / '.batches/previous'
    archived.mkdir(parents=True)
    (archived / 'result.json').write_bytes((first / 'result.json').read_bytes())
    assert run_cli(args) == 0
    history = sorted((root / 'library.cell').iterdir())
    assert len(history) == 2 and history[0] == first
    for directory in history:
        datetime.strptime(directory.name, '%Y%m%d-%H%M%S-%f').astimezone()
    latest = history[-1]
    assert json.loads((latest / 'result.json').read_text())['evaluation']['outcome'] == 'fail'
    capsys.readouterr()
    explicit = args + ['--output', str(root)]
    assert run_cli(explicit) == 0
    assert str(latest / 'result.json') in capsys.readouterr().out
    assert len(calls) == 2
    assert run_cli(['--status', '--output', str(root)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert {r['directory'] for r in status['cases']} == {str(p.relative_to(root)) for p in history}
    record = json.loads((latest / 'result.json').read_text())
    record['identity']['benchmark']['commit'] = 'changed'
    (latest / 'result.json').write_text(json.dumps(record))
    with pytest.raises(SystemExit):
        run_cli(explicit + ['--resume'])
    (latest / 'result.json').unlink()
    with pytest.raises(SystemExit):
        run_cli(explicit + ['--resume'])
    assert len(calls) == 2
    assert original == {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}


def test_local_dataset_continuation_compares_content_not_enclosing_commits(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(['git', '-C', str(workspace), '-c', 'user.name=Synthetic', '-c',
                        'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', *args],
                       check=True, capture_output=True)

    workspace = tmp_path / 'workspace'
    dataset = write_dataset(workspace / 'dataset', ['case'])
    resource = dataset / 'tasks/case/resources/smoke.py'
    resource.parent.mkdir()
    resource.write_text('print("smoke")\n')
    (dataset / 'tasks/case/pdk.toml').write_text(
        'id="fixture"\n[agent.local_files."checks/smoke.py"]\npath="resources/smoke.py"\n')
    git('init', '-q')
    git('add', '.')
    git('commit', '-qm', 'Workspace with a Dataset export')
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\ntasks=["case"]\n'
                      'concurrency=1\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    calls = []
    def run(access, row, output, selection):
        calls.append(row['task'])
        return terminal_files(output, 'pass')
    local = attempt_boundaries(local_service=lambda *args: nullcontext(None))
    run_cli = partial(main, probes=host_probes(harness_version=lambda _: ('1.2.3', 'codex-cli 1.2.3')),
                      boundaries=in_process(run, attempt=local))
    root = tmp_path / 'results/trial'
    args = ['--config', str(config), '--dataset', str(dataset), '--output', str(root)]
    assert run_cli(args) == 0
    recorded = json.loads((case_run(root, 'case') / 'result.json').read_text())['identity']
    assert recorded['inputs']['case']['dataset']['commit'] is None
    assert recorded['inputs']['case']['pdk_files_sha256'] == {
        'resources/smoke.py': hashlib.sha256(resource.read_bytes()).hexdigest()}
    (workspace / 'notes.md').write_text('unrelated\n')
    git('add', 'notes.md')
    git('commit', '-qm', 'Unrelated workspace change')
    assert run_cli(args) == 0
    resource.write_text('print("changed")\n')
    with pytest.raises(SystemExit):
        run_cli(args)
    assert calls == ['case']


def test_append_cases_skips_original_and_runs_new_cases_concurrently(tmp_path, monkeypatch, capsys):
    """Public behavior: grow a completed plan, without touching its original evidence."""
    config = tmp_path / 'trial.toml'
    def configure(tasks, concurrency):
        config.write_text('harness="codex"\nmodel="fixture"\neffort="medium"\n'
                          f'tasks={json.dumps(tasks)}\nconcurrency={concurrency}\nrepetitions=1\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    dataset = write_dataset(tmp_path / 'dataset', ['old', 'new-a', 'new-b'])
    barrier = threading.Barrier(2)
    calls = []
    def run(access, row, output, selection):
        calls.append(row['task'])
        if row['task'] != 'old':
            barrier.wait(timeout=5)  # Cannot pass if the two new sessions are serialized.
        return terminal_files(output, 'pass')
    probes = host_probes(harness_version=lambda _: ('1.2.3', 'codex-cli 1.2.3'))
    boundaries = in_process(run, attempt=attempt_boundaries(local_service=lambda *args: nullcontext(None)))
    run_cli = partial(main, probes=probes, boundaries=boundaries)
    configure(['old'], 1)
    args = ['--config', str(config), '--dataset', str(dataset)]
    assert run_cli(args) == 0
    root = tmp_path / 'results/trial'
    args += ['--output', str(root)]
    old = case_run(root, 'old')
    original = {str(p.relative_to(old)): p.read_bytes() for p in old.rglob('*') if p.is_file()}
    manifest = (old / 'result.json').read_bytes()
    configure(['old', 'new-a', 'new-b'], 2)
    capsys.readouterr()
    assert run_cli(args) == 0
    printed = capsys.readouterr().out
    assert 'SKIP case=old ' in printed
    assert str(old / 'result.json') in printed
    assert sorted(calls) == ['new-a', 'new-b', 'old']
    assert original == {str(p.relative_to(old)): p.read_bytes() for p in old.rglob('*') if p.is_file()}
    assert (old / 'result.json').read_bytes() == manifest
    assert {p.name for p in root.iterdir() if not p.name.startswith(".")} == {'old', 'new-a', 'new-b'}
    assert run_cli(args) == 0
    assert len(calls) == 3
    relocated = tmp_path / 'relocated'
    copied_root = relocated / 'results' / root.name
    copied = copied_root / old.relative_to(root)
    shutil.copytree(old, copied)
    configure(['old'], 1)
    monkeypatch.chdir(relocated)
    relocated_args = args[:-2] + ['--output', str(copied_root)]
    assert run_cli(relocated_args) == 0
    assert len(calls) == 3
    assert {p.name for p in copied.parent.iterdir()} == {old.name}
    monkeypatch.chdir(tmp_path)
    configure(['old', 'new-a', 'new-b'], 2)
    # Inputs are version-owned: changing the benchmark release rejects all dispatch.
    different_release = host_probes(harness_version=probes.harness_version,
                                    package_version=lambda: {"version": "different", "commit": None})
    with pytest.raises(SystemExit):
        run_cli(args, probes=different_release, boundaries=boundaries)
    assert len(calls) == 3


@pytest.mark.parametrize('resource_binding', [False, True])
def test_batch_resume_rejects_changed_dataset_input(tmp_path, monkeypatch, resource_binding):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=1\n')
    dataset = write_dataset(tmp_path / 'dataset', ['test'])
    asset = dataset / ('tasks/test/pdk.toml' if resource_binding else 'tasks/test/fixture/cases/test/input.spice')
    monkeypatch.delenv('ICLAYOUT_BENCH_ENDPOINT', raising=False)
    solve, launches = recording()
    local = attempt_boundaries(local_service=lambda *args: nullcontext(ServiceFixture()))
    run_cli = partial(main, probes=host_probes(), boundaries=in_process(solve, attempt=local))
    args = ['--config', str(config), '--dataset', str(dataset), '--output', str(tmp_path / 'batch')]
    assert run_cli(args) == 0
    asset.write_text('different input')
    with pytest.raises(SystemExit):
        run_cli(args + ['--resume'])
    assert len(launches) == 1


def test_batch_resume_skips_completed_and_rejects_config_change(tmp_path, monkeypatch):
    config = tmp_path / 'trial.toml'
    config.write_text('harness="codex"\nmodel="fixture"\neffort="high"\ntasks=["test"]\nconcurrency=1\nrepetitions=2\n')
    monkeypatch.setenv('ICLAYOUT_BENCH_TOKEN', 'secret')
    calls = []
    def run(*args):
        calls.append(args)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return terminal_files(args[2]) | {'state': 'finished', 'harness_error': None}
    run_cli = partial(main, probes=host_probes(ParticipantSelection({'harness': 'codex', 'model': 'fixture'}, {}, {})),
                      boundaries=in_process(run))
    args = ['--config', str(config), '--endpoint', 'http://localhost:1', '--output', str(tmp_path / 'batch')]
    with pytest.raises(KeyboardInterrupt):
        run_cli(args)
    assert run_cli(args + ['--resume']) == 0
    assert len(calls) == 3
    assert run_cli(args + ['--resume']) == 0
    assert len(calls) == 3
    config.write_text(config.read_text().replace('effort="high"', 'effort="low"'))
    with pytest.raises(SystemExit):
        run_cli(args + ['--resume'])
    assert len(calls) == 3


def test_remote_rejects_local_budget_override():
    with pytest.raises(SystemExit) as raised:
        main(['--harness', 'codex', '--model', 'fixture', '--seconds', '60', '--dry-run'])
    assert raised.value.code == 2


@pytest.mark.parametrize('local', [False, True], ids=['remote', 'local'])
def test_default_batch_groups_local_and_remote_outputs_per_run(tmp_path, monkeypatch, local):
    participant_code = ('import os, pathlib\n'
                        'root = pathlib.Path(os.environ["ICLAYOUT_BENCH_TOOL_ARTIFACTS"])\n'
                        '(root / "fixture").mkdir(parents=True, exist_ok=True)\n'
                        '(root / "fixture/checkpoint.bin").write_bytes(b"native checkpoint" * 1000)\n'
                        'print("done")\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ICLAYOUT_BENCH_ENDPOINT', '')
    batch = tmp_path / 'results/trial'
    write_dataset(tmp_path, ["fixture"])
    config = tmp_path / 'trial.toml'
    config.write_text('harness="claude-code"\nmodel="fixture-model"\ntasks=["fixture"]\nconcurrency=1\neffort="high"\nrepetitions=1\n')
    fixture = ServiceFixture()
    fixture.remaining = 3 * 3600
    selected = ParticipantSelection({'harness': 'claude-code', 'model': 'fixture-model',
                                     'effort_resolved': 'high', 'effort_requested': None}, {}, {})

    def local_service(prepared, output, image, recoverable):
        assert output == case_run(batch, 'fixture') / '.runtime/service'
        (output / 'service.log').write_text('fixture service')
        return nullcontext(fixture)

    attempt = attempt_boundaries(fixture, local_service=local_service,
                                 native_command=lambda context: [sys.executable, '-c', participant_code])
    mode = ['--dataset', str(tmp_path)] if local else ['--endpoint', fixture.endpoint]
    assert main(['--config', str(config), *mode], probes=host_probes(selected),
                boundaries=in_process(attempt=attempt)) == 0
    case_path = str(case_run(batch, 'fixture').relative_to(batch))
    result = json.loads((batch / case_path / 'result.json').read_text())
    assert result['summary']['directory'] == case_path
    assert result['evaluation']['outcome'] == 'no_submission'
    assert (batch / case_path / 'agent.jsonl').exists()
    assert not (batch / case_path / '.runtime').exists()
    artifact = 'tool-artifacts/fixture/checkpoint.bin'
    assert artifact in result['files']
    assert read_file(batch / case_path, artifact) == b'native checkpoint' * 1000
    assert (batch / case_path / artifact).is_file()
    assert not (batch / 'fixture-local').exists()
