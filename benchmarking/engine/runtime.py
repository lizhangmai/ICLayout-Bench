"""Bind a cached dataset case to local tools without a prepared case directory."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from benchmarking.bundles import Bundle, load_bundle
from benchmarking.dataset import dataset_root, process_manifest
from benchmarking.files import Asset, read_file
from benchmarking.tasks import Task, load_task

from .pdk_installation import cache_root, prepare_installation
from .pdk_resources import prepare_agent_cache
from .preparation import case_resources
from .prepare_support import load_profile, prepare_support_cache
from .toolchains import load_toolchain


@dataclass(frozen=True)
class CaseRuntime:
    config: Path
    task: Task
    backends: dict
    agent: Bundle | None

    def agent_resources(self):
        if self.agent is None:
            raise ValueError(f"Case has no Agent resource declaration: {self.task.id}")
        return dict(self.agent.files) | {"manifest.json": self.agent.manifest}

    def witness(self):
        import tomllib

        data = tomllib.loads(self.config.read_text())
        path = data["qualification"]["reference"]
        result = Asset(read_file(self.config.parent, path), "gds")
        for entry in data.get("assets", []):
            if entry["path"] == path and result.sha256 != entry["sha256"]:
                raise ValueError("Reference witness checksum mismatch")
        return result


def load_case(config, *, image="iclayout-bench-tools:local", include_agent=True, factories=None):
    config = Path(config).absolute()
    task = load_task(config)
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    profiles = {}
    root = dataset_root(config)
    diagnostics = cache_root() / "diagnostics" / task.digest
    for _, _, profile, spec, _ in case_resources(config, root):
        if profile not in profiles:
            source = json.loads(load_profile(spec).content)["source"]
            installation = prepare_installation(source)
            profiles[profile] = prepare_support_cache(
                installation, spec, compiler_image=image_id, diagnostics=diagnostics / profile)
    shared = prepare_agent_cache(process_manifest(config), root=root,
                                 profiles=profiles, image=image_id, diagnostics=diagnostics / "agent") if include_agent else None
    return CaseRuntime(config, task, load_toolchain(config, profiles=profiles, image=image_id, factories=factories),
                       load_bundle(shared) if shared else None)
