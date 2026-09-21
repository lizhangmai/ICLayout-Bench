"""Run a single participant condition or a TOML experiment matrix."""
import argparse
import json
import os
import re
import subprocess
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack, nullcontext
from pathlib import Path
from urllib.parse import quote

from benchmarking.client import Client, ClientError
from benchmarking.dataset import process_manifest
from benchmarking.layout_preview import ensure_layout_preview

from .dataset import load_dataset
from .engine.session import DockerSession
from .files import Asset
from .participants.config import digest, read_configs, read_matrix, resolve, validate
from .participants.recovery import classify, policy
from .participants.results import finish_case, verify
from .participants.runner import run_one, save, service
from .participants.scheme import check as check_scheme
from .participants.scheme import identity as scheme_identity
from .participants.storage import CaseLease, case_identity
from .tasks import load_task
from .version import package_version


def path_component(value):
    # Reversible escaping prevents slashes and distinct model names from colliding.
    return quote(value, safe="-_.").replace(".", "%2E") if value in {".", ".."} else quote(value, safe="-_.")


def default_output(row, version):
    name = "-".join(path_component(str(value)) for value in
                    (row["harness"], version, row["model"], row["effort"]))
    if "scheme" in row:
        name += "-" + path_component(row["name"]) + "-" + digest(scheme_identity(row["scheme"]))[:16]
    return Path("results") / name


def harness_version(harness):
    executable = {"codex": "codex", "claude-code": "claude", "dsh": "dsh"}[harness]
    raw = subprocess.check_output([executable, "--version"], text=True, timeout=20).strip()
    match = re.search(r"(?<![\w.])v?(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)", raw)
    if not match:
        raise ValueError("Cannot identify harness version from --version: " + harness)
    return match.group(1), raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--config", type=Path, nargs="+", help="TOML files with explicit experiment conditions")
    inputs.add_argument("--matrix", type=Path, help="TOML [defaults] and [[runs]] combinations")
    parser.add_argument("--case", action="append", help="Select a configured case by full ID or unique final name; repeat for multiple cases")
    parser.add_argument("--repetitions", type=int, help="Override repetitions for this invocation")
    parser.add_argument("--concurrency", type=int, help="Override concurrent sessions for this invocation")
    parser.add_argument("--dataset", help="HF Dataset repo ID or local Dataset directory")
    parser.add_argument("--revision", help="HF dataset revision (resolved to a fixed commit)")
    parser.add_argument("--offline", action="store_true", help="Use only the Hugging Face cache")
    parser.add_argument("--image", default=os.environ.get("ICLAYOUT_BENCH_IMAGE") or "iclayout-bench-tools:local")
    parser.add_argument("--endpoint", default=os.environ.get("ICLAYOUT_BENCH_ENDPOINT"))
    parser.add_argument("--token-env", default="ICLAYOUT_BENCH_TOKEN")
    parser.add_argument("--output", type=Path, default=os.environ.get("ICLAYOUT_BENCH_OUTPUT") or None,
                        help="Condition directory (requires one condition); default: results/<harness>-<version>-<model>-<effort>")
    parser.add_argument("--results-data", type=Path, default=os.environ.get("ICLAYOUT_BENCH_RESULTS_DATA"),
                        help="Copy terminal results to this database/archive; indexing failures stay queued")
    parser.add_argument("--resume", action="store_true", help="Recover the batch at --output without replacing attempts")
    parser.add_argument("--dry-run", action="store_true", help="Resolve combinations without service/model calls")
    args = parser.parse_args(argv)
    try:
        rows = read_configs(args.config) if args.config else read_matrix(args.matrix)
        for row in rows:
            if args.case:
                selected = []
                for name in args.case:
                    matches = ([name] if name in row["tasks"] else
                               [task for task in row["tasks"] if task.rsplit(".", 1)[-1] == name])
                    if not matches:
                        raise ValueError(f"Unknown case {name!r} in condition {row['name']}; choose a configured case ID")
                    if len(matches) > 1:
                        raise ValueError(f"Ambiguous case {name!r}; use a full ID: {', '.join(matches)}")
                    if matches[0] not in selected:
                        selected.append(matches[0])
                row["tasks"] = selected
            for key in ("repetitions", "concurrency"):
                if getattr(args, key) is not None:
                    row[key] = getattr(args, key)
            validate(row)
        # Resolve every condition before creating any sessions; no credentials enter the plan.
        selections = [resolve(r["harness"], r.get("model"), r.get("effort")) for r in rows]
        plan = [{**{k: v for k, v in r.items() if k != "results_data"}, "resolved": selection[0]}
                for r, selection in zip(rows, selections)]
        if args.dry_run:
            print(json.dumps([dict(p, **({"results_data": r["results_data"]} if "results_data" in r else {}))
                              for p, r in zip(plan, rows)], indent=2, ensure_ascii=False))
            return 0
        if (args.dataset or args.revision or args.offline) and args.endpoint:
            raise ValueError("Choose a dataset or --endpoint, not both")
        if not args.dataset and not any(r.get("dataset") for r in rows) and not args.endpoint:
            raise ValueError("Supply --dataset or a dataset configuration for local mode, or --endpoint for remote mode")
        if args.output and len(rows) != 1:
            raise ValueError("--output requires exactly one condition")
        versions = [(r["scheme"]["version"], r["scheme"]["version"]) if r["harness"] == "command"
                    else harness_version(r["harness"]) for r in rows]
        outputs = ([args.output.resolve()] if args.output else
                   [default_output(r, version[0]).resolve() for r, version in zip(rows, versions)])
        if len(set(outputs)) != len(outputs):
            raise ValueError("Duplicate harness/model/effort output directories")
        if not args.endpoint and any(policy(r.get("recovery"))["resume_session"] for r in rows):
            raise ValueError("resume_session requires an independently running --endpoint service")
        if not args.endpoint:
            images = {r.get("scheme", {}).get("solver_image", args.image) for r in rows}
            pinned = {image: DockerSession(image).image_id for image in sorted(images)}
            args.image = pinned.get(args.image, args.image)
        identity = {"plan": plan, "endpoint": args.endpoint, "image": args.image if not args.endpoint else None,
                    "benchmark": package_version()}
        if not args.endpoint:
            args.cases = {}
            identity["inputs"] = {}
            for row in rows:
                spec = row.get("dataset", {})
                source = args.dataset or spec.get("source")
                revision = args.revision or (spec.get("commit") if source and not Path(source).is_dir() else None)
                dataset = load_dataset(source, revision=revision, local_files_only=args.offline or spec.get("local_files_only", False))
                native = None
                if spec:
                    records, native = dataset.native_cases(spec["name"], spec["split"])
                    if digest(records.to_list()) != spec["index_sha256"]:
                        raise ValueError("Dataset index changed after experiment selection")
                for name in row["tasks"]:
                    config = native[name] if native is not None else dataset.case(name)
                    task = load_task(config)
                    selection = {"dataset": dataset.identity["source"],
                                 "revision": dataset.identity["commit"] if not Path(source).is_dir() else None,
                                 "case": name, "offline": args.offline or spec.get("local_files_only", False)}
                    if spec:
                        selection.update(dataset_name=spec["name"], dataset_split=spec["split"])
                    if name in args.cases and args.cases[name] != selection:
                        raise ValueError(f"Conflicting datasets for case: {name}")
                    args.cases[name] = selection
                    identity["inputs"][name] = {"dataset": dataset.identity, "case_sha256": task.digest,
                        "pdk_sha256": Asset((process_manifest(config)).read_bytes(), "toml").sha256,
                        "inputs": {key: value.sha256 for key, value in task.input_assets().items()}}
        code = 0
        blocked = set()
        for index, output in enumerate(outputs):
            current_identity = dict(identity, plan=[plan[index]],
                                    cli_version=versions[index][1],
                                    image=rows[index].get("scheme", {}).get("solver_image", args.image) if not args.endpoint else None)
            code = max(code, execute_condition(args, rows[index], selections[index],
                                               output, current_identity, blocked))
        return code
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))


def execute_condition(args, row, selection, output, identity, blocked):
    """Each case owns its identity and lock; the condition root contains only cases."""
    if args.resume and not output.exists():
        raise ValueError("Cannot resume missing output: " + str(output))
    leases, new_manifests = {}, []
    with ExitStack() as stack:
        # Acquire every selected case before validating or dispatching. Nonblocking
        # locks prevent competing invocations from executing any overlapping case.
        for task in sorted(row["tasks"]):
            directory = output / path_component(task)
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            leases[task] = stack.enter_context(CaseLease(directory))
            current = case_identity(identity, task)
            slots = [output / slot_name(row, task, rep)
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
                if manifest.exists():
                    data = json.loads(manifest.read_text())
                    recorded = data["identity"]
                    finished = data.get("state") == "finished"
                    if recorded != current:
                        raise ValueError("Case configuration, benchmark version or endpoint changed: " + task)
                    if finished:
                        verify(slot, data)
                    elif not args.resume:
                        raise ValueError("Unfinished case requires --resume: " + task)
                else:
                    if slot.exists() and any(p.name != CaseLease.filename for p in slot.iterdir()):
                        raise ValueError("Existing case lacks result identity: " + task)
                    new_manifests.append((manifest, {"identity": current, "state": "pending"}))
        for path, contents in new_manifests:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            save(path, contents)
        return execute_batch(args, [row], [selection], output, leases, blocked)


def execute_slot(args, row, selection, repetition, name, output, lease):
    check_scheme(row.get("scheme", {}))
    case_dir = output / name
    run_dir = case_dir / ".runtime"
    record = json.loads((case_dir / "result.json").read_text())
    old_summary = run_dir / "summary.json"
    if old_summary.exists() and json.loads(old_summary.read_text()).get("state") == "finished":
        return finish_case(case_dir)
    save(case_dir / "result.json", dict(record, state="running"))
    summary_path = run_dir / "summary.json"
    run_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    save(run_dir / "state.json", {"state": "running", "attempt": 1})
    settings = policy(row.get("recovery"))
    service_dir = run_dir / "service"
    if not args.endpoint:
        service_dir.mkdir(mode=0o700, exist_ok=True)
        context = service(args.cases[row["task"]], service_dir, row.get("scheme", {}).get("solver_image", args.image))
    else:
        context = nullcontext(Client(args.endpoint, os.environ.get(args.token_env, ""), timeout=60,
                                     retry_policy=settings))
    try:
        selected, env, cli_settings = selection
        env = dict(env, ICLAYOUT_BENCH_LEASE_FD=str(lease._stream.fileno()))
        with context as access:
            summary = run_one(access, row, run_dir / "participant", (selected, env, cli_settings))
        summary["repetition"] = repetition
        if "result" in summary:
            summary["result"] = str(Path("participant") / summary["result"])
    except (OSError, ValueError, RuntimeError, TimeoutError, ClientError) as error:
        summary = {"name": row["name"], "repetition": repetition, **selection[0],
                   "harness_error": type(error).__name__, "failure": classify(error),
                   "state": "suspended", "outcome": None, "score": None}
    summary.setdefault("state", "finished")
    summary["directory"] = name
    summary["task"] = row["task"]
    # Keep every recovery diagnostic; a slot never gains a new repetition.
    history = run_dir / "recovery-history"
    history.mkdir(mode=0o700, exist_ok=True)
    save(history / f"{uuid.uuid4().hex}.json", summary)
    save(summary_path, summary)
    save(run_dir / "state.json", {"state": summary["state"], "attempt": 1})
    record = json.loads((case_dir / "result.json").read_text())
    save(case_dir / "result.json", dict(record, summary=summary,
         state="finalizing" if summary["state"] == "finished" else summary["state"]))
    if summary["state"] == "finished":
        return finish_case(case_dir)
    return summary


def archive_result(args, output, name, rows):
    data = getattr(args, "results_data", None) or rows[0].get("results_data")
    if not data:
        return
    from .participants.archive import enqueue
    directory = output / name
    source = directory / "result.json"
    try:
        status = enqueue(data, source, experiment=output.name,
                         schedule=[{"tasks": r["tasks"], "repetitions": r["repetitions"],
                                    "harness": r["harness"], "model": r["model"], "effort": r["effort"]} for r in rows])
        print("Result archive: " + json.dumps(status), flush=True)
    except OSError as error:
        # The terminal export is itself the durable retry source if even the outbox disk is unavailable.
        print(f"Result archive pending ({type(error).__name__}); retry by importing {source}", flush=True)


def slot_name(row, task, repetition):
    name = path_component(task)
    return name if row["repetitions"] == 1 else str(Path(name) / f"repetition-{repetition}")


def execute_batch(args, rows, selections, output, lease, blocked=None):
    print(f"Experiment outputs: {output}", flush=True)
    summaries = []
    blocked = set() if blocked is None else blocked
    # Conditions run in order; concurrency caps independent case/repetition sessions
    # within the current condition, never multiplying across configuration files.
    for row, selection in zip(rows, selections):
        provider = (row["harness"], selection[0].get("provider"), row["model"])
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
                    name = slot_name(row, task, repetition)
                    summary_path = output / name / "result.json"
                    data = json.loads(summary_path.read_text()) if summary_path.exists() else None
                    previous = data.get("summary") if data else None
                    if previous and data["state"] != "finished":
                        previous = dict(previous, state=data["state"])
                    if previous and previous.get("state", "finished") == "finished":
                        location = ((output / name) / previous["result"]
                                    if "result" in previous else summary_path)
                        if not location.is_file():
                            raise ValueError("Completed result is missing: " + str(location))
                        print(f"SKIP case={task} condition={row['name']} repetition={repetition} "
                              f"outcome={previous.get('outcome')} result={location}", flush=True)
                        ensure_layout_preview(output / name)
                        finish_case(output / name)  # Retry any interrupted post-commit cleanup.
                        archive_result(args, output, name, [row])
                        summaries.append(previous)
                        problem = previous.get("failure") or {}
                        if problem.get("stop_dispatch"):
                            blocked.add("service" if problem["category"] == "service_failure" else provider)
                        continue
                    if provider in blocked or "service" in blocked:
                        summaries.append({"name": row["name"], "task": task, "repetition": repetition,
                                          "directory": name, **selection[0], "state": "blocked",
                                          "outcome": None, "score": None})
                        directory = output / name
                        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                        record = json.loads((directory / "result.json").read_text())
                        save(directory / "result.json", dict(record, state="blocked", summary=summaries[-1]))
                        continue
                    slot = dict(row, task=task)
                    slot_lease = lease[task]
                    future = pool.submit(execute_slot, args, slot, selection, repetition, name, output, slot_lease)
                    pending[future] = name
                if pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        name = pending.pop(future)
                        summary = future.result()
                        if summary.get("state") == "finished":
                            archive_result(args, output, name, [row])
                        summaries.append(summary)
                        problem = summary.get("failure") or {}
                        if problem.get("stop_dispatch"):
                            blocked.add("service" if problem["category"] == "service_failure" else provider)
                        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if any(s.get("harness_error") or s.get("outcome") == "error" or s.get("state") in {"suspended", "blocked"}
                    for s in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
