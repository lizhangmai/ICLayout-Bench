"""Validate terminal exports and freeze their artifact bytes before SQL import."""

import json
from dataclasses import dataclass
from pathlib import Path

from benchmarking.files import read_file

from .normalization import digest, normalize


@dataclass(frozen=True)
class PreparedResult:
    raw: dict
    evaluation: dict
    condition: dict
    task_id: str
    identity: dict
    repetition: int
    run_data: dict
    files: dict[str, bytes]
    missing: list[str]


def prepare_result(path, namespace):
    path = Path(path)
    path = path / "result.json" if path.is_dir() else path
    original = read_file(path.parent, path.name)
    raw = json.loads(original)
    evaluation, condition, task_id, identity, repetition = normalize(raw)
    run_data = {
        "benchmark": (raw.get("identity") or {}).get("benchmark"),
        "tool_identity": evaluation.get("tool_identity"),
        "limits": evaluation.get("limits"),
        "top_cell": raw.get("top_cell"),
        "candidate_sha256": (evaluation.get("submission") or {}).get(
            "candidate_sha256"
        ),
        "candidate_identity": "recorded"
        if (evaluation.get("submission") or {}).get("candidate_sha256")
        else "import_time_only",
        "execution": raw.get("execution"),
        "attempts": raw.get("attempts", []),
        "image": raw.get("image"),
        "namespace": namespace,
    }
    files = {"result.json": original}
    missing = []
    for name in dict.fromkeys(
        list(raw.get("files", []))
        + [
            "final.gds",
            "layout.png",
            "evaluation/report.json",
            "evaluation/plan.json",
        ]
    ):
        # Never scan recovery/authentication directories, even if a supplied manifest lists one.
        if any(p.startswith(".") for p in Path(name).parts) or name.startswith(
            "participant/"
        ):
            raise ValueError("Private runtime files cannot be imported")
        try:
            content = read_file(path.parent, name)
        except FileNotFoundError:
            missing.append(name)
            continue
        if (
            name == "final.gds"
            and run_data["candidate_sha256"]
            and digest(content) != run_data["candidate_sha256"]
        ):
            raise ValueError("Candidate differs from scored submission")
        files[name] = content
    if "evaluation/report.json" in files:
        report = json.loads(files["evaluation/report.json"])
        if report.get("score") != evaluation.get("score"):
            raise ValueError("Evaluation report and service score disagree")
    run_data["imported_candidate_sha256"] = (
        digest(files["final.gds"]) if "final.gds" in files else None
    )
    return PreparedResult(raw, evaluation, condition, task_id, identity, repetition, run_data, files, missing)
