"""Confined native record reads; vendor layouts and semantics stay in adapters."""

import json
from pathlib import Path


def json_events(path):
    if Path(path).is_file():
        with Path(path).open(errors='replace') as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    yield event


def confined_files(root, *patterns):
    for path in sorted({path for pattern in patterns for path in root.glob(pattern)}):
        if path.is_file() and path.resolve().is_relative_to(root.resolve()):
            yield path


def traces(home, prefix, *patterns):
    return {prefix + '/' + path.relative_to(home).as_posix(): path.read_bytes()
            for path in confined_files(home, *patterns)}
