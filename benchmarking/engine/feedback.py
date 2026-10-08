"""Participant diagnostics with explicit truncation and private evidence filtering."""

import json


def feedback_details(report, directory, *, bounded=True):
    """Candidate diagnostics only; scores, evaluator inputs and reference assets stay private."""
    jobs = {}
    log_budget = 6000
    for name, job in report["jobs"].items():
        detail = {"status": job["status"], "reason": job.get("reason", "")[:512]}
        if job["status"] in {"failed", "error"}:
            logs = {}
            for key in ("log", "console", "result.json"):
                asset = job.get("evidence", {}).get(key, {})
                if asset.get("path") and log_budget:
                    raw = (directory / asset["path"]).read_bytes()
                    limit = min(log_budget, 2000)
                    logs[key] = {"text": raw[-limit:].decode(errors="replace"),
                                 "truncated": len(raw) > limit}
                    log_budget -= min(len(raw), limit)
            detail["evidence"] = logs
        jobs[name] = detail
    metrics = {}
    for name, metric in report.get("metrics", {}).items():
        item = {key: metric.get(key) for key in
                ("status", "value", "unit", "lower", "upper", "category", "observations")}
        values = [obs["value"] for obs in (item["observations"] or {}).values() if "value" in obs]
        if not values and item["value"] is not None:
            values = [item["value"]]
        item["shortfall"] = (max(0, item["lower"] - min(values))
                             if values and item["lower"] is not None else None)
        item["excess"] = (max(0, max(values) - item["upper"])
                          if values and item["upper"] is not None else None)
        metrics[name] = item
    detail = {"jobs": jobs,
              "metrics": metrics, "omitted_jobs": 0, "omitted_metrics": 0}
    while bounded and len(json.dumps(detail).encode()) > 28000:
        if jobs:
            jobs.pop(next(reversed(jobs)))
            detail["omitted_jobs"] += 1
        elif metrics:
            name = next((name for name, item in metrics.items() if item["status"] == "passed"),
                        next(reversed(metrics)))
            metrics.pop(name)
            detail["omitted_metrics"] += 1
        else:
            break
    return detail
