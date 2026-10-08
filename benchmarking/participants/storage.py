"""Case-owned provenance and mutual exclusion for default experiment results."""

import json
from pathlib import Path
from uuid import uuid4

from benchmarking.files import write_json
from benchmarking.locking import BatchLease


class CaseLease(BatchLease):
    filename = ".case.lock"

    # Closing one owner must not unlock descriptors inherited by its workers.
    unlock_on_exit = False


class CaseRecord:
    """Own a case's durable scheduling state and runtime summary commits.

    Callers hold the case lease before mutating a record. Terminal evidence
    publication and runtime removal belong to terminal.finish_case.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.runtime = self.root / ".runtime"
        self.participant = self.runtime / "participant"
        self.service = self.runtime / "service"
        self.manifest = self.root / "result.json"

    def read(self):
        return json.loads(self.manifest.read_text())

    def initialize(self, identity):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_json(self.manifest, {"identity": identity, "state": "pending"})

    def terminal_summary(self):
        record = self.read()
        if record["state"] == "finished":
            return record["summary"]
        path = self.runtime / "summary.json"
        if path.exists():
            summary = json.loads(path.read_text())
            if summary["state"] == "finished":
                return summary
        return None

    def begin(self):
        write_json(self.manifest, dict(self.read(), state="running"))
        self.runtime.mkdir(parents=True, mode=0o700, exist_ok=True)

    def record_summary(self, summary):
        """Retain recovery evidence before publishing the case state."""
        history = self.runtime / "recovery-history"
        history.mkdir(parents=True, mode=0o700, exist_ok=True)
        write_json(history / f"{uuid4().hex}.json", summary)
        write_json(self.runtime / "summary.json", summary)
        write_json(self.manifest, dict(self.read(), summary=summary,
                   state="finalizing" if summary["state"] == "finished" else summary["state"]))

    def block(self, summary):
        write_json(self.manifest, dict(self.read(), state="blocked", summary=summary))

    def previous_summary(self):
        record = self.read()
        summary = record.get("summary")
        if summary and record["state"] != "finished":
            return dict(summary, state=record["state"])
        return summary

    @classmethod
    def discover(cls, output):
        for path in sorted(output.rglob("result.json")):
            if ".runtime" not in path.relative_to(output).parts:
                record = cls(path.parent)
                data = record.read()
                if "identity" in data and "state" in data:
                    yield record


def case_lease_root(slot, repetitions):
    """Return the task-owned directory used to lock all its repetition slots."""
    slot = Path(slot)
    return slot.parent if repetitions > 1 else slot


def case_identity(condition, task):
    """Other selected cases and dispatch concurrency do not change this experiment."""
    row = condition["plan"][0]
    if task not in row["tasks"]:
        raise ValueError("Task is absent from the recorded condition")
    identity = {k: v for k, v in condition.items() if k not in {"plan", "inputs"}}
    identity["plan"] = [{**{k: v for k, v in row.items() if k not in {"tasks", "concurrency"}},
                         "tasks": [task]}]
    if "inputs" in condition:
        identity["inputs"] = {task: condition["inputs"][task]}
    return identity
