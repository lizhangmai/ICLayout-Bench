"""Execution and collection for one case-owned participant slot."""
import json
import os
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from pathlib import Path

from benchmarking.client import Client, ClientError
from benchmarking.participants.recovery import classify, policy
from benchmarking.participants.scheme import check as check_scheme
from benchmarking.participants.terminal import finish_case

from . import local_service, runner
from .adapters.contracts import ParticipantSelection
from .attempt import ParticipantAttempt
from .storage import CaseLease, CaseRecord, case_lease_root


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
        context = local_service.service(request.cases[row["task"]], service_dir, row.get("scheme", {}).get("solver_image", request.image))
    else:
        context = nullcontext(Client(request.endpoint, os.environ.get(request.token_env, ""), timeout=60,
                                     retry_policy=settings))
    try:
        selection = selection.with_environment(ICLAYOUT_BENCH_LEASE_FD=str(lease.fileno()))
        with context as access:
            summary = runner.run_one(access, row, run_dir / "participant", selection)
        summary["repetition"] = repetition
        if "result" in summary:
            summary["result"] = str(Path("participant") / summary["result"])
    except (OSError, ValueError, RuntimeError, TimeoutError, ClientError) as error:
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
