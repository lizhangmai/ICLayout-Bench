"""Case-owned provenance and mutual exclusion for default experiment results."""

from benchmarking.engine.recorder import BatchLease


class CaseLease(BatchLease):
    filename = ".case.lock"


def case_identity(condition, task):
    """Other selected cases and dispatch concurrency do not change this experiment."""
    row = condition["plan"][0]
    if task not in row["tasks"]:
        raise ValueError("Task is absent from the recorded condition")
    identity = {k: v for k, v in condition.items() if k not in {"plan", "inputs", "layout"}}
    identity["layout"] = "case-v2"
    identity["plan"] = [{**{k: v for k, v in row.items() if k not in {"tasks", "concurrency"}},
                         "tasks": [task]}]
    if "inputs" in condition:
        identity["inputs"] = {task: condition["inputs"][task]}
    return identity
