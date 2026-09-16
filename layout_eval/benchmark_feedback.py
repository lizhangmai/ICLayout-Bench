"""Participant opinions: bounded JSON submissions, never evaluator verdicts.

This module is also mounted as a standalone, standard-library-only client.
"""

import argparse
import json
import socket
from pathlib import Path

CAPABILITY = "benchmark-feedback.v1"
MAX_BYTES = 16384
MAX_REPORTS = 16
CATEGORIES = ("task", "inputs", "resources", "tools", "evaluation", "protocol", "other")


def validate_feedback(value):
    required = {"schema_version", "category", "summary", "observed"}
    optional = {"expected", "suggestion", "evidence"}
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise ValueError("Feedback requires schema_version, category, summary and observed")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported feedback schema")
    if value["category"] not in CATEGORIES:
        raise ValueError("Unknown feedback category")
    for name in (required | optional) - {"schema_version", "category"}:
        if name in value and (not isinstance(value[name], str) or not value[name].strip()
                              or "\x00" in value[name]):
            raise ValueError(f"Feedback {name} must be nonempty text")
    if len(value["summary"]) > 240:
        raise ValueError("Feedback summary exceeds 240 characters")
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Feedback exceeds the size limit")
    return dict(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="UTF-8 JSON opinion file in the workspace")
    args = parser.parse_args()
    try:
        with args.file.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Feedback exceeds the size limit")
        value = validate_feedback(json.loads(raw))
        request = json.dumps({"action": "benchmark_feedback", "feedback": value},
                             ensure_ascii=False).encode() + b"\n"
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(10)
            connection.connect("/protocol/control.sock")
            connection.sendall(request)
            receipt = json.loads(connection.makefile("rb").readline(MAX_BYTES))
        print(json.dumps(receipt), flush=True)
        return 0 if receipt.get("accepted") else 1
    except (OSError, TypeError, ValueError) as error:
        parser.exit(1, f"Benchmark feedback rejected: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
