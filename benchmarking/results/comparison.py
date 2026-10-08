"""Pure aggregation for result rows already selected by the archive store."""

from statistics import mean

from benchmarking.protocol import evaluation_tools

from .normalization import digest
from .statistics import score_summary


def aggregate(rows, schedules, filters):
    """Build comparison cells and coverage from rows and experiment schedules."""
    groups, columns, tasks = {}, {}, {}
    for row in rows:
        # Budgets/tools may legitimately differ between circuits; record the full per-task profile.
        context = {
            "task": row["task_version"],
            "tool": evaluation_tools(row["evaluation"]),
            "limits": row["evaluation"].get("limits"),
            "evaluation_mode": row["evaluation_mode"],
            "method": row["method"],
        }
        task_key = digest(context)
        tasks[task_key] = {
            "key": task_key,
            "task_id": row["task_id"],
            "title": row["title"],
            "context": context,
        }
        cid = row["condition_id"]
        columns[cid] = {"id": cid, **row["condition"]}
        groups.setdefault((task_key, cid), []).append(row)

    cells = []
    for (task_key, cid), members in groups.items():
        statistics = score_summary(row["score"] for row in members)
        cells.append(
            {
                "task_key": task_key,
                "condition_id": cid,
                "count": len(members),
                "measured": statistics.measured,
                "mean": statistics.mean,
                "stddev": statistics.sample_stddev,
                "passed": sum(row["outcome"] == "pass" for row in members),
                "outcomes": {
                    name: sum(row["outcome"] == name for row in members)
                    for name in ("pass", "fail", "no_submission", "error")
                },
                "run_ids": [row["id"] for row in members],
            }
        )

    # Planned but unexecuted circuits are visible and count against coverage.
    for plan in schedules:
        if any(
            filters.get(key) and filters[key] != plan.get(key)
            for key in ("model", "harness", "effort")
        ):
            continue
        matches = [
            column
            for column in columns.values()
            if column.get("model") == plan.get("model")
            and column.get("harness") == plan.get("harness")
            and column.get("effort_resolved") == plan.get("effort")
        ]
        if not matches and not any(
            filters.get(key) for key in ("evaluation_mode", "pdk", "outcome")
        ):
            cid = digest(
                ["planned", plan.get("model"), plan.get("harness"), plan.get("effort")]
            )
            columns[cid] = {
                "id": cid,
                "model": plan.get("model"),
                "harness": plan.get("harness"),
                "effort_resolved": plan.get("effort"),
                "planned": True,
            }
        for task_id in plan.get("tasks", []):
            if filters.get("task") and filters["task"] != task_id:
                continue
            if not any(task["task_id"] == task_id for task in tasks.values()) and not any(
                filters.get(key) for key in ("evaluation_mode", "pdk", "outcome")
            ):
                key = digest(["unexecuted", task_id])
                tasks[key] = {
                    "key": key,
                    "task_id": task_id,
                    "context": {"evaluation_mode": "not_run"},
                }

    common = set(tasks)
    for cid in columns:
        common &= {
            cell["task_key"]
            for cell in cells
            if cell["condition_id"] == cid and cell["measured"] == cell["count"]
        }
    totals = []
    for cid in columns:
        included = [
            cell
            for cell in cells
            if cell["condition_id"] == cid and cell["task_key"] in common
        ]
        totals.append(
            {
                "condition_id": cid,
                "common_tasks": len(common),
                "coverage": sum(cell["condition_id"] == cid for cell in cells),
                "total_tasks": len(tasks),
                "mean": mean(cell["mean"] for cell in included) if included else None,
            }
        )
    return {
        "tasks": list(tasks.values()),
        "conditions": list(columns.values()),
        "cells": cells,
        "totals": totals,
    }
