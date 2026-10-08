"""Read host tool declarations without importing or initializing EDA backends."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from benchmarking.evaluation.contracts import identifier
from benchmarking.files import keys, read_file, text


def support_bindings(backend_name, backend, *, require_declared=True):
    """Validate the mapping from support settings to declared resource profiles."""
    settings = backend["settings"]
    names = {name for name in settings if name == "support" or name.endswith("_support")}
    declared = backend.get("support_profiles")
    if declared is None:
        if names and require_declared:
            raise ValueError(f"Backend {backend_name!r} ({backend['type']}) declares support settings "
                             "but no support_profiles metadata")
        return ()
    if not isinstance(declared, dict) or not declared:
        raise ValueError(f"Backend {backend_name!r} support_profiles must be a nonempty table")
    if set(declared) != names:
        raise ValueError(f"Backend {backend_name!r} support_profiles does not match support settings")
    for setting, profile in declared.items():
        identifier(setting)
        identifier(profile)
    return tuple((setting, declared[setting]) for setting in sorted(names))


@dataclass(frozen=True)
class BackendSpec:
    type: str
    settings: dict
    support_profiles: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ToolchainSpec:
    path: Path
    embedded: bool
    backends: dict[str, BackendSpec]
    bindings: dict[str, str]


def load_toolchain_spec(config: Path, *, require_declared=False) -> ToolchainSpec:
    path = Path(config).absolute()
    data = tomllib.loads(read_file(path.parent, path.name).decode("utf-8"))
    embedded = "kind" in data
    if embedded:
        if data["kind"] != "layout_case":
            raise ValueError("Embedded toolchains require a layout_case; supply --toolchain")
        if "toolchain" not in data:
            raise ValueError("Case does not declare a toolchain; supply --toolchain")
        data = data["toolchain"]
    keys(data, {"backends", "bindings"}, set(), "toolchain")
    if not isinstance(data["backends"], dict) or not isinstance(data["bindings"], dict):
        raise TypeError("Toolchain backends and bindings must be tables")
    backends = {}
    for name, entry in data["backends"].items():
        keys(entry, {"type", "settings"}, {"support_profiles"}, f"backend {name}")
        text(entry["type"], "backend type")
        if not isinstance(entry["settings"], dict):
            raise TypeError(f"Backend {name} settings must be a table")
        backends[name] = BackendSpec(entry["type"], entry["settings"],
                                    support_bindings(name, entry, require_declared=require_declared))
    if not all(isinstance(value, str) and value in backends for value in data["bindings"].values()):
        raise ValueError("Toolchain binding references an unknown backend")
    return ToolchainSpec(path, embedded, backends, data["bindings"])
