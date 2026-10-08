"""Case-owned identity checks and bounded participant scheduling."""
import json
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from urllib.parse import quote

from benchmarking.participants.recovery import policy
from benchmarking.participants.replacement import (
    lease_replacement,
    replace_unfinished,
    validate_replacement,
)
from benchmarking.participants.terminal import finish_case
from benchmarking.results.export import verify

from . import case, worker
from .storage import CaseLease, CaseRecord, case_identity, case_lease_root


def path_component(value):
    # Reversible escaping prevents slashes and distinct model names from colliding.
    return quote(value, safe="-_.").replace(".", "%2E") if value in {".", ".."} else quote(value, safe="-_.")



@dataclass(frozen=True)
class BatchOptions:
    endpoint: str | None
    image: str
    token_env: str
    results_data: Path | None
    resume: bool
    replace_unfinished: bool
    case_paths: dict
    cases: dict


def execute_condition(options, row, selection, output, identity, blocked):
    """Each case owns its identity and lock; Dataset paths group cases beneath the condition root."""
    if (options.resume or options.replace_unfinished) and not output.exists():
        raise ValueError("Cannot resume missing output: " + str(output))
    leases, new_manifests, replacements = {}, [], []
    with ExitStack() as stack, ExitStack() as store_leases:
        # Acquire every selected case before validating or dispatching. Nonblocking
        # locks prevent competing invocations from executing any overlapping case.
        for task in sorted(row["tasks"]):
            directory = output / options.case_paths.get(task, path_component(task))
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            first_slot = output / slot_name(row, task, 1, options.case_paths)
            lease_root = case_lease_root(first_slot, row["repetitions"])
            leases[task] = stack.enter_context(CaseLease(lease_root))
            current = case_identity(identity, task)
            slots = [output / slot_name(row, task, rep, options.case_paths)
                     for rep in range(1, row["repetitions"] + 1)]
            existing_repetitions = sorted(directory.glob("repetition-*/result.json"))
            if (directory / "result.json").exists():
                existing_repetitions.append(directory / "result.json")
            # Repetitions are frozen even if the new config would hide an old slot.
            for existing in existing_repetitions:
                old = json.loads(existing.read_text())["identity"]
                if old["plan"][0]["repetitions"] != row["repetitions"]:
                    raise ValueError("Case repetitions changed: " + task)
            for slot in slots:
                manifest = slot / "result.json"
                if (slot / '.replacement.json').exists() and not options.replace_unfinished:
                    raise ValueError('Interrupted replacement requires --replace-unfinished: ' + task)
                if manifest.exists():
                    data = json.loads(manifest.read_text())
                    recorded = data["identity"]
                    finished = data.get("state") == "finished"
                    if options.replace_unfinished:
                        replacements.append((slot, validate_replacement(slot, current)))
                        lease_replacement(slot, store_leases)
                    elif recorded != current:
                        raise ValueError("Case configuration, benchmark version or endpoint changed: " + task)
                    if finished:
                        verify(slot, data)
                    elif not options.resume and not options.replace_unfinished:
                        raise ValueError("Unfinished case requires --resume: " + task)
                else:
                    if options.replace_unfinished:
                        raise ValueError('Replacement requires an existing recorded case: ' + task)
                    if slot.exists() and any(p.name != CaseLease.filename for p in slot.iterdir()):
                        raise ValueError("Existing case lacks result identity: " + task)
                    new_manifests.append((manifest, {"identity": current, "state": "pending"}))
        for slot, transaction in replacements:
            replace_unfinished(slot, transaction)
        for path, contents in new_manifests:
            CaseRecord(path.parent).initialize(contents["identity"])
        store_leases.close()
        return execute_batch(options, row, selection, output, leases, blocked)


def execute_slot(options, row, selection, repetition, name, output, lease):
    request = case.SlotRequest(
        endpoint=options.endpoint, image=options.image, token_env=options.token_env,
        cases=options.cases, results_data=options.results_data,
    )
    return worker.supervise_slot(request, row, selection, repetition, name, output, lease)


def slot_name(row, task, repetition, case_paths):
    name = case_paths.get(task, path_component(task))
    return name if row["repetitions"] == 1 else str(Path(name) / f"repetition-{repetition}")


def execute_batch(options, row, selection, output, lease, blocked=None):
    print(f"Experiment outputs: {output}", flush=True)
    summaries = []
    blocked = set() if blocked is None else blocked
    capacity_streak, cooldown_until = {}, {}
    # Conditions run in order; concurrency caps independent case/repetition sessions
    # within the current condition, never multiplying across configuration files.
    provider = (row["harness"], selection.condition.get("provider"), row["model"])
    recovery = policy(row.get("recovery"), harness=row["harness"])
    slots = iter((task, repetition) for repetition in range(1, row["repetitions"] + 1)
                 for task in row["tasks"])
    exhausted = False
    with ThreadPoolExecutor(max_workers=row["concurrency"]) as pool:
        pending = {}
        while pending or not exhausted:
            while not exhausted and len(pending) < row["concurrency"]:
                try:
                    task, repetition = next(slots)
                except StopIteration:
                    exhausted = True
                    break
                name = slot_name(row, task, repetition, options.case_paths)
                summary_path = output / name / "result.json"
                stored = CaseRecord(output / name)
                previous = stored.previous_summary() if summary_path.exists() else None
                if previous and previous.get("state", "finished") == "finished":
                    location = ((output / name) / previous["result"]
                                if "result" in previous else summary_path)
                    if not location.is_file():
                        raise ValueError("Completed result is missing: " + str(location))
                    print(f"SKIP case={task} condition={row['name']} repetition={repetition} "
                          f"outcome={previous.get('outcome')} result={location}", flush=True)
                    previous = finish_case(output / name, output=output, results_data=options.results_data, schedule=[row])
                    summaries.append(previous)
                    problem = previous.get("failure") or {}
                    for issue in (problem, (previous.get("finalization_error") or {}).get("failure") or {}):
                        if issue.get("stop_dispatch"):
                            blocked.add("service" if issue["category"] == "service_failure" else provider)
                    continue
                if provider in blocked or "service" in blocked:
                    summaries.append({"name": row["name"], "task": task, "repetition": repetition,
                                      "directory": name, **selection.condition, "state": "blocked",
                                      "outcome": None, "score": None})
                    directory = output / name
                    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                    stored.block(summaries[-1])
                    continue
                if time.monotonic() < cooldown_until.get(provider, 0):
                    slots = chain([(task, repetition)], slots)
                    break
                slot = dict(row, task=task)
                slot_lease = lease[task]
                future = pool.submit(execute_slot, options, slot, selection, repetition, name, output, slot_lease)
                pending[future] = name
            if pending:
                delay = cooldown_until.get(provider, 0) - time.monotonic()
                done, _ = wait(pending, timeout=delay if delay > 0 else None, return_when=FIRST_COMPLETED)
                for future in done:
                    name = pending.pop(future)
                    summary = future.result()
                    summaries.append(summary)
                    problem = summary.get("failure") or {}
                    for issue in (problem, (summary.get("finalization_error") or {}).get("failure") or {}):
                        if issue.get("stop_dispatch"):
                            blocked.add("service" if issue["category"] == "service_failure" else provider)
                    if recovery["capacity_resumes"]:
                        interrupted = bool((summary.get("capacity_recovery") or {}).get("interruptions"))
                        interrupted |= problem.get("category") == "provider_overloaded"
                        capacity_streak[provider] = capacity_streak.get(provider, 0) + 1 if interrupted else 0
                        if capacity_streak[provider] >= 2:
                            delay = recovery["capacity_cooldown_seconds"]
                            cooldown_until[provider] = time.monotonic() + delay
                            capacity_streak[provider] = 0
                            print(f"CAPACITY_COOLDOWN model={row['model']} delay_seconds={delay:.3f}", flush=True)
                    print(json.dumps(summary, ensure_ascii=False), flush=True)
            elif not exhausted:
                time.sleep(min(60, max(0, cooldown_until.get(provider, 0) - time.monotonic())))
    return 1 if any(s.get("harness_error") or s.get("outcome") == "error" or s.get("state") in {"suspended", "blocked"}
                    for s in summaries) else 0
