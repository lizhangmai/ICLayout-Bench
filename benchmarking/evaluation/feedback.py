"""Participant diagnostics: verdicts, candidate measurements and raw check files."""

import json
import os
import shutil
from pathlib import Path

from benchmarking.files import relative

# Bench provenance (host cache paths), not a tool product. The trusted report,
# plan and evaluator inputs are never job files and stay private as well.
PRIVATE_FILE_NAMES = frozenset({"support_manifest"})
CHECK_FILES_MOUNT = "/checks"
BOUNDED_INDEX_BYTES = 12000


def participant_files(report):
    """List every job output and evidence file that the participant may read."""
    files, seen = [], set()
    for job_id, job in report["jobs"].items():
        relative(job_id, "job id")
        for group in ("evidence", "outputs"):
            for name, ref in (job.get(group) or {}).items():
                path = ref.get("path")
                if not path or name in PRIVATE_FILE_NAMES:
                    continue
                target = relative(f"{job_id}/{name}", "check file")
                if target in seen:
                    if any(f["target"] == target and f["path"] == path for f in files):
                        continue
                    target = relative(f"{job_id}/{group}/{name}", "check file")
                seen.add(target)
                files.append({"target": target, "path": relative(path, "check artifact"),
                              "bytes": ref.get("bytes")})
    return files


def publish_check_files(source, files, destination):
    """Expose immutable check files read-only without copying them when possible."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for item in files:
        target = destination / item["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            origin = Path(source) / item["path"]
            try:
                os.link(origin, target)
            except OSError:
                shutil.copyfile(origin, target)
        # A rootless solver UID reads through the bind mount as "other".
        target.chmod(0o444)
    for directory in [destination, *(p for p in destination.rglob("*") if p.is_dir())]:
        directory.chmod(0o755)


def file_index(files, root, *, limit=None):
    """Group file sizes by job; a bounded reply lists as many files as fit."""
    index = {"root": root, "jobs": {}, "omitted_files": 0}
    for item in files:
        job, name = item["target"].split("/", 1)
        index["jobs"].setdefault(job, {})[name] = item["bytes"]
    if limit is not None:
        while len(json.dumps(index).encode()) > limit and index["jobs"]:
            job = next(reversed(index["jobs"]))
            entries = index["jobs"][job]
            entries.pop(next(reversed(entries)))
            index["omitted_files"] += 1
            if not entries:
                index["jobs"].pop(job)
    return index


def feedback_details(report, *, bounded=True, files=None, files_root=None):
    """Candidate verdicts and measurements; scores and evaluator inputs stay private."""
    jobs = {}
    for name, job in report["jobs"].items():
        detail = {"status": job["status"], "reason": job.get("reason", "")[:512]}
        if job.get('failure'):
            detail['failure'] = job['failure']
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
    if files is not None:
        detail["files"] = file_index(files, files_root, limit=BOUNDED_INDEX_BYTES if bounded else None)
    return detail
