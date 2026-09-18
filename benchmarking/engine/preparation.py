"""Assemble public case snapshots from declared, verified process resources."""

import configparser
import json
import re
import subprocess
import tomllib
from pathlib import Path

import tomli_w

from benchmarking.files import Asset, read_file, relative
from benchmarking.tasks import load_task

from . import prepare_support

BACKEND_SUPPORT_PROFILES = {
    "klayout-docker": "klayout",
    "magic-capacitance-docker": "magic",
    "magic-rc-docker": "magic",
}


def support_bindings(backend_name, backend):
    settings = backend["settings"]
    names = {name for name in settings if name == "support" or name.endswith("_support")}
    declared = backend.get("support_profiles")
    if declared is not None:
        if not isinstance(declared, dict) or not declared:
            raise ValueError(f"Backend {backend_name!r} support_profiles must be a nonempty table")
        if set(declared) != names:
            raise ValueError(f"Backend {backend_name!r} support_profiles does not match support settings")
        if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value)
               for value in declared.values()):
            raise ValueError(f"Backend {backend_name!r} support_profiles values must be profile names")
        return [(name, declared[name]) for name in sorted(names)]
    if not names:
        return []
    profile = BACKEND_SUPPORT_PROFILES.get(backend["type"])
    if profile is None:
        raise ValueError(f"Backend {backend_name!r} ({backend['type']}) declares support settings "
                         "but no support_profiles metadata")
    return [(name, profile) for name in sorted(names)]


def source_path(root, source):
    """Resolve a pinned cache path or declared public submodule without fetching."""
    if source.get("kind") == "ciel":
        from .pdk_installation import installation_path

        return installation_path(source)
    submodules = configparser.ConfigParser(interpolation=None)
    submodules.read(root / ".gitmodules")
    entries = [dict(submodules[section]) for section in submodules.sections()]
    if "checkout" in source:
        checkout = relative(source["checkout"], "PDK checkout")
        matches = [entry for entry in entries if entry.get("path") == checkout]
    else:
        repository = source["repository"].removesuffix(".git")
        matches = [entry for entry in entries if entry.get("url", "").removesuffix(".git") == repository]
    if len(matches) != 1:
        raise ValueError(f"Expected one declared submodule for PDK source: {source}")
    return root / relative(matches[0]["path"], "PDK checkout")


def case_resources(case, root):
    """Return backend setting, profile specification, and pinned source path."""
    data = tomllib.loads(case.read_text())
    manifest = case.parents[3] / "pdk.toml"
    bindings = []
    for name, backend in data["toolchain"]["backends"].items():
        for setting, profile in support_bindings(name, backend):
            spec = f"{manifest}#{profile}"
            source = json.loads(prepare_support.load_profile(spec).content)["source"]
            bindings.append((name, setting, profile, spec, source_path(root, source)))
    return bindings


def prepare_case(case: Path, destination: Path, *, root: Path, image: str) -> Path:
    """Prepare evaluator inputs without consulting any previous build directory.

    Git initialization and image builds belong to the public CLI. Prebuilt PDKs
    use the shared verified download cache. Catalog regressions use this same
    assembly rather than repairing bindings through a separate preparation path.
    """
    case, destination = case.absolute(), destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Output already exists: {destination}")
    data = tomllib.loads(case.read_text())
    task = load_task(case)
    if (data["status"] not in {"candidate", "qualified"} or task.evaluation is None
            or task.evaluation.mode != "post_layout"):
        raise ValueError("The preview requires an executable case with post-layout evaluation")
    reference = data.get("qualification", {}).get("reference")
    if reference is None:
        raise ValueError("The preview requires an executable case with a published witness; this case declares none")
    witness = Asset(read_file(case.parent, reference), "gds")
    for asset in data.get("assets", []):
        if asset["path"] == reference and witness.sha256 != asset["sha256"]:
            raise ValueError("Reference witness checksum mismatch")
    bindings = case_resources(case, root)
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    destination.mkdir(parents=True, mode=0o700)
    prepared = {}
    for name, setting, profile, spec, checkout in bindings:
        if spec not in prepared:
            output = destination / profile
            print(f"Preparing {profile} from {checkout}", flush=True)
            prepare_support.prepare_support(checkout, spec, output, compiler_image=image_id)
            prepared[spec] = str(output)
        data["toolchain"]["backends"][name]["settings"][setting] = prepared[spec]
    for backend in data["toolchain"]["backends"].values():
        if "image" in backend["settings"]:
            backend["settings"]["image"] = image_id
    task.materialize(destination / "case")
    for entry in data["task"]["inputs"].values():
        entry.pop("source", None)
        entry.pop("collection_source", None)
    bound = destination / "case/case.toml"
    bound.write_text(tomli_w.dumps(data))
    for name in (reference, data["qualification"]["evidence"]):
        target = bound.parent / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_file(case.parent, name))
    return bound
