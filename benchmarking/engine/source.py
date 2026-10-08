"""Content identity of the installed public implementation, independent of Git."""
import hashlib
from pathlib import Path

import benchmarking
from benchmarking.files import Asset, relative
from benchmarking.protocol import json_bytes

EVALUATION_SOURCE_FILES = (
    "engine/evaluate.py", "engine/contracts.py", "evaluation/__init__.py",
    "evaluation/contracts.py", "evaluation/graph.py", "evaluation/parsing.py", "evaluation/metrics.py",
    "evaluation/scoring.py", "files.py", "engine/tools/budget.py",
)


SESSION_SOURCE_FILES = (
    "engine/sessions/config.py", "engine/sessions/execution.py", "engine/sessions/control.py",
    "engine/sessions/recorder.py", "engine/sessions/docker.py", "engine/sessions/staging.py",
    "engine/sessions/archive.py",
    "engine/sessions/environment.py",
    "engine/sessions/workspace.py", "engine/sessions/protocol.py",
    "engine/tools/docker.py",
)


def package_source(name):
    """Locate a declared source within the installed package, without importing it."""
    root = Path(benchmarking.__file__).parent
    path = root / relative(name, "package source")
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Missing or external package source: " + name)
    return path


def source_key(name):
    source = package_source(name)
    return source.relative_to(Path(benchmarking.__file__).parent.parent).as_posix()


def evaluation_identity(task, backends):
    """Bind a task, trusted inputs and backend implementations to this evaluator."""
    def digest(value):
        return hashlib.sha256(json_bytes(value)).hexdigest()

    return {"format": "evaluator", "task_sha256": task.digest,
            "plan_sha256": hashlib.sha256(task.evaluation.raw).hexdigest(),
            "inputs": {k: v.sha256 for k, v in task.evaluation_inputs().items()},
            "backends": {k: digest(v.identity) for k, v in backends.items()},
            "implementation": {name: hashlib.sha256(package_source(name).read_bytes()).hexdigest()
                               for name in EVALUATION_SOURCE_FILES}}


def implementation_files():
    root = Path(benchmarking.__file__).parent
    return {path.relative_to(root.parent).as_posix(): Asset(path.read_bytes(), 'binary')
            for path in sorted(root.rglob('*'))
            if path.is_file() and path.suffix in {'.py', '.json', '.yaml'}}



def implementation_identity():
    identities = {name: asset.sha256 for name, asset in implementation_files().items()}
    return 'sha256:' + Asset(json_bytes(identities), 'json').sha256
