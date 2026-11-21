"""Case-owned identity checks and bounded participant scheduling."""

import json
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from benchmarking.execution.leases import BatchLeaseError, CaseLease
from benchmarking.participants.attempt import worker as case
from benchmarking.participants.attempt.boundaries import (
    DEFAULT_BOUNDARIES,
    AttemptBoundaries,
)
from benchmarking.participants.attempt.recovery import policy
from benchmarking.participants.attempt.storage import (
    CaseRecord,
    case_identity,
    case_lease_root,
)
from benchmarking.participants.attempt.worker import finish_case
from benchmarking.participants.batch import coordinator as scheduler
from benchmarking.participants.batch import worker
from benchmarking.participants.batch.config import frozen_pricing
from benchmarking.participants.batch.replacement import (
    content_identity,
    lease_replacement,
    replace_unfinished,
    validate_replacement,
)
from benchmarking.results.package import verify


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


@dataclass(frozen=True)
class BatchBoundaries:
    """Batch effects outside its case records; the defaults are the production effects.

    ``run_slot`` has :func:`execute_slot`'s signature; ``None`` runs each slot in
    its own worker process through :func:`execute_slot`. ``clock`` times dispatch
    cooldowns. ``attempt`` supplies service clients for replacement checks.
    """

    run_slot: Callable | None = None
    clock: Any = time
    attempt: AttemptBoundaries = DEFAULT_BOUNDARIES


DEFAULT_BATCH = BatchBoundaries()


def execute_condition(options, row, selection, output, identity, blocked, boundaries=None, *, scheduler_fd=None):
    if (options.resume or options.replace_unfinished) and not output.exists():
        raise ValueError("Cannot resume missing output: " + str(output))
    with scheduler.Coordinator(output, row, scheduler_fd) as coordinator:
        code = _execute_condition(options, row, selection, output, identity, blocked, coordinator,
                                  boundaries or DEFAULT_BATCH)
        coordinator.exit_code = code
        return code


def _execute_condition(options, row, selection, output, identity, blocked, coordinator, boundaries):
    """Each timestamped case run owns its identity and lock beneath the condition root."""
    leases, new_manifests, replacements = {}, [], []
    active = scheduler.live_slots(output) if options.resume else {}
    # Record existence before acquiring leases, which can create directories.
    existing_slots = {output / slot_name(row, task, rep, options.case_paths)
                      for task in row['tasks'] for rep in range(1, row['repetitions'] + 1)
                      if (output / slot_name(row, task, rep, options.case_paths)).exists()}

    with ExitStack() as stack, ExitStack() as store_leases:
        # Acquire every selected case before validating or dispatching. Nonblocking
        # locks prevent competing invocations from executing any overlapping case.
        for task in sorted(row["tasks"]):
            directory = output / options.case_paths.get(task, path_component(task))
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            first_slot = output / slot_name(row, task, 1, options.case_paths)
            lease_root = case_lease_root(first_slot, row["repetitions"])
            current = case_identity(identity, task)
            slots = [output / slot_name(row, task, rep, options.case_paths)
                     for rep in range(1, row["repetitions"] + 1)]
            try:
                leases[task] = stack.enter_context(CaseLease(lease_root))
            except BatchLeaseError:
                # A resumed coordinator may observe an independently owned worker.
                # Terminal slots can also be verified without mutating their records.
                observable = all(str(slot.relative_to(output)) in active or
                    (slot.joinpath('result.json').exists() and CaseRecord(slot).read()['state'] == 'finished')
                    or (slot.joinpath('result.json').exists() and CaseRecord(slot).read()['state'] == 'pending')
                    for slot in slots)
                has_owner = any(str(slot.relative_to(output)) in active for slot in slots)
                all_finished = all(slot.joinpath('result.json').exists() and
                                   CaseRecord(slot).read()['state'] == 'finished' for slot in slots)
                if not options.resume or not observable or not (has_owner or all_finished):
                    raise
                leases[task] = None
            existing_repetitions = sorted(directory.glob("repetition-*/result.json"))
            if (directory / "result.json").exists():
                existing_repetitions.append(directory / "result.json")
            # Repetitions are frozen even if the new config would hide an old slot.
            for existing in existing_repetitions:
                old = json.loads(existing.read_text())["identity"]
                if old["plan"][0]["repetitions"] != row["repetitions"]:
                    raise ValueError("Case repetitions changed: " + task)
            if existing_repetitions:
                # Shared price lists can change between invocations. Existing
                # runs retain their original price basis, including repetitions
                # that were allocated but have not yet started.
                recorded = json.loads(existing_repetitions[0].read_text())["identity"]
                current = dict(current, plan=[frozen_pricing(current["plan"][0], recorded["plan"][0])])
            for slot in slots:
                manifest = slot / "result.json"
                if (slot / '.replacement.json').exists() and not options.replace_unfinished:
                    raise ValueError('Interrupted replacement requires --replace-unfinished: ' + task)
                if manifest.exists():
                    data = json.loads(manifest.read_text())
                    recorded = data["identity"]
                    finished = data.get("state") == "finished"
                    if options.replace_unfinished:
                        replacements.append((slot, validate_replacement(slot, current,
                                                                        client=boundaries.attempt.client)))
                        lease_replacement(slot, store_leases)
                    elif content_identity(recorded) != content_identity(current):
                        raise ValueError("Case configuration, benchmark version or endpoint changed: " + task)
                    if finished:
                        verify(slot, data)
                    elif not options.resume and not options.replace_unfinished:
                        raise ValueError("Unfinished case requires --resume: " + task)
                else:
                    if options.replace_unfinished:
                        raise ValueError('Replacement requires an existing recorded case: ' + task)
                    if options.resume and slot in existing_slots:
                        raise ValueError("Existing case lacks result identity: " + task)
                    if slot.exists() and any(p.name != CaseLease.filename for p in slot.iterdir()):
                        raise ValueError("Existing case lacks result identity: " + task)
                    new_manifests.append((manifest, {"identity": current, "state": "pending"}))
        for slot, transaction in replacements:
            replace_unfinished(slot, transaction)
        for path, contents in new_manifests:
            CaseRecord(path.parent).initialize(contents["identity"])
        store_leases.close()
        return execute_batch(options, row, selection, output, leases, blocked,
                             coordinator=coordinator, active=active, lease_stack=stack, boundaries=boundaries)


def slot_request(options):
    """Launch inputs a slot worker receives from the batch options."""
    return case.SlotRequest(
        endpoint=options.endpoint, image=options.image, token_env=options.token_env,
        cases=options.cases, results_data=options.results_data,
    )


def execute_slot(options, row, selection, repetition, name, output, lease):
    return worker.supervise_slot(slot_request(options), row, selection, repetition, name, output, lease)


def slot_name(row, task, repetition, case_paths):
    name = case_paths.get(task, path_component(task))
    return name if row["repetitions"] == 1 else str(Path(name) / f"repetition-{repetition}")


def dispatch_block(issue, row, endpoint):
    """Identify the shared resource that failed; a local session owns no batch block."""
    if not issue.get('stop_dispatch') or issue.get('scope') == 'session':
        return None
    scope = issue.get('scope') or ('endpoint' if issue.get('category') == 'service_failure' else 'provider')
    if scope == 'runtime':
        return ('runtime',)
    if scope == 'endpoint':
        return ('endpoint', endpoint) if endpoint else None
    return ('provider', row['harness'], row.get('harness_home') or
            (row.get('resolved') or {}).get('provider'))


def dispatch_blocks(summary, row, endpoint):
    """Shared resources blocked by a case's stop-dispatch or finalization failure."""
    issues = (summary.get('failure') or {}, (summary.get('finalization_error') or {}).get('failure') or {})
    targets = (dispatch_block(issue, row, endpoint) for issue in issues if issue.get('stop_dispatch'))
    return {target for target in targets if target is not None}


def dispatch_blocked(blocked, row, endpoint):
    """Whether a recorded block covers this condition's runtime, endpoint or provider."""
    provider = dispatch_block({'stop_dispatch': True, 'scope': 'provider'}, row, endpoint)
    return any(target in blocked for target in (('runtime',), ('endpoint', endpoint), provider))


@dataclass
class CapacityCooldown:
    """Pause new dispatch after consecutive capacity-interrupted cases of one provider/model."""

    seconds: float
    until: float = 0
    streak: int = 0

    def observe(self, summary, now):
        """Count one collected case; return the started pause, or ``None``."""
        interrupted = (bool((summary.get('capacity_recovery') or {}).get('interruptions'))
                       or (summary.get('failure') or {}).get('category') == 'provider_overloaded')
        self.streak = self.streak + 1 if interrupted else 0
        if self.streak < 2:
            return None
        self.streak, self.until = 0, now + self.seconds
        return self.seconds


def poll_timeout(cooldown_remaining, deferred):
    """Wake for leases released by other owners and for cooldown expiry."""
    if deferred:
        return min(cooldown_remaining, .05) if cooldown_remaining > 0 else .05
    return cooldown_remaining if cooldown_remaining > 0 else None


class _ConditionDispatch:
    """Dispatch one condition's slots and record skipped, blocked and completed cases."""

    def __init__(self, options, row, selection, output, lease, blocked, coordinator, lease_stack, boundaries):
        self.options, self.row, self.selection, self.output = options, row, selection, output
        self.lease, self.blocked = lease, blocked
        self.coordinator, self.lease_stack = coordinator, lease_stack
        self.clock = boundaries.clock
        self.run_slot = boundaries.run_slot or execute_slot
        recovery = policy(row.get("recovery"), harness=row["harness"])
        self.capacity_resumes = recovery['capacity_resumes']
        self.cooldown = CapacityCooldown(recovery['capacity_cooldown_seconds'])
        self.provider = (row["harness"], selection.condition.get("provider"), row["model"])
        self.summaries = []

    def submit(self, pool, slots, pending):
        """Submit ready slots up to the concurrency cap; return how many await a case lease."""
        row, options = self.row, self.options
        deferred = 0
        available = len(slots)
        while slots and len(pending) < row["concurrency"] and available:
            available -= 1
            task, repetition = slots.popleft()
            name = slot_name(row, task, repetition, options.case_paths)
            stored = CaseRecord(self.output / name)
            slot_row = frozen_pricing(row, stored.read()["identity"]["plan"][0])
            previous = stored.previous_summary()
            if previous and previous.get("state", "finished") == "finished":
                self._skip(stored, task, repetition, slot_row, previous)
            elif not self._lease(task):
                slots.append((task, repetition))
                deferred += 1
            elif dispatch_blocked(self.blocked, row, options.endpoint):
                self._block(stored, task, repetition, name)
            elif self.clock.monotonic() < self.cooldown.until:
                slots.appendleft((task, repetition))
                break
            else:
                self.coordinator.event('case_dispatched', case=name, repetition=repetition)
                future = pool.submit(self.run_slot, options, dict(slot_row, task=task), self.selection,
                                     repetition, name, self.output, self.lease[task])
                pending[future] = name
        return deferred

    def _skip(self, stored, task, repetition, slot_row, previous):
        verify(stored.root, stored.read())
        if self.lease[task] is not None:
            previous = finish_case(stored.root, output=self.output, results_data=self.options.results_data,
                                   schedule=[slot_row])
        self.summaries.append(previous)
        print(f"SKIP case={task} condition={self.row['name']} repetition={repetition} "
              f"outcome={previous.get('outcome')} result={stored.manifest}", flush=True)
        self.blocked.update(dispatch_blocks(previous, slot_row, self.options.endpoint))

    def _lease(self, task):
        """Hold the case lease, acquiring it once a resumed independent owner has exited."""
        if self.lease[task] is None:
            first = self.output / slot_name(self.row, task, 1, self.options.case_paths)
            try:
                self.lease[task] = self.lease_stack.enter_context(
                    CaseLease(case_lease_root(first, self.row['repetitions'])))
            except BatchLeaseError:
                return False
        return True

    def _block(self, stored, task, repetition, name):
        summary = {'name': self.row['name'], 'task': task, 'repetition': repetition,
                   'directory': name, **self.selection.condition, 'state': 'blocked',
                   'outcome': None, 'score': None}
        stored.block(summary)
        self.summaries.append(summary)
        self.coordinator.event('case_blocked', case=name)

    def complete(self, name, summary, selected):
        if selected:
            self.summaries.append(summary)
        problem = summary.get('failure') or {}
        self.coordinator.event('case_completed', case=name, state=summary.get('state'),
                               outcome=summary.get('outcome'), score=summary.get('score'),
                               failure_category=problem.get('category'), selected=selected)
        recorded = CaseRecord(self.output / name).read()['identity']['plan'][0]
        self.blocked.update(dispatch_blocks(summary, recorded, self.options.endpoint))
        source_provider = (recorded['harness'], (recorded.get('resolved') or {}).get('provider'), recorded['model'])
        if source_provider != self.provider:
            return
        if self.capacity_resumes:
            delay = self.cooldown.observe(summary, self.clock.monotonic())
            if delay is not None:
                self.coordinator.event('capacity_cooldown', delay_seconds=delay)
                print(f"CAPACITY_COOLDOWN model={self.row['model']} delay_seconds={delay:.3f}", flush=True)
        print(json.dumps(summary, ensure_ascii=False), flush=True)


def execute_batch(options, row, selection, output, lease, blocked=None, *, coordinator, active, lease_stack,
                  boundaries=DEFAULT_BATCH):
    print(f"Experiment outputs: {output}", flush=True)
    # Conditions run in order; concurrency caps independent case/repetition sessions
    # within the current condition, never multiplying across configuration files.
    dispatch = _ConditionDispatch(options, row, selection, output, lease, set() if blocked is None else blocked,
                                  coordinator, lease_stack, boundaries)
    clock = boundaries.clock
    selected = {slot_name(row, task, rep, options.case_paths)
                for rep in range(1, row['repetitions'] + 1) for task in row['tasks']}
    slots = deque((task, repetition) for repetition in range(1, row["repetitions"] + 1)
                  for task in row["tasks"]
                  if slot_name(row, task, repetition, options.case_paths) not in active)
    cancelled = threading.Event()
    with ThreadPoolExecutor(max_workers=max(row["concurrency"], len(active))) as pool:
        pending = {}
        try:
            for name, owner in active.items():
                coordinator.event('worker_adopted', case=name, pid=owner['pid'], selected=name in selected)
                pending[pool.submit(scheduler.observe_worker, output / name, owner, cancelled)] = name
            while slots or any(name in selected for name in pending.values()):
                deferred = dispatch.submit(pool, slots, pending)
                if not slots and not any(name in selected for name in pending.values()):
                    break
                cooling = dispatch.cooldown.until - clock.monotonic()
                if pending:
                    done, _ = wait(pending, timeout=poll_timeout(cooling, deferred), return_when=FIRST_COMPLETED)
                    for future in done:
                        name = pending.pop(future)
                        dispatch.complete(name, future.result(), name in selected)
                elif slots:
                    clock.sleep(min(60, cooling) if cooling > 0 else .05)
        finally:
            cancelled.set()
    return 1 if any(s.get("harness_error") or s.get("outcome") == "error" or s.get("state") in {"suspended", "blocked"}
                    for s in dispatch.summaries) else 0
