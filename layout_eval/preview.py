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
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import benchmarking

ROOT = Path(benchmarking.__file__).resolve().parents[1]
IMAGE = "iclayout-bench-tools:local"
RUNS = "build/runs"
PDK_PATH = Path("third_party/IHP-Open-PDK")

# The public PDK contains several optional nested submodules.  The reviewed
# view only consumes the two Python libraries below; initializing the complete
# recursive tree is both unnecessary and fragile when a checkout already has
# unpacked (but untracked) optional directories.
PDK_REQUIRED_SUBMODULES = {
    Path("ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api"):
        Path("source/python/cni/box.py"),
    Path("ihp-sg13g2/libs.tech/klayout/python/pypreprocessor"):
        Path("pypreprocessor/__init__.py"),
}


def call(*command, expected=0, log=None):
    arguments = [str(arg) for arg in command]
    print("+ " + shlex.join(arguments), flush=True)
    if log is None:
        result = subprocess.run(arguments, cwd=ROOT, check=False)
    else:
        with log.open("w") as stream:
            result = subprocess.run(arguments, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
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


def ensure_pdk():
    """Initialize only the pinned PDK and nested libraries used by the view.

    A populated directory without Git metadata is common in source archives
    and cached workspaces.  Git cannot clone a submodule over such a directory,
    so reuse it when the reviewed files are present and let ``prepare`` verify
    every byte.  An empty directory is a normal uninitialized submodule and
    can be cloned into.  A non-empty incomplete directory is rejected before
    Git is invoked so the user gets a recovery path instead of Git's clone error.
    """
    pdk = ROOT / PDK_PATH
    if not pdk.is_dir() or _git_metadata(pdk) or not any(pdk.iterdir()):
        # This is intentionally not recursive: optional nested PDK projects
        # are not part of the reviewed public view.
        call("git", "submodule", "update", "--init", "--depth", "1", str(PDK_PATH))
    if not pdk.is_dir():
        raise ValueError(f"PDK checkout missing after initialization: {pdk}. "
                         f"Run: git submodule update --init --depth 1 {PDK_PATH}")
    if not _git_metadata(pdk) and any(
            not (pdk / relative / marker).is_file()
            for relative, marker in PDK_REQUIRED_SUBMODULES.items()):
        raise ValueError(
            f"PDK checkout {pdk} has no Git metadata and is missing files required by the reviewed view. "
            f"Use a Git checkout, then run: git submodule update --init --depth 1 {PDK_PATH}")

    missing = []
    for relative, marker in PDK_REQUIRED_SUBMODULES.items():
        path = pdk / relative
        if (path / marker).is_file():
            continue
        if path.is_dir() and any(path.iterdir()) and not _git_metadata(path):
            command = (f"git -C {PDK_PATH} submodule update --init --depth 1 "
                       f"{relative}")
            raise ValueError(
                f"Required PDK dependency {relative} is a non-empty directory without Git metadata "
                f"and is incomplete. Move it aside (preserving any local files), then run: {command}")
        missing.append(str(relative))
    if missing:
        call("git", "-C", pdk, "submodule", "update", "--init", "--depth", "1", *missing)
    incomplete = [str(relative) for relative, marker in PDK_REQUIRED_SUBMODULES.items()
                  if not (pdk / relative / marker).is_file()]
    if incomplete:
        command = f"git -C {PDK_PATH} submodule update --init --depth 1 {' '.join(incomplete)}"
        raise ValueError(f"Required PDK files are still missing: {', '.join(incomplete)}. Run: {command}")


def _catalog_paths():
    """Return public catalogs across all processes in stable order."""
    return sorted((ROOT / "tasks").glob("*/*/catalog.toml"))


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
    if "collection_source" in entry:
        from benchmarking.tasks import load_task

        try:
            plan = load_task(case_path).evaluation
            return plan.mode if plan else None
        except (OSError, ValueError, TypeError):
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
    """Read catalog case metadata, including records still under development."""
    records = []
    for catalog_path in _catalog_paths():
        catalog = tomllib.loads(catalog_path.read_text())
        for entry in catalog.get("cases", []):
            case_path = catalog_path.parent / entry["config_path"]
            case = tomllib.loads(case_path.read_text())
            records.append({
                "id": entry["id"],
                "key": case_path.parent.name,
                "collection": catalog_path.parent.name,
                "process": catalog_path.parent.parent.name,
                "catalog": catalog_path,
                "config": case_path,
                "path": case_path.parent,
                "data": case,
            })
    return records


def discover_cases():
    """Return executable post-layout public cases suitable for local preview.

    Inventory candidates without a task or post-layout plan stay discoverable
    through the catalogs but are intentionally absent from the preview CLI.
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
        # Preserve the original quick-start name after other processes add comparators.
        if _qualified_key(record) == "ihp-sg13g2/IHP-AnalogAcademy/comparator":
            aliases.add("comparator")
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


def ensure_case_pdks(case, *, initialized=None):
    from layout_eval.pdk_resources import agent_sources
    from layout_eval.preparation import case_resources

    record = _executable_case(case)
    checkouts = {binding[-1] for binding in case_resources(record["config"], ROOT)}
    sources = agent_sources(record["config"].parents[3] / "pdk.toml", ROOT)
    checkouts.update(path for path, _ in sources)
    initialized = set() if initialized is None else initialized
    for checkout, source in sources:
        required = [checkout, *(checkout / path for path in source.get("submodules", []))] if source else []
        for path in required:
            if path.is_dir() and any(path.iterdir()) and not _git_metadata(path):
                raise ValueError(f"Agent PDK sources require Git metadata: {path}. "
                                 "Preserve this source archive elsewhere, then rerun fetch to initialize the pinned checkout.")
    for checkout in sorted(checkouts - initialized):
        if not checkout.is_dir() or _git_metadata(checkout) or not any(checkout.iterdir()):
            call("git", "submodule", "update", "--init", "--depth", "1", checkout.relative_to(ROOT))
        # Populated source archives are verified file-by-file during preparation.
        initialized.add(checkout)
    for checkout, source in sources:
        nested = [path for path in source.get("submodules", []) if checkout / path not in initialized]
        if nested:
            call("git", "-C", checkout, "submodule", "update", "--init", "--depth", "1", *nested)
            initialized.update(checkout / path for path in nested)


def prepare(destination, image=IMAGE, case="comparator"):
    from benchmarking.tasks import load_task
    from layout_eval.pdk_resources import prepare_agent_resources
    from layout_eval.preparation import prepare_case

    record = _executable_case(case)
    bound_case = prepare_case(record["config"], destination, root=ROOT, image=image)
    prepare_agent_resources(record["config"].parents[3] / "pdk.toml", destination / "agent-resources",
                            root=ROOT, prepared=destination, image=image)
    task = load_task(bound_case)
    print(f"Prepared case ({task.status}): {bound_case}", flush=True)


def run(prepared, output):
    from benchmarking.tasks import load_task

    config = prepared.absolute() / "case/case.toml"
    task = load_task(config)
    data = tomllib.loads(config.read_text())
    reference = config.parent / data["qualification"]["reference"]
    output = new_directory(output)
    python("-m", "layout_eval.cli", "evaluate", config, reference,
           "--output", output / "reference", log=output / "reference.log")
    report = json.loads((output / "reference/report.json").read_text())
    if report["outcome"] != "passed" or report["task_success"] is not True:
        raise ValueError("The case witness did not pass its complete evaluation")
    summary = {"run_kind": "public_case_reference", "task": task.id,
               "reference": "passed", "model_called": False}
    (output / "preview.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS: {task.id} reference passed its declared evaluation. No model was called. "
          f"Report: {output / 'reference/report.json'}")


def quickstart(output, image, network, skip_build, case="comparator"):
    _executable_case(case)
    doctor()
    if not skip_build:
        _check_build_network(network)
    output = new_directory(output or ROOT / RUNS / datetime.now(UTC).strftime("preview-%Y%m%dT%H%M%S%fZ"))
    print(f"Preview directory: {output}", flush=True)
    if not skip_build:
        build(image, network)
    ensure_case_pdks(case)
    prepare(output / "prepared", image, case)
    run(output / "prepared", output / "run")
    resources = output / "prepared/agent-resources"
    if resources.is_dir():
        print(f"Reviewed solver resources: {resources}", flush=True)
    print(f"Prepared case: {output / 'prepared/case/case.toml'}", flush=True)


def _case_choices():
    """Return CLI choices without making inventory-only cases executable."""
    return tuple(sorted(discover_cases()))


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-root", type=Path, help="Public source catalog checkout (defaults to the installed source checkout)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check the supported host and Docker access")
    commands.add_parser("list", help="List every executable public witness and its process")
    fetch = commands.add_parser("fetch", help="Initialize the pinned upstream resources without building or evaluating")
    selection = fetch.add_mutually_exclusive_group()
    selection.add_argument("--case", default="comparator", help="Case key or ID (default: comparator)")
    selection.add_argument("--all", action="store_true", help="Fetch resources for every executable public witness")
    choices = None
    default_case = "comparator"
    for name, help_text in (("quickstart", "Build one image, fetch the pinned PDK, prepare resources and run no-key checks"),
                            ("build", "Build the unified public tool image; downloads required")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--image", default=IMAGE, help="Tool image tag (default: %(default)s)")
        command.add_argument("--network", choices=("default", "host"), default="default", help="Build network; host can reach local proxy services")
        if name == "quickstart":
            command.add_argument("--output", type=Path, help=f"New directory; default is a timestamped directory under {RUNS}")
            command.add_argument("--case", default=default_case, help="Case key or ID; use 'list' to discover cases")
            command.add_argument("--skip-build", action="store_true", help="Use an already available --image; still prepare and verify fresh resources")
    preparation = commands.add_parser("prepare", help="Create reviewed PDK/tool bundles in a new directory")
    preparation.add_argument("--output", type=Path, default=ROOT / RUNS / "preview/prepared")
    preparation.add_argument("--image", default=IMAGE)
    preparation.add_argument("--case", default=default_case, help="Case key or ID; use 'list' to discover cases")
    command = commands.add_parser("run", help="Evaluate the prepared case witness with its complete declared plan")
    command.add_argument("--prepared", type=Path, default=ROOT / RUNS / "preview/prepared")
    command.add_argument("--output", type=Path, required=True, help="New directory for reports; existing evidence is never overwritten")
    args = parser.parse_args()
    if args.public_root is not None:
        ROOT = args.public_root.resolve()
    try:
        if args.command in {"list", "fetch"}:
            choices = _case_choices()
        if args.command == "doctor":
            doctor()
        elif args.command == "list":
            records = discover_cases()
            for key in choices:
                record = records[key]
                print(f"{key}\t{record['process']}\t{record['data']['status']}\t{record['id']}")
        elif args.command == "fetch":
            initialized = set()
            for case in choices if args.all else (args.case,):
                ensure_case_pdks(case, initialized=initialized)
        elif args.command == "build":
            doctor()
            build(args.image, args.network)
        elif args.command == "quickstart":
            quickstart(args.output, args.image, args.network, args.skip_build, args.case)
        elif args.command == "prepare":
            if args.output.exists() or args.output.is_symlink():
                raise ValueError(f"Output already exists: {args.output}")
            ensure_case_pdks(args.case)
            prepare(args.output, args.image, args.case)
        else:
            run(args.prepared.absolute(), args.output)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"Public preview stopped: {error}\n")


if __name__ == "__main__":
    main()
