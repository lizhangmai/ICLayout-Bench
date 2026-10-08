"""Declared solver resources and participant-facing session instructions."""

from benchmarking.engine.container_scripts import benchmark_feedback as opinions
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY

from ..resources.agent import descriptor


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
    message = ("Generate a GDS layout implementing the authoritative netlist and all task requirements.\n"
               "Read /protocol/task.json for input paths, top cell, output path and limits.\n"
               "Read /protocol/harness.json for the session protocol and declared capabilities.\n"
               "Read /protocol/resources.json for reviewed resource paths and the optional import preflight.\n"
               "Task inputs are read-only in /task; reviewed resources are in /resources.\n"
               "The writable /workspace starts empty. Available tools come from the recorded image.\n"
               f"Wall-clock budget: {config.wall_seconds:g} seconds, including your tool calls.\n"
               f"Write {task.description()['output']['path']}, then explicitly submit with:\n"
               "python -I /protocol/submit.py\n"
               "Wait for the host receipt. Submit candidates early and retain your best final snapshot.\n"
               "Only the last accepted snapshot is evaluated; writing a file alone is not submission.\n"
               "The receipt confirms file delivery, not DRC/LVS or performance success.\n")
    if config.soft_budget:
        message += ("This is a soft solve budget. At expiry, finish already-started work and submit immediately.\n"
                    "Do not start another command, check or optimization round after expiry.\n")
    if PROCESS_FEEDBACK_CAPABILITY in config.harness.capabilities:
        message += ("This harness declares optional same-semantic process feedback. For a read-only\n"
                     "check of the current output snapshot, run:\n"
                     "python -I /protocol/process_check.py\n"
                     "Feedback is diagnostic and never replaces the final independent evaluation.\n")
    if opinions.CAPABILITY in config.harness.capabilities:
        message += ("You may report problems with the benchmark independently of your layout submission.\n"
                    "Write a JSON object with category, summary and observed;\n"
                    f"category must be one of: {', '.join(opinions.CATEGORIES)}.\n"
                    "Optional text fields: expected, suggestion, evidence (commands or log excerpts).\n"
                    "Send it with python -I /protocol/benchmark_feedback.py <your-json-file>.\n"
                    "Opinions do not change the score or submit a layout. Report only problems you observed.\n")
    return message
