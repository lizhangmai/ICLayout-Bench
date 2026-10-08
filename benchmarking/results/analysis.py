"""Analysis of service results; no evaluator or private-package dependency."""

import csv
import json
from pathlib import Path

from benchmarking.files import Asset, atomic_write
from benchmarking.protocol import evaluation_mode, layout_score_value

from .statistics import score_summary


def _csv(path, columns, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key) for key in columns} for row in rows)
    Path(path).chmod(0o600)


def export_session_result(result, destination):
    """Export service-reported data, preserving its evaluation mode and missing values.

    This is not local cryptographic verification of the private judge's evidence.
    The complete response and its digest accompany plotting tables.
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


def export_results(results, destination, *, plots=False):
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
    if plots and summaries:
        from .plotting import render_service_results

        render_service_results(rows, output)
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
