"""Analysis of service results; no evaluator or private-package dependency."""

import csv
import json
from pathlib import Path

from benchmarking.files import Asset, atomic_write
from benchmarking.protocol import evaluation_mode, layout_score_value
from benchmarking.results.statistics import model_usage_summary, score_summary


def _csv(path, columns, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in columns} for row in rows)
    Path(path).chmod(0o600)


def export_session_result(result, destination):
    """Export service-reported data, preserving its evaluation mode and missing values.

    This is not local cryptographic verification of the private judge's evidence.
    The complete response and its digest accompany analysis tables.
    """
    from benchmarking.protocol import PROTOCOL, json_bytes

    if result.get("protocol") != PROTOCOL or result.get("state") not in {
        "complete",
        "error",
    }:
        raise ValueError("Expected a terminal layout-http result")
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False)
    raw = json_bytes(result)
    atomic_write(output / "result.json", raw)
    receipt = result.get("submission") or {}
    row = {
        key: result.get(key)
        for key in (
            "session_id",
            "task_id",
            "task_sha256",
            "outcome",
            "task_success",
            "failure_reason",
        )
    }
    row.update(
        evaluation_mode=evaluation_mode(result),
        candidate_sha256=receipt.get("candidate_sha256"),
        score=layout_score_value(result.get("score")),
        **result["condition"],
        **result["usage"],
    )
    for key in ("tool_identity", "limits", "provenance"):
        row[key] = json.dumps(result[key], sort_keys=True)
    _csv(output / "summary.csv", tuple(row), [row])
    metrics = []
    for name, metric in result.get("metrics", {}).items():
        metrics.append(
            {
                "session_id": result["session_id"],
                "metric": name,
                "value": metric.get("value"),
                "unit": metric.get("unit"),
                "status": metric.get("status"),
            }
        )
    _csv(
        output / "metrics.csv",
        ("session_id", "metric", "value", "unit", "status"),
        metrics,
    )
    atomic_write(
        output / "manifest.json",
        json_bytes(
            {
                "source_sha256": Asset(raw, "json").sha256,
                "verification": "service_reported",
                "missing_csv_values": "empty",
                "files": {
                    name: Asset((output / name).read_bytes(), "binary").identity()
                    for name in ("result.json", "summary.csv", "metrics.csv")
                },
            }
        ),
    )
    return output


def export_results(results, destination):
    """Compare like conditions; incomplete/error results never become zero scores.

    This consumes disclosed service results, not private evaluator artifacts.
    Evaluation modes are retained, not changed by analysis.
    """
    from collections import defaultdict

    from benchmarking.protocol import PROTOCOL, json_bytes

    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    groups = defaultdict(list)
    rows = []
    seen = set()
    for result in results:
        if result.get("protocol") != PROTOCOL or result.get("test_only"):
            raise ValueError(
                "Only real protocol results can enter measurement analysis"
            )
        sid = result["session_id"]
        if sid in seen:
            raise ValueError("Duplicate session")
        seen.add(sid)
        binding = {
            key: result[key]
            for key in ("condition", "tool_identity", "limits")
        }
        binding["evaluation_mode"] = evaluation_mode(result)
        cohort = Asset(json_bytes(binding), "json").sha256
        value = layout_score_value(result.get("score"))
        if result.get("outcome") == "error" or result.get("state") not in {
            "complete",
            "error",
        }:
            value = None
        row = {
            "cohort": cohort,
            "session_id": sid,
            "task_id": result["task_id"],
            "task_sha256": result["task_sha256"],
            "state": result["state"],
            "outcome": result.get("outcome"),
            "score": value,
            "evaluation_mode": evaluation_mode(result),
            **result["condition"],
            **result["usage"],
        }
        rows.append(row)
        groups[(cohort, result["task_id"], result["task_sha256"])].append(row)
    atomic_write(output / "results.json", json_bytes(results))
    if rows:
        _csv(output / "runs.csv", tuple(rows[0]), rows)
    summaries = []
    for (cohort, task, sha), group in sorted(groups.items()):
        statistics = score_summary(row["score"] for row in group)
        summaries.append(
            {
                "cohort": cohort,
                "task_id": task,
                "task_sha256": sha,
                "trials": len(group),
                "measured": statistics.measured,
                "unknown": len(group) - statistics.measured,
                "mean": statistics.mean,
                "sample_stddev": statistics.sample_stddev,
                "pass": sum(row["outcome"] == "pass" for row in group),
                "fail": sum(row["outcome"] == "fail" for row in group),
                "no_submission": sum(
                    row["outcome"] == "no_submission" for row in group
                ),
                "infrastructure_error": sum(row["outcome"] == "error" for row in group),
            }
        )
    if summaries:
        _csv(output / "tasks.csv", tuple(summaries[0]), summaries)
    atomic_write(
        output / "manifest.json",
        json_bytes(
            {
                "verification": "service_reported",
                "missing_csv_values": "empty",
                "files": {
                    p.name: Asset(p.read_bytes(), "binary").identity()
                    for p in sorted(output.iterdir())
                    if p.is_file()
                },
            }
        ),
    )
    return output


def export_participant_results(results, destination):
    """Export task cost, duration and native usage separately from judge verdicts."""
    from benchmarking.results.normalization import normalize

    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    rows, groups = [], {}
    for result in results:
        evaluation, condition, task, _, repetition = normalize(result)
        usage = result.get("model_usage") or {}
        row = {"task": task, "session_id": evaluation["session_id"], "repetition": repetition,
               "harness": condition["harness"], "model": condition["model"],
               "effort": condition["effort_resolved"], "outcome": evaluation["outcome"],
               **(usage.get("tokens") or {}), "api_seconds": usage.get("api_seconds"),
               "cost_per_task": usage.get("cost"), "currency": usage.get("currency"),
               "cost_source": usage.get("cost_source"),
               "usage_aggregation": usage.get("aggregation"),
               "output_tokens_missing_records": (usage.get("coverage") or {}).get("output_tokens", {}).get("missing"),
               "cost_missing_records": (usage.get("coverage") or {}).get("cost", {}).get("missing"),
               "missing_attempts": usage.get("missing_attempts"),
               "wall_seconds": (result.get("execution") or {}).get("elapsed_seconds")}
        rows.append(row)
        key = (condition["harness"], condition["model"], condition["effort_resolved"])
        groups.setdefault(key, []).append(result.get("model_usage"))
    from benchmarking.results.usage import TOKEN_FIELDS
    columns = ("task", "session_id", "repetition", "harness", "model", "effort", "outcome",
               *TOKEN_FIELDS, "api_seconds", "cost_per_task", "currency",
               "cost_source", "wall_seconds")
    columns += ("usage_aggregation", "output_tokens_missing_records", "cost_missing_records", "missing_attempts")
    _csv(output / "runs.csv", columns, rows)
    summaries = [{"harness": key[0], "model": key[1], "effort": key[2], **model_usage_summary(values)}
                 for key, values in groups.items()]
    atomic_write(output / "summary.json", (json.dumps(summaries, indent=2) + "\n").encode())
    atomic_write(output / "results.json", (json.dumps(results, indent=2) + "\n").encode())
    manifest = {"usage_provenance": "participant_reported", "missing_csv_values": "empty",
                "files": {p.name: Asset(p.read_bytes(), "binary").identity()
                          for p in sorted(output.iterdir()) if p.is_file()}}
    atomic_write(output / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return output
