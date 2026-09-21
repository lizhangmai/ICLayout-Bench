"""Prepare and evaluate published case witnesses without a model account."""

import argparse
import ipaddress
import json
import os
import platform
import shlex
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import benchmarking
from benchmarking.dataset import (
    Dataset,
    case_location,
    load_dataset,
    process_manifest,
)

CODE_ROOT = Path(benchmarking.__file__).resolve().parents[1]
ROOT = None
IMAGE = "iclayout-bench-tools:local"
RUNS = "build/runs"

def call(*command, expected=0, log=None):
    arguments = [str(arg) for arg in command]
    print("+ " + shlex.join(arguments), flush=True)
    if log is None:
        result = subprocess.run(arguments, cwd=CODE_ROOT, check=False)
    else:
        with log.open("w") as stream:
            result = subprocess.run(arguments, cwd=CODE_ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
    if result.returncode != expected:
        details = f"Inspect {log}." if log else "See the output above."
        raise RuntimeError(f"Step exited {result.returncode}; expected {expected}. {details}")


def python(*arguments, **options):
    call(sys.executable, *arguments, **options)


def new_directory(path):
    path = path.absolute()
    if path.exists() or path.is_symlink():
        raise ValueError(f"Output already exists: {path}. Choose a new --output directory; existing evidence is retained.")
    path.mkdir(parents=True, mode=0o700)
    return path


def doctor():
    if sys.version_info < (3, 12) or platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise ValueError("The preview requires Linux x86-64 and Python 3.12+. See README.md for the supported environment.")
    call("git", "--version")
    call("docker", "version", "--format", "{{.Server.Version}}")
    print("Host prerequisites OK.", flush=True)


def _proxy_hostname(value):
    """Return a proxy hostname from a URL or a host:port value."""
    if not value:
        return None
    candidate = value if "://" in value else f"//{value}"
    try:
        return urlparse(candidate).hostname
    except ValueError:
        return None


def _loopback_proxy_variables():
    variables = []
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(name)
        hostname = _proxy_hostname(value)
        if hostname == "localhost":
            variables.append(name)
            continue
        try:
            if hostname and ipaddress.ip_address(hostname).is_loopback:
                variables.append(name)
        except ValueError:
            pass
    return variables


def _check_build_network(network):
    if network != "default":
        return
    variables = _loopback_proxy_variables()
    if variables:
        names = ", ".join(variables)
        raise ValueError(
            f"{names} point to a loopback proxy, which the default Docker build network cannot reach. "
            "Rerun with --network host, or unset the proxy variables if direct access is allowed.")


def build(image, network):
    _check_build_network(network)
    call("docker", "build", "--network", network, "--build-arg", "HTTP_PROXY", "--build-arg", "HTTPS_PROXY",
         "--build-arg", "NO_PROXY", "--target", "tools", "-t", image, ".")


def _git_metadata(path):
    metadata = path / ".git"
    return metadata.is_dir() or metadata.is_file()


def _evaluation_mode(case_path, case):
    """Read a task's mode without requiring candidate cases to be executable."""
    task = case.get("task")
    if not isinstance(task, dict):
        return None
    evaluation = task.get("evaluation")
    if isinstance(evaluation, dict):
        return evaluation.get("mode")
    inputs = task.get("inputs")
    entry = inputs.get("evaluation") if isinstance(inputs, dict) else None
    if not isinstance(entry, dict):
        return None
    relative = entry.get("source", entry.get("path"))
    if not isinstance(relative, str):
        return None
    plan_path = case_path.parent / relative
    try:
        raw = plan_path.read_bytes()
        if entry.get("format", "text") == "json":
            return json.loads(raw).get("mode")
        return tomllib.loads(raw.decode("utf-8")).get("mode")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, json.JSONDecodeError):
        return None


def _case_records():
    """Read published task metadata from the selected Dataset."""
    if not (ROOT / "tasks").is_dir():
        return []
    records = []
    for name, case_path in Dataset(ROOT, {}).cases().items():
        case = tomllib.loads(case_path.read_text())
        location = case_location(case_path)
        records.append({
            "id": name, "key": case_path.parent.name,
            "collection": location["collection"],
            "process": location["process"], "config": case_path,
            "path": case_path.parent, "data": case,
        })
    return records


def discover_cases():
    """Return executable post-layout public cases suitable for local preview.

    Local preview does not establish qualification or formal admission.
    """
    all_records = _case_records()
    records = [record for record in all_records
               if record["data"].get("status") in {"candidate", "qualified"}
               and isinstance(record["data"].get("task"), dict)
               and record["data"].get("qualification", {}).get("reference")
               and _evaluation_mode(record["config"], record["data"]) == "post_layout"]
    # Include candidates in the collision count so a later promotion cannot
    # change the meaning of an already published CLI key.
    counts = Counter(record["key"] for record in all_records)
    result = {}
    for record in records:
        key = record["key"] if counts[record["key"]] == 1 else _qualified_key(record)
        result[key] = {**record, "preview_key": key}
    return result


def _qualified_key(record):
    return f'{record["process"]}/{record["collection"]}/{record["key"]}'


def _resolve_case(case):
    """Resolve a preview case by its CLI key, case ID, or unique directory name."""
    case = str(case)
    records = _case_records()
    counts = Counter(record["key"] for record in records)
    matches = []
    for record in records:
        aliases = {record["id"], str(record["config"]), str(record["path"])}
        if counts[record["key"]] == 1:
            aliases.add(record["key"])
        aliases.add(f'{record["collection"]}/{record["key"]}')
        aliases.add(_qualified_key(record))
        if case in aliases:
            matches.append(record)
    if len(matches) == 1:
        return {**matches[0], "preview_key": case}
    if matches:
        raise ValueError(f"Ambiguous public case {case!r}; use " + ", ".join(_qualified_key(r) for r in matches))
    choices = ", ".join(sorted(discover_cases()))
    raise ValueError(f"Unknown public case {case!r}; available post-layout cases: {choices or 'none'}")


def _executable_case(case):
    record = _resolve_case(case)
    data = record["data"]
    if not data.get("qualification", {}).get("reference"):
        raise ValueError("The preview requires a published witness; use 'list' to select an executable case")
    if (data.get("status") not in {"candidate", "qualified"}
            or _evaluation_mode(record["config"], data) != "post_layout"):
        raise ValueError("The preview requires an executable case with post-layout evaluation")
    return record


def ensure_case_pdks(case):
    from benchmarking.engine.pdk_installation import prepare_installation
    from benchmarking.engine.preparation import case_resources
    from benchmarking.engine.prepare_support import load_profile

    record = _executable_case(case)
    manifest = process_manifest(record["config"])
    prepare_installation(tomllib.loads(manifest.read_text())["source"])
    for *_, spec, _ in case_resources(record["config"], ROOT):
        prepare_installation(json.loads(load_profile(spec).content)["source"])


def run(case, output, image=IMAGE):
    from benchmarking.engine.evaluate import run_evaluation
    from benchmarking.engine.runtime import load_case

    record = _executable_case(case)
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    runtime = load_case(record["config"], image=image, include_agent=False)
    witness = runtime.witness()
    report = run_evaluation(runtime.task.evaluation,
                            {**runtime.task.evaluation_inputs(), "candidate": witness},
                            runtime.backends, output / "reference", task_sha256=runtime.task.digest,
                            task_witnessed=runtime.task.witnessed)
    if report["outcome"] != "passed" or report["task_success"] is not True:
        raise ValueError("The case witness did not pass its complete evaluation")
    (output / "preview.json").write_text(json.dumps({"run_kind": "public_case_reference",
        "task": runtime.task.id, "reference": "passed", "model_called": False}, indent=2) + "\n")
    print(f"PASS: {runtime.task.id}; report: {output / 'reference/report.json'}")


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", help="HF Dataset repo ID or local Dataset working copy")
    parser.add_argument("--revision", help="HF dataset revision")
    parser.add_argument("--offline", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("list")
    command = commands.add_parser("fetch", help="Fetch pinned PDK installations")
    command.add_argument("--case", required=True)
    command = commands.add_parser("build", help="Build tools from the evaluator source checkout")
    command.add_argument("--image", default=IMAGE)
    command.add_argument("--network", default="default", choices=("default", "host"))
    command = commands.add_parser("run", help="Evaluate a Dataset witness without creating a prepared case")
    command.add_argument("--case", required=True)
    command.add_argument("--image", default=IMAGE)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            doctor()
        elif args.command == "build":
            doctor()
            build(args.image, args.network)
        else:
            dataset = load_dataset(args.dataset, revision=args.revision, local_files_only=args.offline,
                                   include_reference=args.command == "run")
            ROOT = dataset.root
            if args.command == "list":
                for key, record in discover_cases().items():
                    print(f"{key}\t{record['data']['status']}\t{record['id']}")
            elif args.command == "fetch":
                ensure_case_pdks(args.case)
            else:
                run(args.case, args.output.absolute(), args.image)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"Dataset operation stopped: {error}\n")


if __name__ == "__main__":
    main()
