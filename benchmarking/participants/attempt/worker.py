"""Commit a case's terminal export before releasing its private runtime evidence."""

import json
import os
import shutil
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from pathlib import Path

from benchmarking.client import Client, ClientError
from benchmarking.execution.leases import BatchLease
from benchmarking.files import write_json as save
from benchmarking.participants.attempt import runner
from benchmarking.participants.attempt import service as local_service
from benchmarking.participants.attempt.evidence import (
    read_attempt_evidence,
    read_participant_evidence,
)
from benchmarking.participants.attempt.recovery import classify, policy
from benchmarking.participants.attempt.state import ParticipantAttempt
from benchmarking.participants.attempt.storage import (
    CaseLease,
    CaseRecord,
    case_lease_root,
)
from benchmarking.participants.harnesses.contracts import ParticipantSelection
from benchmarking.participants.harnesses.scheme import check as check_scheme
from benchmarking.results.outbox import archive_result
from benchmarking.results.package import (
    compact_result,
    export_attempts,
    export_run,
    load,
    put,
    verify,
)
from benchmarking.results.preview import ensure_layout_preview
from benchmarking.results.usage import combine_usage


def finish_case(root, *, output=None, results_data=None, schedule=None):
    """Caller owns the case lease. Commit verified outputs before removing runtime state."""
    record = CaseRecord(root)
    state = record.read()
    if record.terminal_summary() is None:
        raise ValueError('Cannot finalize an unfinished case')
    if not state['identity'].get('endpoint') and record.service.exists():
        local_service.stop_local_service(record.service)
    if state['state'] == 'finished':
        ensure_layout_preview(record.root)
    summary = _finish_case(record, state)
    from benchmarking.results.retention import compact

    selected_pool = next((row['archive_objects'] for row in schedule or [] if row.get('archive_objects')), None)
    compact(record.root, objects=selected_pool or (Path(output) / '.objects' if output is not None else None))
    # Derived previews and archive indexing can be retried without a solve.
    if output is not None:
        archive_result(results_data, output, str(record.root.relative_to(output)), schedule or state['identity']['plan'])
    return summary


def _finish_case(record, state):
    root, runtime = record.root, record.runtime
    if state.get('state') == 'finished':
        if state.get('format') != 'participant-result':
            raise ValueError('Unsupported participant result format')
        verify(root, state)
        if runtime.exists():
            with ExitStack() as stack:
                for store in sorted(runtime.rglob('service-store')):
                    stack.enter_context(BatchLease(store))
                shutil.rmtree(runtime)
        return state['summary']
    summary = record.terminal_summary()
    if summary is None:
        raise ValueError('Cannot finalize an unfinished case')
    # Do not delete stores still owned by a live service, including abandoned attempts.
    with ExitStack() as stack:
        for store in sorted(runtime.rglob('service-store')):
            stack.enter_context(BatchLease(store))
        result = {'format': 'participant-result', 'identity': state['identity'], 'state': 'finalizing',
                  'summary': dict(summary, result='result.json'), 'files': []}
        files = result['files']
        export_run(root, read_participant_evidence(runtime), result)
        for path in sorted((root / 'tool-artifacts').rglob('*')):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError('Tool artifacts must be regular files: ' + str(path))
            if path.is_file():
                files.append(path.relative_to(root).as_posix())
        # These journals contain fixed lifecycle/HTTP fields, never credentials
        # or request bodies. Keep them before removing private runtime stores.
        journals = [('worker-events.jsonl', 'worker-events.jsonl'),
                    ('service/service-store/http.jsonl', 'service-http.jsonl'),
                    ('service/service-store/lifecycle.jsonl', 'service-lifecycle.jsonl'),
                    ('service/lifecycle.jsonl', 'service-launch.jsonl')]
        for source, target in journals:
            path = runtime / source
            if path.is_file():
                put(root, target, path.read_bytes(), files)
        for attempt in sorted((runtime / 'attempts').glob('*')):
            for source, target in journals:
                path = attempt / source
                if path.is_file():
                    put(root, f'attempts/{attempt.name}/{target}', path.read_bytes(), files)
        result['prior_plans'] = [load(p) for p in sorted((runtime / 'plans').glob('*/record.json'))]
        attempts = [read_attempt_evidence(path) for path in sorted((runtime / "attempts").glob('*')) if path.is_dir()]
        result["attempts"] = export_attempts(root, attempts, files)
        if attempts and (result.get("model_usage") is not None
                         or any(a.metadata.get("model_usage") is not None for a in attempts)):
            result["model_usage"] = combine_usage([a.metadata.get("model_usage") for a in attempts]
                                                   + [result.get("model_usage")])
        result = _commit_terminal(root, result)
        shutil.rmtree(runtime)
    return result['summary']

def _commit_terminal(root, result):
    result = compact_result(result)
    save(root / 'result.json', result)
    ensure_layout_preview(root)
    result = load(root / 'result.json')
    if ((root / 'layout.png').exists() and result.get('image', {}).get('status') == 'complete'
            and 'layout.png' not in result['files']):
        result['files'].append('layout.png')
    verify(root, result)
    result['state'] = 'finished'
    save(root / 'result.json', result)
    return result


@dataclass(frozen=True)
class SlotRequest:
    endpoint: str | None
    image: str
    token_env: str
    cases: dict
    results_data: Path | None


@dataclass(frozen=True)
class CollectRequest:
    output: Path
    cases: list[str] | None = None
    results_data: Path | None = None


def execute_owned_slot(request: SlotRequest, row, selection, repetition, name, output, lease):
    check_scheme(row.get("scheme", {}))
    record = CaseRecord(output / name)
    run_dir = record.runtime
    if record.terminal_summary() is not None:
        return finish_case(record.root, output=output, results_data=request.results_data, schedule=[row])
    record.begin()
    settings = policy(row.get("recovery"), harness=row["harness"])
    service_dir = run_dir / "service"
    if not request.endpoint:
        service_dir.mkdir(mode=0o700, exist_ok=True)
        arguments = (request.cases[row["task"]], service_dir, row.get("scheme", {}).get("solver_image", request.image))
        context = local_service.service(*arguments, settings['resume_session'])
    else:
        context = nullcontext(Client(request.endpoint, os.environ.get(request.token_env, ""), timeout=60,
                                     retry_policy=settings))
    interrupted = False
    try:
        artifacts = record.root / 'tool-artifacts'
        artifacts.mkdir(mode=0o700, exist_ok=True)
        selection = selection.with_environment(ICLAYOUT_BENCH_LEASE_FD=str(lease.fileno()),
                                               ICLAYOUT_BENCH_TOOL_ARTIFACTS=str(artifacts.resolve()))
        with context as access:
            summary = runner.run_one(access, row, run_dir / "participant", selection)
        summary["repetition"] = repetition
        if "result" in summary:
            summary["result"] = str(Path("participant") / summary["result"])
    except (OSError, ValueError, RuntimeError, TimeoutError, ClientError, KeyboardInterrupt) as error:
        interrupted = isinstance(error, KeyboardInterrupt)
        summary = {"name": row["name"], "repetition": repetition, **selection.condition,
                   "harness_error": type(error).__name__, "failure": classify(error),
                   "state": "suspended", "outcome": None, "score": None}
        launch_path = run_dir / "participant/harness-summary.json"
        launch = json.loads(launch_path.read_text()) if launch_path.exists() else {}
        if "finalization_error" in launch:
            summary["finalization_error"] = launch["finalization_error"]
            if launch.get("error"):
                summary.update(harness_error=launch["error"], failure=launch.get("failure"))
    summary.setdefault("state", "finished")
    summary["directory"] = name
    summary["task"] = row["task"]
    record.record_summary(summary)
    if interrupted:
        raise KeyboardInterrupt
    if summary["state"] == "finished":
        return finish_case(record.root, output=output, results_data=request.results_data, schedule=[row])
    return summary


def collect_batch(request: CollectRequest):
    """Recover terminal exports/accepted candidates, keeping their original identity."""
    output = request.output.resolve()
    records = [(record.root, record.read()) for record in CaseRecord.discover(output)]
    if not records:
        raise ValueError("No recorded cases at --output")
    if request.cases:
        chosen = set()
        for name in request.cases:
            matches = [i for i, (_, record) in enumerate(records)
                       if name in {record["identity"]["plan"][0]["tasks"][0],
                                   record["identity"]["plan"][0]["tasks"][0].rsplit(".", 1)[-1]}]
            tasks = {records[i][1]["identity"]["plan"][0]["tasks"][0] for i in matches}
            if len(tasks) != 1:
                raise ValueError("Unknown or ambiguous recorded case: " + name)
            chosen.update(matches)
        records = [value for i, value in enumerate(records) if i in chosen]
    summaries = []
    with ExitStack() as stack:
        # All repetition workers share the task's case lease. Acquire each root
        # once before any mutation; a collector must not race an active owner.
        lease_roots = {
            case_lease_root(directory, record["identity"]["plan"][0]["repetitions"])
            for directory, record in records
        }
        for lease_root in sorted(lease_roots):
            stack.enter_context(CaseLease(lease_root))
        for directory, record in records:
            stored = CaseRecord(directory)
            if stored.terminal_summary() is not None:
                summary = finish_case(directory, output=output, results_data=request.results_data)
                summaries.append(summary)
                print(json.dumps(summary, ensure_ascii=False), flush=True)
                continue
            participant = stored.participant
            if not ParticipantAttempt.exists(participant):
                print(f"SKIP unstarted case={directory.relative_to(output)}", flush=True)
                continue
            attempt = ParticipantAttempt.load(participant)
            frozen = attempt.conditions
            created = attempt.created
            row = dict(record["identity"]["plan"][0])
            row["task"] = row["tasks"][0]
            endpoint = record["identity"].get("endpoint")
            access = (Client(endpoint, created["session_token"], timeout=60) if endpoint else
                      local_service.local_service_client(stored.service))
            summary = runner.run_one(access, row, participant, ParticipantSelection(frozen["selection"], {}, {}), collect_only=True)
            summary.update(repetition=record.get("summary", {}).get("repetition", 1),
                           directory=str(directory.relative_to(output)), task=row["task"])
            if "result" in summary:
                summary["result"] = str(Path("participant") / summary["result"])
            stored.record_summary(summary)
            if summary["state"] == "finished":
                summary = finish_case(directory, output=output, results_data=request.results_data, schedule=[row])
            summaries.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if any(s.get("harness_error") or s.get("outcome") == "error" for s in summaries) else 0
