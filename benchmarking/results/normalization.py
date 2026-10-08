"""Pure normalization and identity helpers for archived result records."""

import hashlib
import json
import math
import mimetypes
from pathlib import Path

from benchmarking.harnesses import scheme_identity


def digest(value):
    raw = (
        value
        if isinstance(value, bytes)
        else json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )
    return hashlib.sha256(raw).hexdigest()


def finite(value):
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
    ):
        raise ValueError("Expected a finite measurement or null")
    return value


def media(name):
    return {
        ".gds": "application/octet-stream",
        ".jsonl": "text/plain",
        ".spice": "text/plain",
        ".cdl": "text/plain",
        ".md": "text/plain",
    }.get(
        Path(name).suffix, mimetypes.guess_type(name)[0] or "application/octet-stream"
    )


def normalize(raw):
    """Read compact exports and disclosed protocol results without inventing identities."""
    if raw.get("test_only"):
        raise ValueError("Protocol fixtures are not model measurements")
    if "evaluation" in raw:
        if raw.get("format") != "participant-result" or raw.get("state") != "finished":
            raise ValueError("Expected a finished supported compact result")
        evaluation = raw["evaluation"]
        identity, summary = raw.get("identity", {}), raw.get("summary", {})
    elif raw.get("protocol") == "layout-http":
        evaluation, identity, summary = raw, {}, {}
    else:
        raise ValueError("Unsupported result format")
    if evaluation.get("test_only") or evaluation.get("state") not in {
        "complete",
        "error",
    }:
        raise ValueError("Expected a terminal model evaluation")
    if evaluation.get("outcome") not in {"pass", "fail", "no_submission", "error"}:
        raise ValueError("Unknown terminal outcome")
    task_id = evaluation.get("task_id") or summary.get("task")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("Missing task identity")
    plans = identity.get("plan") or [{}]
    plan = next((p for p in plans if task_id in p.get("tasks", [])), plans[0])
    resolved = plan.get("resolved") or {}
    condition = dict(evaluation.get("condition") or {})
    condition.update(
        harness=plan.get("harness", condition.get("harness_id")),
        cli_version=identity.get("cli_version"),
        model=plan.get("model", condition.get("model")),
        effort_requested=summary.get(
            "effort_requested", resolved.get("effort_requested", plan.get("effort"))
        ),
        effort_resolved=summary.get(
            "effort_resolved", resolved.get("effort_resolved", plan.get("effort"))
        ),
        provider_effective_effort=summary.get(
            "provider_effective_effort", resolved.get("provider_effective_effort")
        ),
    )
    tools = evaluation.get("tool_identity") or {}
    if "evaluator" in tools:
        condition["solver_image"] = tools.get("image_id")
        condition["solver_resources"] = tools.get("solver_resources")
    if "scheme" in plan:
        condition["scheme"] = scheme_identity(plan["scheme"])
        condition["scheme_name"] = plan.get("name")
        condition["scheme_sha256"] = digest(condition["scheme"])
    task_identity = {
        "task_sha256": evaluation.get("task_sha256"),
        "benchmark": identity.get("benchmark"),
        "dataset": (
            identity.get("inputs", {}).get(task_id, {}).get("dataset")
            or plan.get("dataset")
        ),
    }
    # Unknown task versions stay isolated by session; a release identity is an explicitly weaker fallback.
    if not task_identity["task_sha256"] and not (
        task_identity.get("benchmark") or {}
    ).get("commit"):
        task_identity["unknown_version_scope"] = evaluation.get("session_id") or digest(
            raw
        )
    repetition = summary.get("repetition", 1)
    if (
        not isinstance(repetition, int)
        or isinstance(repetition, bool)
        or repetition < 1
    ):
        raise ValueError("Invalid repetition")
    return evaluation, condition, task_id, task_identity, repetition
