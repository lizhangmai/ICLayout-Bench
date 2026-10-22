"""Declared solver resources and the unchanged authored task message."""

import json
import re

from benchmarking.files import ReadOnlyMount, keys, relative

DESCRIPTOR = "pdk-environment.json"

def descriptor(resources):
    if DESCRIPTOR not in resources:
        return None
    data = json.loads(resources[DESCRIPTOR].content)
    keys(data, {"id", "environment", "checks", "sources"}, set(), "PDK environment")
    for name, value in data["environment"].items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or not isinstance(value, str) or "\0" in value:
            raise ValueError("Invalid PDK environment setting")
        if name in {"HOME", "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONHOME"}:
            raise ValueError(f"Reserved PDK environment setting: {name}")
        if name.endswith(("PATH", "ROOT")):
            for path in value.split(":"):
                if not path.startswith("/resources/"):
                    raise ValueError("PDK paths must be inside /resources")
                local = relative(path.removeprefix("/resources/"), "PDK environment path")
                if not any(key == local or key.startswith(local + "/")
                           or (isinstance(value, ReadOnlyMount) and value.path.is_dir()
                               and local.startswith(key + "/"))
                           for key, value in resources.items()):
                    raise ValueError(f"Missing PDK environment path: {path}")
    if not isinstance(data["checks"], list) or not data["checks"]:
        raise ValueError("PDK environment requires usage checks")
    for command in data["checks"]:
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or "\0" in x for x in command):
            raise ValueError("PDK checks must be argument lists")
    return data


def resource_environment(resources):
    """Return environment settings declared by the selected PDK manifest."""
    declared = descriptor(resources)
    return dict(declared["environment"]) if declared is not None else {}


def resource_preflight(resources, runtime=None):
    """Describe mounted resource checks without exposing task/reference files."""
    environment = resource_environment(resources)
    result = {"mount": "/resources", "environment": environment,
              "bundles": [], "python_imports": []}
    declared = descriptor(resources)
    if runtime is not None:
        result['external'] = {'name': runtime.name, 'environment': dict(runtime.environment),
                              'modules': runtime.modules,
                              'tool_environment': runtime.tool_environment,
                              'mounts': [{'target': m['target'], 'release': m['release']}
                                         for m in runtime.mounts if not m.get('credential')]}
    if declared is not None:
        result.update({"pdk": declared["id"], "checks": declared["checks"],
                       "bundles": [{"kind": "pdk-sources", "sources": declared["sources"]}]})
        return result
    return result


def task_description(task, resource_info):
    """Combine solver-visible task and deployment metadata without changing the task."""
    return {**task.solver_description(), 'resources': resource_info}


def _agent_environment(config, resources):
    """Merge automatic resource paths with explicitly configured public values."""
    environment = dict(config.environment)
    pdk = resource_environment(resources)
    if not pdk:
        return environment
    for name, value in pdk.items():
        if name in {"PYTHONPATH", "KLAYOUT_PATH"}:
            paths = value.split(":") + [p for p in environment.get(name, "").split(":") if p]
            environment[name] = ":".join(dict.fromkeys(paths))
        elif name in environment and environment[name] != value:
            raise ValueError(f"PDK resources require {name}={value}")
        else:
            environment[name] = value
    return environment


def task_message(task, config):
    """First task input is exactly the declared problem document."""
    return task.problem
