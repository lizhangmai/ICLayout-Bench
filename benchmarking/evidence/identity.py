"""Content identity of the installed public implementation, independent of Git."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import benchmarking
from benchmarking.files import Asset, relative
from benchmarking.protocol import json_bytes
from benchmarking.version import package_version

EVALUATION_SOURCE_FILES = (
    'evaluation/runner.py',
    'evaluation/contracts.py',
    'evaluation/__init__.py',
    'evaluation/plans.py',
    'evaluation/scoring.py',
    'files.py',
    'execution/tools/budget.py',
    'execution/tools/diagnostics.py',
)


SESSION_SOURCE_FILES = (
    'execution/workspace/__init__.py',
    'execution/tools/__init__.py',
    'execution/workspace/config.py',
    'service/session.py',
    'service/supervisor.py',
    'execution/process.py',
    'evidence/journal.py',
    'execution/workspace/docker.py',
    'execution/workspace/staging.py',
    'evidence/archive.py',
    'execution/workspace/environment.py',
    'execution/workspace/access.py',
    'execution/workspace/protocol.py',
    'execution/tools/docker.py',
    'execution/tools/cleanup.py',
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


def package_identity():
    dist = importlib.metadata.distribution("iclayout-bench")
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    files = {}
    if direct.get("dir_info", {}).get("editable"):
        root = Path(benchmarking.__file__).resolve().parent
        for file in sorted(root.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                files["benchmarking/" + file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    else:
        for file in dist.files or []:
            if str(file).startswith("benchmarking/") and file.suffix != ".pyc":
                files[str(file)] = hashlib.sha256(Path(dist.locate_file(file)).read_bytes()).hexdigest()
    if not files:
        raise ValueError("Installed benchmark has no identifiable package files")
    return {"name": dist.metadata["Name"], "version": dist.version, "installed_content_sha256": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "commit": package_version()["commit"],
            "wheel_sha256": direct.get("archive_info", {}).get("hashes", {}).get("sha256")}
