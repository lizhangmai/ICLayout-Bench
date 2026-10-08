"""Frozen participant conditions and durable creation state for one attempt."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from benchmarking.files import write_json
from benchmarking.harnesses import scheme_identity

from . import adapters
from .config import digest, package_identity

ROOT = Path(__file__).resolve().parent


def protocol_condition(frozen, *, harness=None):
    selection = frozen["selection"]
    return {"harness_kind": "agent", "harness_id": "iclayout-" + (harness or selection["harness"]),
            "harness_version": "1", "model": selection["model"],
            "prompt_sha256": hashlib.sha256(frozen["prompt"].encode()).hexdigest(),
            "configuration_sha256": digest({k: v for k, v in frozen.items()
                                             if k not in {"task", "native_store_sha256"}})}


@dataclass
class AttemptState:
    create_key: str | None = None
    native_id: str | None = None
    launches: int = 0
    access_identity: str | None = None
    created: dict | None = field(default=None, repr=False)
    phase: str | None = None
    error: str | None = None
    redactions: list[str] = field(default_factory=list, repr=False)
    capacity_interruptions: list[dict] = field(default_factory=list)
    capacity_resumes: int = 0
    capacity_outcome: str | None = None


@dataclass
class ParticipantAttempt:
    output: Path
    state: AttemptState = field(repr=False)
    conditions: dict

    @property
    def state_path(self):
        return self.output / ".private/recovery.json"

    @property
    def created(self):
        if self.state.created is None:
            raise ValueError("Uncertain session creation must be reconciled before collection")
        return self.state.created

    @classmethod
    def exists(cls, output):
        return (output / ".private/recovery.json").exists()

    @classmethod
    def read_state(cls, output):
        return AttemptState(**json.loads((output / ".private/recovery.json").read_text()))

    @classmethod
    def load(cls, output):
        return cls(output, cls.read_state(output), json.loads((output / "conditions.json").read_text()))

    def _persist(self, **changes):
        updated = replace(self.state, **changes)
        write_json(self.state_path, asdict(updated))
        for key, value in changes.items():
            setattr(self.state, key, value)

    def add_redactions(self, values):
        self._persist(redactions=sorted(set(self.state.redactions) | set(values)))

    def begin_launch(self):
        self._persist(launches=self.state.launches + 1, phase="running", error=None)

    def record_error(self, error):
        self._persist(error=error)

    def mark_unavailable(self):
        if self.state.phase == "running" or self.state.launches == 0:
            self.record_error("runner_interrupted" if self.state.launches else "not_launched")

    def begin_finalization(self, error):
        self._persist(phase="finalizing", error=error)

    def record_capacity_interruption(self, problem):
        entry = {"launch": self.state.launches, "failure": problem, "status": "interrupted"}
        self._persist(capacity_interruptions=[*self.state.capacity_interruptions, entry])

    def apply_capacity_decision(self, decision):
        """Persist the decision before sleeping or starting another native launch."""
        entries = self.state.capacity_interruptions
        if not entries:
            raise ValueError("Capacity recovery requires a recorded interruption")
        entry = dict(entries[-1], status=decision.outcome)
        if decision.delay_seconds is not None:
            entry['delay_seconds'] = decision.delay_seconds
        changes = {"capacity_interruptions": [*entries[:-1], entry]}
        if decision.outcome == "waiting":
            changes['phase'] = "capacity_wait"
        elif decision.outcome == "continued":
            changes.update(phase="ready", capacity_resumes=self.state.capacity_resumes + 1,
                           capacity_outcome="continuing")
        else:
            changes['capacity_outcome'] = decision.outcome
        self._persist(**changes)

    def complete(self, error, *, suspended):
        """Commit the attempt outcome, including interrupted continuation evidence."""
        state = self.state
        recovery = {}
        changes = {}
        if state.capacity_interruptions:
            outcome = state.capacity_outcome
            if not error:
                outcome = "recovered"
            elif outcome in {None, "continuing"}:
                outcome = "stopped_on_other_error"
            entries = state.capacity_interruptions
            if entries[-1]['status'] in {"interrupted", "waiting"}:
                entries = [*entries[:-1], dict(entries[-1], status=outcome)]
            changes.update(capacity_interruptions=entries, capacity_outcome=outcome)
            recovery = {"capacity_recovery": {"resumes": state.capacity_resumes,
                        "outcome": outcome, "interruptions": entries}}
        self._persist(error=error, phase="suspended" if suspended else "finalizing", **changes)
        return recovery

    @classmethod
    def open(cls, access, row, output, selection, env, instructions, recovery):
        private = output / ".private"
        private.mkdir(mode=0o700, exist_ok=True)
        state_path = private / "recovery.json"
        scheme = row.get("scheme", {})
        frozen = {"selection": selection, "task": row["task"], "package": package_identity(),
                  "prompt": instructions, "scheme": scheme_identity(scheme), "recovery": recovery,
                  "native_store_sha256": digest({"cwd": str(private.resolve()),
                      "home": str(adapters.get(row["harness"]).METADATA.home(env))}),
                  "adapter_sha256": digest({p.relative_to(ROOT).as_posix(): p.read_text()
                                            for p in sorted(ROOT.rglob("*.py"))}),
                  "cli_version": adapters.cli_version(row["harness"], scheme)}
        if state_path.exists():
            attempt = cls.load(output)
            if attempt.conditions != frozen:
                raise ValueError("Cannot resume changed participant conditions or CLI")
        else:
            write_json(output / "conditions.json", frozen)
            attempt = cls(output, AttemptState(create_key="trial-" + uuid.uuid4().hex,
                          native_id=str(uuid.uuid4()), access_identity=digest(getattr(access, "token", None))), frozen)
            attempt._persist()
        if attempt.state.created is None:
            if attempt.state.access_identity != digest(getattr(access, "token", None)):
                raise ValueError("Uncertain creation cannot change access identity")
            attempt._persist(created=access.create(row["task"], protocol_condition(frozen, harness=row["harness"]),
                                                  key=attempt.state.create_key))
        return attempt
