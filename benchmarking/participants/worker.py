"""Keep a case's existing solve, settlement and export alive beyond its scheduler."""

import json
import os
import subprocess
import sys
from pathlib import Path

from benchmarking.files import append_event, write_json

from .adapters.contracts import ParticipantSelection
from .case import SlotRequest, execute_owned_slot
from .local_service import process_start


def supervise_slot(request, row, selection, repetition, name, output, lease):
    """Pass the case lease and launch inputs to one independent owner process."""
    case_dir = output / name
    runtime = case_dir / ".runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    payload = {
        "request": {
            "endpoint": request.endpoint,
            "image": request.image,
            "token_env": request.token_env,
            "cases": request.cases,
            "results_data": str(request.results_data) if request.results_data else None,
        },
        "row": row,
        "selection": selection.launch_payload(),
        "repetition": repetition,
        "name": name,
        "output": str(output),
        "scheduler": {"pid": os.getpid(), "start": process_start(os.getpid())},
    }
    fd = lease.fileno()
    with (runtime / "worker.log").open("a") as log:
        process = subprocess.Popen(
            [sys.executable, "-I", "-m", "benchmarking.participants.worker", str(fd)],
            cwd=Path(__file__).resolve().parents[2], stdin=subprocess.PIPE,
            stdout=log, stderr=log, text=True, start_new_session=True, pass_fds=(fd,))
        append_event(output / '.scheduler/events.jsonl', 'worker_spawned', durable=True,
                     case=name, pid=process.pid)
        # Credentials travel over the pipe; they are never written as launch inputs.
        process.communicate(json.dumps(payload))
    if process.returncode:
        raise RuntimeError(f"Case worker exited {process.returncode}; retained session needs --collect-only")
    record = json.loads((case_dir / "result.json").read_text())
    if "summary" not in record:
        raise RuntimeError("Case worker did not commit its result; recovery evidence retained")
    return record["summary"]


def main():
    payload = json.load(sys.stdin)
    request_data = payload["request"]
    if request_data["results_data"]:
        request_data["results_data"] = Path(request_data["results_data"])
    request = SlotRequest(**request_data)
    output = Path(payload["output"])
    runtime = output / payload['name'] / '.runtime'
    write_json(output / payload["name"] / ".runtime/worker.json",
               {"pid": os.getpid(), "start": process_start(os.getpid()),
                "scheduler": payload["scheduler"]})
    append_event(runtime / 'worker-events.jsonl', 'worker_started', durable=True,
                 pid=os.getpid(), scheduler_pid=payload['scheduler']['pid'])
    # Closing this inherited descriptor releases only this process's reference.
    # The scheduler and native child may still hold the same exclusive lease.
    with os.fdopen(int(sys.argv[1]), "ab", closefd=True) as lease:
        try:
            execute_owned_slot(request, payload["row"], ParticipantSelection(**payload["selection"]),
                               payload["repetition"], payload["name"], output, lease)
        except Exception as error:
            if runtime.exists():
                append_event(runtime / 'worker-events.jsonl', 'worker_failed', durable=True,
                             error_type=type(error).__name__)
            raise


if __name__ == "__main__":
    main()
