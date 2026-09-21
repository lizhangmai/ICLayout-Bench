"""Resolve declared backend profiles to pinned process resources."""

import json
import re
import tomllib

from benchmarking.dataset import process_manifest

from . import prepare_support


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
    raise ValueError(f"Backend {backend_name!r} ({backend['type']}) declares support settings "
                     "but no support_profiles metadata")


def source_path(root, source):
    """Resolve a pinned cache path without fetching."""
    from .pdk_installation import installation_path

    return installation_path(source)


def case_resources(case, root):
    """Return backend setting, profile specification, and pinned source path."""
    data = tomllib.loads(case.read_text())
    manifest = process_manifest(case)
    bindings = []
    for name, backend in data["toolchain"]["backends"].items():
        for setting, profile in support_bindings(name, backend):
            spec = f"{manifest}#{profile}"
            source = json.loads(prepare_support.load_profile(spec).content)["source"]
            bindings.append((name, setting, profile, spec, source_path(root, source)))
    return bindings
