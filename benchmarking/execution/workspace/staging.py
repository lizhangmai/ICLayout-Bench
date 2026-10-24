"""Stage declared solver inputs and trusted protocol helpers as read-only mounts."""

import json

from benchmarking.evidence.identity import package_source
from benchmarking.execution._scripts import benchmark_feedback as opinions
from benchmarking.execution.harness import PROCESS_FEEDBACK_CAPABILITY
from benchmarking.execution.tools.docker import read_only_mount_args
from benchmarking.execution.workspace.environment import task_description
from benchmarking.files import Asset, ReadOnlyMount, relative


def stage_inputs(root, task, config, resources, message, resource_info, *, inference=None, feedback=None):
    task.materialize(root / "task")
    protocol_files = {
        "task.json": Asset(json.dumps(task_description(task, resource_info), sort_keys=True).encode(), "json"),
        "prompt.txt": Asset(message.encode(), "text"),
        **{name: Asset(package_source("execution/_scripts/" + name).read_bytes(), "python")
           for name in ("snapshot.py", "submit.py", "workspace.py")}}
    feedback_enabled = (feedback is not None
                        and PROCESS_FEEDBACK_CAPABILITY in config.harness.capabilities)
    if feedback_enabled:
        protocol_files["process_check.py"] = Asset(
            package_source("execution/_scripts/process_check.py").read_bytes(), "python")
    opinions_enabled = opinions.CAPABILITY in config.harness.capabilities
    if opinions_enabled:
        protocol_files["benchmark_feedback.py"] = Asset(
            package_source("execution/_scripts/benchmark_feedback.py").read_bytes(), "python")
    helpers = {name.removesuffix('.py'): {'command': ['python', '-I', '/protocol/' + name]}
               for name in ('submit.py', 'process_check.py', 'benchmark_feedback.py')
               if name in protocol_files}
    protocol_files['harness.json'] = Asset(json.dumps({
        **config.harness.identity(),
        'budget': {'phase_budgets': config.phase_budgets.identity()},
        'helpers': helpers,
    }, sort_keys=True).encode(), 'json')
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
    # Bind mounts expose these approved inputs to a different rootless UID.
    # Keep the enclosing host session private; its mounted directories need
    # explicit traversal permissions independent of the caller's umask.
    for group in ("task", *groups):
        for directory in [root / group, *(p for p in (root / group).rglob('*') if p.is_dir())]:
            directory.chmod(0o755)
    return resource_mounts
