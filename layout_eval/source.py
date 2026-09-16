"""Content identity of the installed public implementation, independent of Git."""
from pathlib import Path

import benchmarking
import layout_service
from benchmarking.files import Asset
from benchmarking.protocol import json_bytes


def source_path(name):
    evaluator = Path(__file__).with_name(name)
    return evaluator if evaluator.is_file() else Path(benchmarking.__file__).with_name(name)


def source_key(name):
    source = source_path(name)
    return source.parent.name + '/' + source.name


def implementation_files():
    files = {}
    for package in (Path(benchmarking.__file__).parent, Path(__file__).parent,
                    Path(layout_service.__file__).parent):
        for path in sorted(package.iterdir()):
            if path.is_file() and path.suffix in {'.py', '.json', '.yaml'}:
                files[package.name + '/' + path.name] = Asset(path.read_bytes(), 'binary')
    return files


def implementation_identity():
    identities = {name: asset.sha256 for name, asset in implementation_files().items()}
    return 'sha256:' + Asset(json_bytes(identities), 'json').sha256
