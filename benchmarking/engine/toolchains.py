"""Bind declared operations to selected, trusted evaluator implementations."""

from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from .contracts import Backend
from .toolchain_config import load_toolchain_spec

# Only this installed registry names importable code. Task declarations select
# registry keys and cannot supply module paths.
_BUILTINS = {
    "ngspice-docker": ("ngspice", "NgspiceDocker"),
    "assura-drc-docker": ("assura", "AssuraDocker"),
    "assura-lvs-docker": ("assura", "AssuraLvsDocker"),
    "assura-rc-docker": ("assura", "AssuraRCDocker"),
    "pvs-docker": ("pvs", "PvsDocker"),
    "calibre-docker": ("calibre", "CalibreDocker"),
    "spectre-docker": ("spectre", "SpectreDocker"),
    "calibre-native": ("calibre", "CalibreNative"),
    "calibre-quantus-native": ("calibre_quantus", "CalibreQuantusNative"),
    "calibre-starrc-native": ("calibre_starrc", "CalibreStarRCNative"),
    "spectre-aps-docker": ("spectre_aps", "SpectreAPSDocker"),
    "spectre-x-docker": ("spectre_x", "SpectreXDocker"),
    "spectre-x-native": ("spectre_native", "SpectreXNative"),
    "icv-native": ("synopsys", "ICVNative"),
    "hspice-native": ("synopsys", "HspiceNative"),
    "magic-physical-docker": ("magic_checks", "MagicPhysicalDocker"),
    "magic-capacitance-docker": ("magic", "MagicCapacitanceDocker"),
    "magic-rc-docker": ("magic", "MagicRCDocker"),
    "sg13g2-hbt-rc-docker": ("hbt.backend", "SG13G2HBTRCDocker"),
    "klayout-docker": ("klayout", "KLayoutDocker"),
    "sg13g2-kpex-cc-docker": ("kpex", "SG13G2KpexCCDocker"),
    "klayout-geometry-docker": ("geometry", "KLayoutGeometryDocker"),
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
        from benchmarking.dataset import process_manifest

        from .external import ExternalRuntime

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
