"""Durable terminal-result outbox; indexing failures never restart an Agent."""

import hashlib
import json
import os
from pathlib import Path

from benchmarking.files import atomic_write


def enqueue(data, source, *, experiment, schedule=None, namespace="local"):
    data, source = Path(data), Path(source).resolve()
    pending = data / "pending"
    pending.mkdir(parents=True, exist_ok=True, mode=0o700)
    job = {
        "source": str(source),
        "experiment": experiment,
        "schedule": schedule or [],
        "namespace": namespace,
    }
    key = hashlib.sha256(str(source).encode()).hexdigest()
    path = pending / (key + ".json")
    atomic_write(path, json.dumps(job).encode())
    return deliver(data, path)


def deliver(data, path):
    store = None
    try:
        from benchmarking.results import ResultStore

        job = json.loads(Path(path).read_text())
        store = ResultStore(
            data, database_url=os.environ.get("ICLAYOUT_BENCH_DATABASE_URL")
        )
        store.register_experiment(
            job["experiment"], job["schedule"], namespace=job["namespace"]
        )
        result = store.import_result(
            job["source"], experiment=job["experiment"], namespace=job["namespace"]
        )
        Path(path).unlink()
        return result
    except Exception as error:  # noqa: BLE001 - archive failures must not change a terminal experiment
        # The exception category is useful; database URLs / provider details are not printed.
        return {
            "status": "pending",
            "reason": type(error).__name__,
            "retry": "benchmarking.results retry",
        }
    finally:
        if store is not None:
            store.close()


def retry(data):
    return [deliver(data, p) for p in sorted((Path(data) / "pending").glob("*.json"))]
