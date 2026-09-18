"""Content identities of trusted evaluation, independent of participant tooling."""

import hashlib

from benchmarking.protocol import json_bytes

from .source import source_path


def evaluation_identity(task, backends):
    def digest(value):
        return hashlib.sha256(json_bytes(value)).hexdigest()

    return {"format": "evaluator-v1", "task_sha256": task.digest,
            "plan_sha256": hashlib.sha256(task.evaluation.raw).hexdigest(),
            "inputs": {k: v.sha256 for k, v in task.evaluation_inputs().items()},
            "backends": {k: digest(v.identity) for k, v in backends.items()},
            "implementation": {name: hashlib.sha256(source_path(name).read_bytes()).hexdigest()
                               for name in ("evaluate.py", "evaluation.py", "scoring.py", "files.py")}}
