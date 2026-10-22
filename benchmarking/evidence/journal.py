"""Private, durable run evidence. A submission event is the acceptance commit."""

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from benchmarking.files import (
    Asset,
    EvidenceError,
    atomic_write,
    read_file,
    sync_directory,
)

__all__ = ["RecordingError", "RunJournal", "RunRecorder", "read_journal", "recover_submissions"]


class RecordingError(OSError):
    """Evidence could not be persisted; this run cannot produce a score."""


@dataclass(frozen=True)
class RunJournal:
    events: tuple[dict, ...]
    incomplete_tail: bool = False


def read_journal(root, *, partial=False, missing_ok=False):
    """Read ordered committed events; only an unfinished final line is optional."""
    try:
        raw = read_file(Path(root), 'events.jsonl')
    except FileNotFoundError:
        if missing_ok:
            return RunJournal(())
        raise
    except ValueError as error:
        raise EvidenceError('Invalid archived journal') from error
    lines = raw.split(b'\n')
    events = []
    for line in lines[:-1]:
        try:
            event = json.loads(line)
        except ValueError as error:
            raise EvidenceError('Invalid committed journal event') from error
        if (not isinstance(event, dict) or type(event.get('sequence')) is not int
                or event['sequence'] != len(events) + 1
                or not isinstance(event.get('kind'), str) or not event['kind']
                or not isinstance(event.get('data'), dict)):
            raise EvidenceError('Invalid event journal sequence or schema')
        events.append(event)
    incomplete_tail = bool(lines[-1])
    if incomplete_tail and not partial:
        raise EvidenceError('Cannot read an event journal with an incomplete tail')
    return RunJournal(tuple(events), incomplete_tail)


class RunRecorder:
    def __init__(self, destination):
        self.root = Path(destination).absolute()
        self.root.mkdir(parents=True, mode=0o700)
        sync_directory(self.root.parent)
        (self.root / "artifacts").mkdir(mode=0o700)
        atomic_write(self.root / "events.jsonl", b"")
        self._lock = threading.RLock()
        self._sequence = 0
        self._started = time.monotonic()
        self.error = None
        self._closed = False

    @classmethod
    def resume(cls, destination, *, discard_incomplete_tail=False):
        """Reopen an unfinished evidence directory without replacing its journal."""
        self = cls.__new__(cls)
        self.root = Path(destination).absolute()
        if not self.root.is_dir() or not (self.root / "artifacts").is_dir():
            raise FileNotFoundError(self.root)
        self._lock = threading.RLock()
        journal = read_journal(self.root, partial=discard_incomplete_tail)
        self._sequence = len(journal.events)
        self._started = time.monotonic()
        if journal.events:
            last = journal.events[-1]
            elapsed = last.get('elapsed_seconds', 0)
            if last.get('time'):
                elapsed += max(0, time.time() - datetime.fromisoformat(last['time']).timestamp())
            self._started -= elapsed
        self.error = None
        self._closed = False
        if journal.incomplete_tail:
            path = self.root / 'events.jsonl'
            raw = path.read_bytes()
            committed = raw.rfind(b'\n') + 1
            # Archive the uncommitted bytes; they remain evidence, not events.
            tail = self.archive(Asset(raw[committed:], 'binary'))
            atomic_write(path, raw[:committed])
            self.event('journal.recovered', incomplete_tail=tail)
        return self

    def _write(self, operation):
        if self._closed:
            raise RecordingError("Run recorder is closed")
        if self.error:
            raise RecordingError(self.error)
        try:
            return operation()
        except OSError as error:
            self.error = "Run evidence persistence failed"
            raise RecordingError(self.error) from error

    def archive(self, asset):
        with self._lock:
            path = self.root / "artifacts" / asset.sha256
            if not path.exists():
                self._write(lambda: atomic_write(path, asset.content, 0o400))
            return {**asset.identity(), "path": f"artifacts/{asset.sha256}"}

    def save(self, report, *, filename="run.json"):
        if filename not in {"run.json", "batch.json"}:
            raise ValueError("Unsupported record filename")
        with self._lock:
            content = (json.dumps(report, indent=2, allow_nan=False) + "\n").encode()
            self._write(lambda: atomic_write(self.root / filename, content))

    def event(self, kind, **data):
        with self._lock:
            event = {"sequence": self._sequence + 1,
                     "time": datetime.now(UTC).isoformat(),
                     "elapsed_seconds": time.monotonic() - self._started,
                     "kind": kind, "data": data}
            content = (json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n").encode()

            def append():
                with (self.root / "events.jsonl").open("ab") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())

            self._write(append)
            self._sequence += 1
            return event


    def finish(self, report, *, filename="run.json", kind="run.finished"):
        """Seal the journal and bind its exact bytes to the final atomic report."""
        with self._lock:
            self.event(kind, termination=report["termination"], outcome=report["outcome"])
            report["events"].update(Asset((self.root / "events.jsonl").read_bytes(), "jsonl").identity())
            report["phase"] = "finished"
            self.save(report, filename=filename)
            self._closed = True


def recover_submissions(destination):
    """Read committed submissions, tolerating only an unfinished final journal line.

    Does not resume an agent, modify the old run, or turn an interrupted run into
    a score. Orphaned blobs without an acceptance event are never submissions.
    """
    root = Path(destination).absolute()
    submissions, candidate = [], None
    journal = read_journal(root, partial=True)
    for event in journal.events:
        if event["kind"] != "submission":
            continue
        receipt = event["data"]["receipt"]
        if receipt["accepted"]:
            ref = event["data"]["candidate"]
            if ref["path"] != f'artifacts/{ref["sha256"]}' or not re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]):
                raise ValueError("Invalid candidate artifact path")
            asset = Asset(read_file(root, ref["path"]), "gds")
            if ref != {**asset.identity(), "path": ref["path"]} or any(
                    receipt[k] != v for k, v in asset.identity().items()):
                raise ValueError("Committed candidate integrity mismatch")
            candidate = ref
        submissions.append(receipt)
    return {"submissions": submissions, "candidate": candidate,
            "journal_events": len(journal.events), "incomplete_tail": journal.incomplete_tail}
