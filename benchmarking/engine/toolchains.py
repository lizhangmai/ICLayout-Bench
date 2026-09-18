"""Bind trusted evaluator tools from a standalone config or a circuit case."""

import tomllib
from collections.abc import Callable
from pathlib import Path

from benchmarking.evaluation import identifier
from benchmarking.files import keys, read_file

from .evaluate import Backend
from .geometry import KLayoutGeometryDocker
from .hbt import SG13G2HBTRCDocker
from .klayout import KLayoutDocker
from .kpex import SG13G2KpexCCDocker
from .magic import MagicCapacitanceDocker, MagicRCDocker
from .ngspice import NgspiceDocker


def load_toolchain(config: Path, *, factories: dict[str, Callable[..., Backend]] | None = None) -> dict[str, Backend]:
    """Bind operations using trusted factories; never import code named by a task.

    Python callers can supply additional factories without changing evaluation.
    Read either a schema-1 toolchain or the [toolchain] table of a schema-2
    layout_case. Backend settings retain their existing path semantics.  The
    optional backend-level ``support_profiles`` table is host metadata: it is
    validated here and deliberately omitted from backend constructor kwargs.
    Toolchain configuration is never a solver input.
    """
    config = config.absolute()
    data = tomllib.loads(read_file(config.parent, config.name).decode("utf-8"))
    if "kind" in data:
        if data["kind"] != "layout_case" or type(data.get("schema_version")) is not int or data["schema_version"] != 2:
            raise ValueError("Embedded toolchains require a schema-2 layout_case; supply --toolchain")
        if "toolchain" not in data:
            raise ValueError("Case does not declare a toolchain; supply --toolchain")
        data = data["toolchain"]
    keys(data, {"schema_version", "backends", "bindings"}, set(), "toolchain")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported toolchain schema_version")
    if not isinstance(data["backends"], dict) or not isinstance(data["bindings"], dict):
        raise TypeError("Toolchain backends and bindings must be tables")
    factories = {"ngspice-docker": NgspiceDocker,
                 "magic-capacitance-docker": MagicCapacitanceDocker,
                 "magic-rc-docker": MagicRCDocker,
                 "sg13g2-hbt-rc-docker": SG13G2HBTRCDocker,
                 "klayout-docker": KLayoutDocker,
                 "sg13g2-kpex-cc-docker": SG13G2KpexCCDocker,
                 "klayout-geometry-docker": KLayoutGeometryDocker} if factories is None else factories
    for name, config_data in data["backends"].items():
        keys(config_data, {"type", "settings"}, {"support_profiles"}, f"backend {name}")
        if config_data["type"] not in factories or not isinstance(config_data["settings"], dict):
            raise ValueError(f"Unknown or invalid backend: {name}")
        _validate_support_profiles(name, config_data)
    if not all(isinstance(value, str) and value in data["backends"] for value in data["bindings"].values()):
        raise ValueError("Toolchain binding references an unknown backend")
    instances = {name: factories[entry["type"]](**entry["settings"])
                 for name, entry in data["backends"].items() if name in data["bindings"].values()}
    return {operation: instances[name] for operation, name in data["bindings"].items()}


def _validate_support_profiles(name: str, config_data: dict) -> None:
    """Validate host-only support profile metadata without exposing it to tools."""
    if "support_profiles" not in config_data:
        return
    profiles = config_data["support_profiles"]
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"backend {name} support_profiles must be a nonempty table")
    settings = config_data["settings"]
    support_settings = {setting for setting in settings
                        if setting == "support" or setting.endswith("_support")}
    for setting, profile in profiles.items():
        identifier(setting)
        if setting not in support_settings:
            raise ValueError(f"backend {name} support_profiles names a non-support setting: {setting}")
        identifier(profile)
    if set(profiles) != support_settings:
        missing = sorted(support_settings - set(profiles))
        detail = f"missing {missing}" if missing else "has no matching support setting"
        raise ValueError(f"backend {name} support_profiles {detail}")
