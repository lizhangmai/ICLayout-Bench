"""Content identity of the installed public implementation, independent of Git."""
from pathlib import Path

import benchmarking
from benchmarking.files import Asset
from benchmarking.protocol import json_bytes


def source_path(name):
    evaluator = Path(__file__).with_name(name)
    return evaluator if evaluator.is_file() else Path(benchmarking.__file__).with_name(name)


def source_key(name):
    source = source_path(name)
    return source.relative_to(Path(benchmarking.__file__).parent.parent).as_posix()


def implementation_files():
    root = Path(benchmarking.__file__).parent
    return {path.relative_to(root.parent).as_posix(): Asset(path.read_bytes(), 'binary')
            for path in sorted(root.rglob('*'))
            if path.is_file() and path.suffix in {'.py', '.json', '.yaml'}}



def implementation_identity():
    identities = {name: asset.sha256 for name, asset in implementation_files().items()}
    return 'sha256:' + Asset(json_bytes(identities), 'json').sha256
