"""Ownership and lifecycle for the participant's local evaluation service."""
import json
import os
import secrets
import selectors
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

from benchmarking.client import Client
from benchmarking.files import append_event, write_json
from benchmarking.service.process import process_start

from .config import clean_env


def stop(process, signum=signal.SIGTERM):
    if process.poll() is None:
        os.killpg(process.pid, signum)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def local_service_owner(output):
    """Find a live service using its durably recorded process identity."""
    owner_path = output / ".private/owner.json"
    if owner_path.exists():
        owner = json.loads(owner_path.read_text())
        if process_start(owner["pid"]) == owner["start"]:
            return owner
    return None


def local_service_client(output):
    owner = local_service_owner(output)
    if owner is None:
        raise RuntimeError("Existing local service is unavailable; retained session was not relaunched")
    token = json.loads((output / ".private/access.json").read_text())["token"]
    return Client(owner["endpoint"], token, timeout=60)


def stop_local_service(output):
    owner = local_service_owner(output)
    if owner is not None and process_start(owner["pid"]) == owner["start"]:
        try:
            os.killpg(owner["pid"], signal.SIGINT)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 30
        while process_start(owner["pid"]) == owner["start"]:
            if time.monotonic() >= deadline:
                raise TimeoutError("Local service still owns its store; recovery material retained")
            time.sleep(.05)


@contextmanager
def service(case, output, image):
    """Local mode starts the installed service; remote mode needs no evaluator."""
    private = output / ".private"
    private.mkdir(mode=0o700, exist_ok=True)
    token_file = private / "access.json"
    token = json.loads(token_file.read_text())["token"] if token_file.exists() else secrets.token_urlsafe(32)
    if not token_file.exists():
        write_json(token_file, {"token": token})
    owner = local_service_owner(output)
    if owner is not None:
        append_event(output / 'lifecycle.jsonl', 'service_reused', durable=True, pid=owner['pid'])
        try:
            yield Client(owner["endpoint"], token, timeout=60)
        finally:
            if (output.parent / "participant/analysis/manifest.json").exists():
                stop_local_service(output)
        return
    env = clean_env()
    env["ICLAYOUT_BENCH_LOCAL_TOKEN"] = token
    with (output / "service.log").open("a") as log:
        process = subprocess.Popen([
            sys.executable, "-I", "-m", "benchmarking.service", "--dataset", case["dataset"], "--case", case["case"],
            *(["--revision", case["revision"]] if case.get("revision") else []),
            *(["--offline"] if case.get("offline") else []),
            *(["--dataset-name", case["dataset_name"], "--dataset-split", case["dataset_split"]]
              if case.get("dataset_name") else []),
            "--data", str(output / "service-store"), "--port", "0",
            "--owner-record", str(private / "owner.json"),
            "--image", image, "--token-env", "ICLAYOUT_BENCH_LOCAL_TOKEN",
        ], cwd=output, env=env, stdout=subprocess.PIPE, stderr=log, text=True, start_new_session=True)
        append_event(output / 'lifecycle.jsonl', 'service_spawned', durable=True, pid=process.pid)
        ready = False
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=600):
                    raise TimeoutError("Local service did not start; see service.log")
            line = process.stdout.readline().strip()
            prefix = "Local development service: "
            if not line.startswith(prefix):
                raise RuntimeError("Local service failed; see service.log")
            ready = True
            append_event(output / 'lifecycle.jsonl', 'service_ready', durable=True, pid=process.pid)
            yield Client(line.removeprefix(prefix), token, timeout=60)
        finally:
            if not ready or (output.parent / "participant/analysis/manifest.json").exists():
                stop(process, signal.SIGINT)
                append_event(output / 'lifecycle.jsonl', 'service_exit', durable=True, pid=process.pid,
                             exit_code=process.returncode, ready=ready)
            process.stdout.close()
