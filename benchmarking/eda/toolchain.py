"""Read host tool declarations without importing or initializing EDA backends."""

import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from benchmarking.evaluation.contracts import Backend, identifier
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
        if 'finfet' in entry['settings'] and entry['type'].startswith('calibre-'):
            raise ValueError('Retired finfet policy: declare native process rules and parameter checks instead')
        if entry['type'] in {'calibre-native', 'calibre-quantus-native',
                             'calibre-starrc-native', 'assura-rc-native', 'pvs-native', 'icv-native'}:
            retired = {'mos_models', 'resistor_models', 'bipolar_models', 'mos_junctions'} & entry['settings'].keys()
            if retired:
                raise ValueError(f"Backend {name} requests retired circuit rewriting settings: "
                                 + ', '.join(sorted(retired))
                                 + '. Configure and qualify native extraction/model resources instead.')
        backends[name] = BackendSpec(entry["type"], entry["settings"],
                                    support_bindings(name, entry, require_declared=require_declared))
    if not all(isinstance(value, str) and value in backends for value in data["bindings"].values()):
        raise ValueError("Toolchain binding references an unknown backend")
    return ToolchainSpec(path, embedded, backends, data["bindings"])


# Only this installed registry names importable code. Task declarations select
# registry keys and cannot supply module paths.
_BUILTINS = {
    "ngspice-docker": ("ngspice", "NgspiceDocker"),
    "assura-drc-native": ("assura", "AssuraNative"),
    "assura-lvs-native": ("assura", "AssuraLvsNative"),
    "assura-rc-native": ("assura", "AssuraRCNative"),
    "pvs-native": ("pvs", "PvsNative"),
    "virtuoso-geometry-native": ("virtuoso", "VirtuosoGeometryNative"),
    "customcompiler-geometry-native": ("customcompiler", "CustomCompilerGeometryNative"),
    "spectre-native": ("spectre", "SpectreNative"),
    "calibre-native": ("calibre", "CalibreNative"),
    "calibre-quantus-native": ("calibre_quantus", "CalibreQuantusNative"),
    "calibre-starrc-native": ("calibre_starrc", "CalibreStarRCNative"),
    "spectre-aps-native": ("spectre", "SpectreAPSNative"),
    "spectre-x-native": ("spectre", "SpectreXNative"),
    "icv-native": ("synopsys", "ICVNative"),
    "hspice-native": ("synopsys", "HspiceNative"),
    "magic-physical-docker": ("magic_checks", "MagicPhysicalDocker"),
    "magic-capacitance-docker": ("magic", "MagicCapacitanceDocker"),
    "magic-rc-docker": ("magic", "MagicRCDocker"),
    "substrate-sheet-docker": ("substrate", "SubstrateSheetDocker"),
    "sg13g2-hbt-rc-docker": ("hbt.backend", "SG13G2HBTRCDocker"),
    "klayout-docker": ("klayout", "KLayoutDocker"),
    "kpex-cc-docker": ("kpex", "KpexCCDocker"),
    "klayout-geometry-docker": ("geometry", "KLayoutGeometryDocker"),
    "fixed-macros-docker": ("fixed_macros", "FixedMacrosDocker"),
    "rlc-line-docker": ("rlc_line", "RLCLineDocker"),
}


def load_toolchain(config: Path, *, profiles=None, image=None, runtimes=None,
                   factories: dict[str, Callable[..., Backend]] | None = None) -> dict[str, Backend]:
    """Validate declarations before constructing only the bound backends.

    The default registry imports selected built-ins lazily. Python callers may
    supply their own trusted factory registry. Prepared resource paths, image
    identities and external runtimes replace settings in memory only. Toolchain
    declarations and their implementations never enter the solver workspace.
    """
    spec = load_toolchain_spec(config, require_declared=profiles is not None)
    registry = _BUILTINS if factories is None else factories
    for name, backend in spec.backends.items():
        if backend.type not in registry:
            raise ValueError(f"Unknown or invalid backend: {name}")
    if runtimes is None and spec.embedded and spec.path.name == 'case.toml' and any(
            'runtime' in backend.settings for backend in spec.backends.values()):
        from benchmarking.eda.environment import ExternalRuntime
        from benchmarking.tasks.dataset import process_manifest

        runtime = ExternalRuntime.from_manifest(process_manifest(spec.path))
        runtimes = {runtime.name: runtime}
    settings = {}
    for name, backend in spec.backends.items():
        selected = dict(backend.settings)
        if profiles is not None:
            for setting, profile in backend.support_profiles:
                if profile not in profiles:
                    raise ValueError(f"Missing runtime profile: {profile}")
                selected[setting] = str(profiles[profile])
        if image is not None and "image" in selected:
            selected["image"] = image
        if runtimes is not None and "runtime" in selected:
            runtime = selected["runtime"]
            if runtime not in runtimes:
                raise ValueError(f"Unknown external runtime: {runtime}")
            selected["runtime"] = runtimes[runtime]
        settings[name] = selected
    instances = {}
    for name in dict.fromkeys(spec.bindings.values()):
        kind = spec.backends[name].type
        if factories is None:
            module, attribute = _BUILTINS[kind]
            factory = getattr(import_module('.backends.' + module, __package__), attribute)
        else:
            factory = factories[kind]
        instances[name] = factory(**settings[name])
    return {operation: instances[name] for operation, name in spec.bindings.items()}
