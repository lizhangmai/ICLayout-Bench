"""Stage declared solver inputs and trusted protocol helpers as read-only mounts."""

import json

from benchmarking.engine.container_scripts import benchmark_feedback as opinions
from benchmarking.files import Asset, ReadOnlyMount, relative
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY

from ..source import package_source
from ..tools.docker import read_only_mount_args


def stage_inputs(root, task, config, resources, message, resource_info, *, inference=None, feedback=None):
    task.materialize(root / "task")
    protocol_files = {
        "task.json": Asset(json.dumps(task.description()).encode(), "json"),
        "prompt.txt": Asset(message.encode(), "text"),
        "harness.json": Asset(json.dumps(config.harness.identity(), sort_keys=True).encode(), "json"),
        "resources.json": Asset(json.dumps(resource_info, sort_keys=True).encode(), "json"),
        **{name: Asset(package_source("engine/container_scripts/" + name).read_bytes(), "python")
           for name in ("snapshot.py", "submit.py", "workspace.py")}}
    feedback_enabled = (feedback is not None
                        and PROCESS_FEEDBACK_CAPABILITY in config.harness.capabilities)
    if feedback_enabled:
        protocol_files["process_check.py"] = Asset(
            package_source("engine/container_scripts/process_check.py").read_bytes(), "python")
    opinions_enabled = opinions.CAPABILITY in config.harness.capabilities
    if opinions_enabled:
        protocol_files["benchmark_feedback.py"] = Asset(
            package_source("engine/container_scripts/benchmark_feedback.py").read_bytes(), "python")
    groups = {"agent": config.files, "resources": resources, "protocol": protocol_files}
    if inference:
        profile = Asset(json.dumps(inference.public, sort_keys=True).encode(), "json")
        groups["protocol"]["inference.json"] = profile
    resource_mounts = []
    for group, files in groups.items():
        (root / group).mkdir()
        for name, asset in files.items():
            relative(name, "session input")
            if isinstance(asset, ReadOnlyMount):
                target = root / group / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.mkdir() if asset.path.is_dir() else target.touch()
                resource_mounts.extend(read_only_mount_args(asset, f"/{group}/{name}"))
                continue
            destination = root / group / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(asset.content)
            destination.chmod(0o444)
    return resource_mounts
