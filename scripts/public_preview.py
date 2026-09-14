"""Prepare and evaluate published SG13G2 case witnesses without a model account."""

import argparse
import ipaddress
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tomllib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
# These defaults cover the legacy KLayout and Magic settings already present
# in published cases.  Model and composite extraction support must be named by
# the case's explicit ``support_profiles`` metadata below.
BACKEND_SUPPORT_PROFILES = {
    "klayout-docker": "klayout",
    "magic-capacitance-docker": "magic",
    "magic-rc-docker": "magic",
}
IMAGE = "layout-bench-tools:local"
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
    """Return public SG13G2 catalogs in stable order."""
    return sorted((ROOT / "tasks" / "ihp-sg13g2").glob("*/catalog.toml"))


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
               and _evaluation_mode(record["config"], record["data"]) == "post_layout"]
    # Include candidates in the collision count so a later promotion cannot
    # change the meaning of an already published CLI key.
    counts = Counter(record["key"] for record in all_records)
    result = {}
    for record in records:
        key = record["key"] if counts[record["key"]] == 1 else f'{record["collection"]}/{record["key"]}'
        result[key] = {**record, "preview_key": key}
    return result


def _resolve_case(case):
    """Resolve a preview case by its CLI key, case ID, or unique directory name."""
    case = str(case)
    records = _case_records()
    counts = Counter(record["key"] for record in records)
    for record in records:
        aliases = {record["id"], str(record["config"]), str(record["path"])}
        if counts[record["key"]] == 1:
            aliases.add(record["key"])
        aliases.add(f'{record["collection"]}/{record["key"]}')
        if case in aliases:
            return {**record, "preview_key": case}
    choices = ", ".join(sorted(discover_cases()))
    raise ValueError(f"Unknown public case {case!r}; available post-layout cases: {choices or 'none'}")


def _support_bindings(backend_name, backend):
    """Return ``(settings_key, pdk_profile)`` bindings for one backend.

    ``support`` and ``*_support`` settings are host-side paths.  A case may
    declare the reviewed manifest profile for each such setting in the
    backend-level ``support_profiles`` table.  The small type map remains for
    the historical KLayout/Magic cases, while model and composite backends
    must carry explicit metadata.
    """
    settings = backend["settings"]
    support_settings = tuple(sorted(name for name in settings
                                    if name == "support" or name.endswith("_support")))
    declared = backend.get("support_profiles")
    if declared is not None:
        if not isinstance(declared, dict) or not declared:
            raise ValueError(f"Backend {backend_name!r} support_profiles must be a nonempty table")
        if set(declared) != set(support_settings):
            missing = sorted(set(support_settings) - set(declared))
            extra = sorted(set(declared) - set(support_settings))
            detail = []
            if missing:
                detail.append(f"missing {missing}")
            if extra:
                detail.append(f"unknown {extra}")
            raise ValueError(f"Backend {backend_name!r} support_profiles does not match support settings ({'; '.join(detail)})")
        if any(not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", profile)
               for profile in declared.values()):
            raise ValueError(f"Backend {backend_name!r} support_profiles values must be profile names")
        return [(name, declared[name]) for name in support_settings]
    if not support_settings:
        return []
    profile = BACKEND_SUPPORT_PROFILES.get(backend["type"])
    if profile is None:
        raise ValueError(f"Backend {backend_name!r} ({backend['type']}) declares support settings but no support_profiles metadata")
    return [(name, profile) for name in support_settings]


def prepare(destination, image=IMAGE, case="comparator"):
    from benchmarking.environment import prepare_pdk_bundle
    from benchmarking.files import Asset, read_file
    from benchmarking.prepare_support import prepare_support
    from benchmarking.tasks import load_task

    record = _resolve_case(case)
    source = record["path"]
    config = read_file(source, "case.toml").decode()
    data = tomllib.loads(config)
    task = load_task(source / "case.toml")
    if data["status"] not in {"candidate", "qualified"} or task.evaluation.mode != "post_layout":
        raise ValueError("The preview requires an executable case with post-layout evaluation")
    reference = data.get("qualification", {}).get("reference")
    if reference is None:
        raise ValueError("The preview requires an executable case with a published witness; "
                         "this case declares none")
    witness = Asset(read_file(source, reference), "gds")
    for asset in data.get("assets", []):
        if asset["path"] == reference and witness.sha256 != asset["sha256"]:
            raise ValueError("Reference witness checksum mismatch")
    pdk = ROOT / PDK_PATH
    if not (pdk / "ihp-sg13g2").is_dir():
        raise ValueError("PDK missing. Run quickstart, or initialize it with: "
                         "git submodule update --init --depth 1 third_party/IHP-Open-PDK")
    image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    destination = new_directory(destination)
    prepare_pdk_bundle(pdk, destination / "agent-resources")
    prepared = set()
    for backend_name, backend in data["toolchain"]["backends"].items():
        settings = backend["settings"]
        config = config.replace(json.dumps(settings["image"]), json.dumps(image_id))
        for setting, profile in _support_bindings(backend_name, backend):
            if profile not in prepared:
                print(f"Preparing {profile} from the reviewed PDK files", flush=True)
                prepare_support(pdk, f"{ROOT}/tasks/ihp-sg13g2/pdk.toml#{profile}", destination / profile,
                                compiler_image=image_id)
                prepared.add(profile)
            config = config.replace(json.dumps(settings[setting]), json.dumps(str(destination / profile)))
    # Host-side assembly: the solver loader still delivers only task.inputs.
    task.materialize(destination / "case")
    # The prepared case reads the materialized snapshots, not the source collection.
    prepared_data = tomllib.loads(config)
    if any("source" in entry or "collection_source" in entry
           for entry in prepared_data["task"]["inputs"].values()):
        import tomli_w

        for entry in prepared_data["task"]["inputs"].values():
            entry.pop("source", None)
            entry.pop("collection_source", None)
        config = tomli_w.dumps(prepared_data)
    bound_case = destination / "case/case.toml"
    bound_case.write_text(config)
    target = bound_case.parent / reference
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(witness.content)
    evidence = data["qualification"]["evidence"]
    target = bound_case.parent / evidence
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(read_file(source, evidence))
    print(f"Prepared case ({task.status}): {bound_case}", flush=True)


def run(prepared, output):
    from benchmarking.tasks import load_task

    config = prepared.absolute() / "case/case.toml"
    task = load_task(config)
    data = tomllib.loads(config.read_text())
    reference = config.parent / data["qualification"]["reference"]
    output = new_directory(output)
    python(ROOT / "main.py", "evaluate", config, reference,
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
    doctor()
    if not skip_build:
        _check_build_network(network)
    output = new_directory(output or ROOT / RUNS / datetime.now(UTC).strftime("preview-%Y%m%dT%H%M%S%fZ"))
    print(f"Preview directory: {output}", flush=True)
    if not skip_build:
        build(image, network)
    ensure_pdk()
    prepare(output / "prepared", image, case)
    run(output / "prepared", output / "run")
    print(f"Reviewed solver resources: {output / 'prepared/agent-resources'}\n"
          f"Prepared case: {output / 'prepared/case/case.toml'}", flush=True)


def _case_choices():
    """Return CLI choices without making inventory-only cases executable."""
    return tuple(sorted(discover_cases()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check the supported host and Docker access")
    choices = _case_choices()
    default_case = "comparator" if "comparator" in choices else choices[0] if choices else None
    for name, help_text in (("quickstart", "Build one image, fetch the pinned PDK, prepare resources and run no-key checks"),
                            ("build", "Build the unified public tool image; downloads required")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--image", default=IMAGE, help="Tool image tag (default: %(default)s)")
        command.add_argument("--network", choices=("default", "host"), default="default", help="Build network; host can reach local proxy services")
        if name == "quickstart":
            command.add_argument("--output", type=Path, help=f"New directory; default is a timestamped directory under {RUNS}")
            command.add_argument("--case", choices=choices, default=default_case)
            command.add_argument("--skip-build", action="store_true", help="Use an already available --image; still prepare and verify fresh resources")
    preparation = commands.add_parser("prepare", help="Create reviewed PDK/tool bundles in a new directory")
    preparation.add_argument("--output", type=Path, default=ROOT / RUNS / "preview/prepared")
    preparation.add_argument("--image", default=IMAGE)
    preparation.add_argument("--case", choices=choices, default=default_case)
    command = commands.add_parser("run", help="Evaluate the prepared case witness with its complete declared plan")
    command.add_argument("--prepared", type=Path, default=ROOT / RUNS / "preview/prepared")
    command.add_argument("--output", type=Path, required=True, help="New directory for reports; existing evidence is never overwritten")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            doctor()
        elif args.command == "build":
            doctor()
            build(args.image, args.network)
        elif args.command == "quickstart":
            quickstart(args.output, args.image, args.network, args.skip_build, args.case)
        elif args.command == "prepare":
            prepare(args.output, args.image, args.case)
        else:
            run(args.prepared.absolute(), args.output)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"Public preview stopped: {error}\n")


if __name__ == "__main__":
    main()
