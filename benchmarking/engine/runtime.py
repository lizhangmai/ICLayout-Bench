"""Bind a cached dataset case to local tools without a prepared case directory."""

import json
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from benchmarking.bundles import Bundle, load_bundle
from benchmarking.dataset import process_manifest
from benchmarking.files import Asset, read_file
from benchmarking.tasks import Task, load_task

from .external import ExternalRuntime
from .resources.agent import prepare_agent_cache
from .resources.installation import cache_root, prepare_installation
from .resources.support import load_profile, prepare_support_cache
from .toolchain_config import load_toolchain_spec
from .toolchains import load_toolchain


def case_resources(case):
    """Collect declared support profiles for one case without preparing them."""
    spec = load_toolchain_spec(case, require_declared=True)
    manifest = process_manifest(case)
    return [(name, setting, profile, f"{manifest}#{profile}")
            for name, backend in spec.backends.items()
            for setting, profile in backend.support_profiles]


@dataclass(frozen=True)
class CaseInputs:
    config: Path
    task: Task

    def witness(self):
        data = tomllib.loads(self.config.read_text())
        path = data["qualification"]["reference"]
        result = Asset(read_file(self.config.parent, path), "gds")
        for entry in data.get("assets", []):
            if entry["path"] == path and result.sha256 != entry["sha256"]:
                raise ValueError("Reference witness checksum mismatch")
        return result


@dataclass(frozen=True)
class CaseRuntime(CaseInputs):
    backends: dict
    agent: Bundle | None
    external: ExternalRuntime | None = None

    def agent_resources(self):
        if self.agent is None:
            raise ValueError(f"Case has no Agent resource declaration: {self.task.id}")
        return dict(self.agent.files) | {"manifest.json": self.agent.manifest}


def load_case_inputs(config):
    """Load a task and reference without preparing PDKs, images or backends."""
    config = Path(config).absolute()
    return CaseInputs(config, load_task(config))


def load_case(config, *, image="iclayout-eda-open:local", include_agent=True, factories=None):
    selected = load_case_inputs(config)
    config, task = selected.config, selected.task
    manifest = process_manifest(config)
    declaration = tomllib.loads(manifest.read_text())
    external = None
    if declaration.get('source', {}).get('kind') == 'external':
        source = declaration['source']
        external = ExternalRuntime.from_manifest(manifest)
        mounts = external.pdk_mounts()
        if not mounts or any(m['release'] != source['release'] for m in mounts):
            raise ValueError('External PDK release differs from the task declaration')
        if declaration.get('profiles') or declaration.get('agent'):
            raise ValueError('External PDKs cannot use public cached profiles or Agent bundles')
        data = tomllib.loads(config.read_text())
        for backend in data['toolchain']['backends'].values():
            selected = backend['settings'].get('runtime')
            if selected is not None and selected != source['runtime']:
                raise ValueError('Backend runtime differs from the external PDK declaration')
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    profiles = {}
    diagnostics = cache_root() / "diagnostics" / task.digest
    for _, _, profile, spec in case_resources(config):
        if profile not in profiles:
            source = json.loads(load_profile(spec).content)["source"]
            installation = prepare_installation(source)
            profiles[profile] = prepare_support_cache(
                installation, spec, compiler_image=image_id, diagnostics=diagnostics / profile)
    shared = prepare_agent_cache(manifest,
                                 profiles=profiles, image=image_id, diagnostics=diagnostics / "agent") if include_agent else None
    return CaseRuntime(config, task, load_toolchain(config, profiles=profiles, image=image_id,
                                                    runtimes={external.name: external} if external else None,
                                                    factories=factories),
                       load_bundle(shared) if shared else None, external)
