"""Recompute internal development statistics from verified frozen run evidence.

This is not a public/hidden-task export policy. Outputs belong to the same
trusted operator as the complete batch directory.
"""

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist

from .admission import restore_policy
from .evaluation import parse_evaluation
from .files import Asset, read_file
from .harnesses import PROCESS_FEEDBACK_CAPABILITY
from .provenance import json_asset
from .recorder import recover_submissions
from .scoring import recompute_score

_BENCH_SCORE_METHOD = "bench-v1"
_TASK_SCORE_METHOD = "layout-v1"
_SCORE_MAXIMUM = 100


def wilson(successes, count):
    """Two-sided 95% Wilson score interval; no fictitious zero-width extremes."""
    if type(count) is not int or type(successes) is not int or not 0 <= successes <= count:
        raise ValueError("Invalid binomial counts")
    if count == 0:
        return None
    z = NormalDist().inv_cdf(.975)
    rate = successes / count
    denominator = 1 + z*z/count
    center = (rate + z*z/(2*count)) / denominator
    half = z * math.sqrt(rate*(1-rate)/count + z*z/(4*count*count)) / denominator
    return [max(0.0, center-half), min(1.0, center+half)]


def _read_json(root, reference):
    raw = read_file(root, reference["path"])
    if any(reference[key] != value for key, value in Asset(raw, "json").identity().items()):
        raise ValueError("Report artifact integrity mismatch")
    return json.loads(raw)


def _distribution(values):
    known = [v for v in values if type(v) in {int, float} and math.isfinite(v) and v >= 0]
    return {"count": len(values), "known": len(known), "missing": len(values)-len(known),
            "sum": sum(known) if known and len(known) == len(values) else None,
            "mean_known": sum(known)/len(known) if known else None,
            "min_known": min(known) if known else None, "max_known": max(known) if known else None}


def _resources(reports):
    result = {field: _distribution([(r.get("usage") or {}).get(field) if r else None for r in reports])
              for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens", "cost")}
    result["wall_seconds"] = _distribution([r.get("elapsed_seconds") if r else None for r in reports])
    return result


def _inference_resources(reports):
    """Summarize gateway resource evidence without treating tokens as compute."""
    failed = {"service_error", "http_error", "protocol_or_transport_error",
              "incomplete_error", "cancelled"}
    gateways = [r.get("inference") for r in reports
                if isinstance(r, dict) and isinstance(r.get("inference"), dict)]
    requests = [event for gateway in gateways for event in gateway.get("requests", [])]
    outcomes = [event.get("outcome") for event in requests]
    usage = {}
    for field in ("input_tokens", "output_tokens", "cached_input_tokens",
                  "reasoning_output_tokens", "cost"):
        values = [(event.get("usage") or {}).get(field) for event in requests]
        known = sum(value is not None for value in values)
        usage[field] = {"known": known, "missing": len(values) - known,
                        "total": sum(values) if values and known == len(values) else None}
    return {
        "forwarded": len(requests),
        "denied": sum((gateway.get("denied_requests") or 0) for gateway in gateways),
        "failed": sum(outcome in failed for outcome in outcomes),
        "truncated": sum(outcome == "budget_truncated" for outcome in outcomes),
        "content_filtered": sum(outcome == "content_filtered" for outcome in outcomes),
        "cancelled": sum(outcome == "cancelled" for outcome in outcomes),
        "wall_seconds": _distribution([gateway.get("wall_seconds") for gateway in gateways]),
        "usage": usage,
    }


def _read_archived_asset(root, reference, label):
    """Read and verify an archive reference from a trusted run directory."""
    if not isinstance(reference, dict) or set(reference) != {"sha256", "format", "bytes", "path"}:
        raise ValueError(f"Invalid {label} archive reference")
    if reference["path"] != f"artifacts/{reference['sha256']}":
        raise ValueError(f"Invalid {label} archive path")
    try:
        raw = read_file(root, reference["path"])
        identity = Asset(raw, reference["format"]).identity()
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid {label} archive") from error
    expected = {key: reference[key] for key in ("sha256", "format", "bytes")}
    if identity != expected:
        raise ValueError(f"{label} archive integrity mismatch")
    return raw


def _verify_evaluation_inputs(root, run_root, evaluation, report, task):
    """Verify the evaluator consumed the frozen plan and declared task inputs.

    The independent evaluator writes its own content-addressed copies. Merely
    checking the evaluation report's digest does not establish that its plan
    and inputs are the ones frozen in the batch manifest, so verify both the
    references and their bytes here.
    """
    task_inputs = task.get("inputs")
    frozen_plan_ref = task_inputs.get("evaluation") if isinstance(task_inputs, dict) else None
    if frozen_plan_ref is None:
        raise ValueError("Task has no frozen evaluation plan")
    frozen_plan = _read_archived_asset(root, frozen_plan_ref, "frozen evaluation plan")
    if frozen_plan_ref.get("format") not in {"toml", "json"}:
        raise ValueError("Frozen evaluation plan has the wrong format")

    plan_ref = evaluation.get("plan")
    if not isinstance(plan_ref, dict):
        raise TypeError("Evaluation report has no plan archive")
    # The path is local to each run directory, but the content identity must
    # exactly equal the task input frozen in execution.json.
    if {key: plan_ref.get(key) for key in ("sha256", "format", "bytes")} != {
            key: frozen_plan_ref.get(key) for key in ("sha256", "format", "bytes")}:
        raise ValueError("Evaluation plan differs from the frozen task plan")
    evaluated_plan = _read_archived_asset(run_root, plan_ref, "evaluation plan")
    if evaluated_plan != frozen_plan:
        raise ValueError("Evaluation plan differs from the frozen task plan")
    try:
        parsed_plan = parse_evaluation(frozen_plan, file_format=frozen_plan_ref["format"])
        external_inputs = parsed_plan.external_inputs()
    except (TypeError, ValueError) as error:
        raise ValueError("Frozen evaluation plan is invalid") from error

    expected = {}
    for reference in sorted(external_inputs):
        if reference == "candidate":
            expected[reference] = report.get("candidate")
        elif reference == "task":
            expected[reference] = task.get("description")
        elif reference.startswith("input:"):
            role = reference.removeprefix("input:")
            expected[reference] = task_inputs.get(role)
        else:  # parse_evaluation currently rejects this, keep the boundary explicit.
            raise ValueError(f"Unsupported evaluation input reference: {reference}")
        if expected[reference] is None:
            raise ValueError(f"Evaluation input is not frozen: {reference}")
    actual = evaluation.get("inputs")
    if actual != expected:
        raise ValueError("Evaluation inputs differ from the frozen task inputs")
    for reference, archive in actual.items():
        _read_archived_asset(run_root, archive, f"evaluation input {reference}")
    return parsed_plan


def _verify_process_feedback(root, run_root, report, manifest, task):
    """Verify optional process checks without making them the final score."""
    capabilities = report.get("harness", {}).get("capabilities", [])
    feedback = report.get("process_feedback")
    if PROCESS_FEEDBACK_CAPABILITY not in capabilities:
        if feedback is not None:
            raise ValueError("Process feedback is not declared by the harness")
        return
    if (not isinstance(feedback, dict)
            or feedback.get("capability") != PROCESS_FEEDBACK_CAPABILITY
            or not isinstance(feedback.get("checks"), list)):
        raise ValueError("Process feedback evidence is malformed")
    expected_backends = {op: task["backends"][op] for op in task["operations"]}
    for sequence, check in enumerate(feedback["checks"], 1):
        if (not isinstance(check, dict) or check.get("sequence") != sequence
                or type(check.get("accepted")) is not bool
                or type(check.get("elapsed_seconds")) not in {int, float}
                or check["elapsed_seconds"] < 0):
            raise ValueError("Process feedback sequence is invalid")
        candidate = check.get("candidate")
        if candidate is not None:
            if not isinstance(candidate, dict) or candidate.get("format") != "gds":
                raise ValueError("Process feedback candidate has the wrong format")
            _read_archived_asset(run_root, candidate, "process feedback candidate")
        reference = check.get("report")
        if reference is None:
            if check.get("report_path") is not None:
                raise ValueError("Process feedback report path has no report artifact")
            continue
        raw = _read_archived_asset(run_root, reference, "process feedback report")
        try:
            evaluated = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("Process feedback report is not JSON") from error
        if not isinstance(evaluated, dict):
            raise TypeError("Process feedback report is not an object")
        path = check.get("report_path")
        if not isinstance(path, str) or not path.endswith("/report.json"):
            raise ValueError("Process feedback report path is invalid")
        local = read_file(run_root, path)
        if local != raw:
            raise ValueError("Process feedback report copy differs from its archive")
        if (evaluated.get("task_sha256") != task["task_sha256"]
                or evaluated.get("backends") != expected_backends):
            raise ValueError("Process feedback report does not match its task or toolchain")
        for name, digest in evaluated.get("engine_sha256", {}).items():
            expected = manifest["framework"]["files"].get("benchmarking/" + name)
            if expected is None or digest != expected["sha256"]:
                raise ValueError("Process feedback evaluator differs from frozen framework")
        inputs = evaluated.get("inputs", {})
        evaluated_candidate = inputs.get("candidate") if isinstance(inputs, dict) else None
        if candidate is None or not isinstance(evaluated_candidate, dict):
            raise ValueError("Process feedback report has no frozen candidate")
        identity = {key: candidate[key] for key in ("sha256", "format", "bytes")}
        actual_identity = {key: evaluated_candidate.get(key)
                           for key in ("sha256", "format", "bytes")}
        if actual_identity != identity:
            raise ValueError("Process feedback evaluated a different candidate")
        if (check.get("outcome") != evaluated.get("outcome")
                or check.get("physical_valid") != evaluated.get("physical_valid")
                or check.get("specs_pass") != evaluated.get("specs_pass")
                or check.get("task_success") != evaluated.get("task_success")
                or check.get("tool_identity") != evaluated.get("backends")):
            raise ValueError("Process feedback summary differs from its report")


def _failure_modes(report, evaluation):
    """Return conclusive model failure causes for one measured attempt."""
    modes = Counter()
    if report.get("outcome") == "no_submission":
        modes["no_submission"] += 1
        return modes
    if report.get("task_success") is not False:
        return modes
    if evaluation is None:
        modes["task_failure_without_evaluation"] += 1
        return modes
    for job_id, job in evaluation.get("jobs", {}).items():
        if job.get("status") == "failed":
            modes[f"job:{job.get('gate') or job.get('stage')}:{job_id}"] += 1
        elif job.get("status") == "error":
            # This can coexist with a conclusive failure elsewhere. Preserve
            # it as a diagnostic cause without turning the attempt into an
            # evaluation-only sample.
            modes[f"evaluation_error:job:{job_id}"] += 1
    for metric_id, metric in evaluation.get("metrics", {}).items():
        if metric.get("status") == "failed":
            modes[f"metric:{metric_id}"] += 1
        elif metric.get("status") == "error":
            modes[f"evaluation_error:metric:{metric_id}"] += 1
    return modes


def _run_kind_matches(report, agent):
    """Allow a configured inference profile to record that it was unused."""
    actual = report.get("run_kind")
    configured = agent["run_kind"]
    if agent.get("inference") is None:
        return actual == "offline_cli_development"
    return actual in {"offline_cli_development", configured}


def _verify_batch_events(root, batch):
    """Validate journal structure; a finished batch also binds its bytes."""
    events = batch.get("events")
    if (not isinstance(events, dict) or events.get("schema_version") != 1
            or events.get("path") != "events.jsonl"):
        raise ValueError("Batch event journal reference is missing")
    try:
        raw = read_file(root, events["path"])
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ValueError("Batch event journal is unavailable") from error
    finished = batch.get("phase") == "finished"
    if finished:
        identity = Asset(raw, "jsonl").identity()
        if any(events.get(key) != value for key, value in identity.items()):
            raise ValueError("Batch event journal integrity mismatch")
    expected_sequence = 1
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            if finished:
                raise ValueError("Finished batch event journal has an incomplete tail")
            break
        try:
            event = json.loads(line)
        except (TypeError, ValueError) as error:
            raise ValueError("Batch event journal contains invalid JSON") from error
        if (not isinstance(event, dict) or event.get("schema_version") != 1
                or event.get("sequence") != expected_sequence):
            raise ValueError("Batch event journal sequence is invalid")
        expected_sequence += 1


def verify_run(root, entry, manifest, execution_sha):
    report = _read_json(root, entry["report"])
    expected = {key: entry[key] for key in ("slot_id", "task_id", "configuration_id", "repeat", "attempt")}
    expected["execution_sha256"] = execution_sha
    task, agent = manifest["tasks"][entry["task_id"]], manifest["agents"][entry["configuration_id"]]
    if (report.get("schema_version") != 2 or report.get("phase") != "finished"
            or report.get("execution") != expected or report.get("task_sha256") != task["task_sha256"]
            or not _run_kind_matches(report, agent) or report.get("agent_id") != agent["agent_id"]
            or report.get("harness") != agent["harness"]
            or report.get("configuration", {}).get("sha256") != agent["source"]["sha256"]
            or report.get("command") != agent["command"] or report.get("public_environment") != agent["environment"]
            or report.get("environment", {}).get("image_id") != agent["image_id"]):
        raise ValueError("Run does not match its frozen execution conditions")
    for name, ref in report.get("implementation", {}).items():
        expected_source = manifest["framework"]["files"].get("benchmarking/" + name)
        if expected_source is None or ref["sha256"] != expected_source["sha256"]:
            raise ValueError("Run implementation differs from frozen framework")
    for key, value in agent["budget"].items():
        if report["environment"].get(key) != value:
            raise ValueError("Run budget differs from its frozen plan")
    for group, expected_files in (("agent_files", agent["files"]), ("resources", agent["resources"]), ("inputs", task["inputs"])):
        actual = {key: value["sha256"] for key, value in report.get(group, {}).items()}
        if actual != {key: value["sha256"] for key, value in expected_files.items()}:
            raise ValueError("Run inputs differ from its frozen plan")
    if agent["inference"]:
        if report.get("inference_profile", {}).get("sha256") != agent["inference"]["source"]["sha256"]:
            raise ValueError("Run inference profile differs from plan")
        actual_inference = report.get("inference")
        if not isinstance(actual_inference, dict) or actual_inference.get("run_kind") != report.get("run_kind"):
            raise ValueError("Run inference usage identity is missing or inconsistent")
        if any(actual_inference.get(key) != value for key, value in agent["inference"]["identity"].items()):
            raise ValueError("Actual inference endpoint/model differs from plan")
    elif "inference" in report:
        raise ValueError("Offline plan unexpectedly used inference")
    run_root = (root / entry["report"]["path"]).parent
    events = report.get("events")
    if (not isinstance(events, dict) or events.get("schema_version") != 1
            or events.get("path") != "events.jsonl"
            or any(events.get(key) != value for key, value in
                   Asset(read_file(run_root, events["path"]), "jsonl").identity().items())):
        raise ValueError("Run event journal integrity mismatch")
    recovered = recover_submissions(run_root)
    if recovered["candidate"] != report.get("candidate"):
        raise ValueError("Reported candidate differs from the last durable submission")
    evaluation = None
    if report.get("evaluation"):
        ref = report["evaluation"]
        raw = read_file(run_root, ref["path"])
        if Asset(raw, "json").sha256 != ref["sha256"]:
            raise ValueError("Evaluation report integrity mismatch")
        evaluation = json.loads(raw)
        for name, digest in evaluation["engine_sha256"].items():
            if digest != manifest["framework"]["files"]["benchmarking/" + name]["sha256"]:
                raise ValueError("Evaluation implementation differs from frozen framework")
        expected_backends = {op: task["backends"][op] for op in task["operations"]}
        if (evaluation.get("task_sha256") != task["task_sha256"] or evaluation["backends"] != expected_backends
                or evaluation.get("task_witnessed") != task["witnessed"]):
            raise ValueError("Evaluation does not match its task, candidate or toolchain")
        evaluation["_frozen_plan"] = _verify_evaluation_inputs(root, run_root, evaluation, report, task)
    _verify_process_feedback(root, run_root, report, manifest, task)
    return report, evaluation


def _score_statistics(manifest):
    """Validate and return the one scoring binding frozen for this batch."""
    statistics = manifest.get("statistics")
    if (not isinstance(statistics, dict)
            or statistics.get("schema_version") != 1
            or statistics.get("method") != _BENCH_SCORE_METHOD
            or statistics.get("task_score_method") != _TASK_SCORE_METHOD
            or statistics.get("maximum") != _SCORE_MAXIMUM):
        raise ValueError("Execution manifest has no supported BenchScore binding")
    task_identity = {
        task_id: {"task_sha256": task["task_sha256"], "coefficient": task.get("coefficient"),
                  "score_method": task.get("score_method")}
        for task_id, task in sorted(manifest.get("tasks", {}).items())
    }
    if (not task_identity or any(type(item["coefficient"]) is not int
                                 or not 1 <= item["coefficient"] <= 5
                                 or item["score_method"] != _TASK_SCORE_METHOD
                                 for item in task_identity.values())):
        raise ValueError("Execution manifest has invalid task score coefficients")
    expected = json_asset({
        "schema_version": statistics["schema_version"],
        "method": statistics["method"],
        "task_score_method": statistics["task_score_method"],
        "maximum": statistics["maximum"],
        "tasks": task_identity,
    }).sha256
    if statistics.get("suite_sha256") != expected:
        raise ValueError("Execution manifest has an invalid score suite binding")
    return statistics


def _validate_score_record(score, label):
    """Validate the stable score identity shared by evaluator and batch."""
    if not isinstance(score, dict):
        raise TypeError(f"{label} is missing")
    if (score.get("method") != _TASK_SCORE_METHOD
            or score.get("maximum") != _SCORE_MAXIMUM):
        raise ValueError(f"{label} has an unsupported method or maximum")
    value = score.get("value")
    if (value is not None
            and (type(value) not in {int, float} or not math.isfinite(value)
                 or not 0 <= value <= _SCORE_MAXIMUM)):
        raise ValueError(f"{label} has an invalid value")
    return value


def _recompute_evaluation_score(evaluation):
    """Ask the scoring core to recompute from jobs and metric observations."""
    plan = evaluation.get("_frozen_plan") if isinstance(evaluation, dict) else None
    if plan is None:
        return None
    return recompute_score(plan, evaluation)


def _score_observation(report, evaluation, statistics):
    """Return one frozen repetition's score, or ``None`` when it is unknown."""
    # A candidate produced before an Agent error or budget stop is not a
    # completed solve. The public BenchScore contract therefore gives the
    # scheduled repetition zero, while infrastructure termination remains
    # unknown and is excluded from measured results by the caller.
    if report.get("termination") in {"agent_error", "budget_exhausted"}:
        return 0.0
    # A measured run without a candidate is a conclusive model failure.  It
    # has no evaluator report from which to reconstruct a score, but the
    # layout-v1 contract gives such a run zero points.
    if report.get("outcome") == "no_submission":
        if report.get("candidate") is None:
            return 0.0
        raise ValueError("No-submission report contains a candidate")
    if evaluation is None:
        return None
    recomputed = _recompute_evaluation_score(evaluation)
    if recomputed is None:
        return None
    recomputed_value = _validate_score_record(recomputed, "Recomputed task score")
    declared = evaluation.get("score")
    if declared is None:
        if isinstance(recomputed, dict):
            raise ValueError("Evaluation task score is missing")
        return None
    declared_value = _validate_score_record(declared, "Evaluation task score")
    if ((recomputed_value is None) != (declared_value is None)
            or recomputed_value is not None
            and not math.isclose(recomputed_value, declared_value, rel_tol=1e-12, abs_tol=1e-12)):
        raise ValueError("Evaluation task score differs from recomputation")
    # run_agent copies the evaluator score into run.json for convenience. It
    # remains untrusted evidence, so verify it when present and use only the
    # independently recomputed value below.
    reported = report.get("score")
    if reported is not None:
        reported_value = _validate_score_record(reported, "Run task score")
        if ((recomputed_value is None) != (reported_value is None)
                or recomputed_value is not None
                and not math.isclose(recomputed_value, reported_value, rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError("Run task score differs from recomputation")
    elif isinstance(recomputed, dict):
        raise ValueError("Run task score is missing")
    return recomputed_value


def _bench_score_cohort(manifest, slots, score_observations, score_results,
                        configuration_id, run_kind, statistics):
    """Aggregate all task environments for one compatible model cohort."""
    task_rows = {}
    complete = True
    coefficient_total = 0
    unknown = 0
    missing = 0
    environment_groups = set()
    for task_id, task in sorted(manifest["tasks"].items()):
        environment_groups.add(task["environment_group"])
        selected = [slot for slot in slots.values()
                    if slot["task_id"] == task_id and slot["configuration_id"] == configuration_id]
        matching = []
        for slot in selected:
            observed = score_observations.get(slot["slot_id"])
            if observed is None:
                continue
            report, _ = observed
            if report.get("run_kind") == run_kind:
                matching.append((slot, score_results[slot["slot_id"]]))
        values = [value for _, value in matching if value is not None]
        task_missing = len(selected) - len(matching)
        task_unknown = len(matching) - len(values)
        task_complete = task_missing == 0 and task_unknown == 0
        if not task_complete:
            complete = False
        missing += task_missing
        unknown += task_unknown
        coefficient = task["coefficient"]
        coefficient_total += coefficient
        task_rows[task_id] = {
            "coefficient": coefficient,
            "scheduled": len(selected),
            "measured": len(matching),
            "missing": task_missing,
            "unknown": task_unknown,
            "value": sum(values) / len(selected) if task_complete else None,
            "maximum": statistics["maximum"],
        }
    value = (sum(row["coefficient"] * row["value"] for row in task_rows.values()) / coefficient_total
             if complete and coefficient_total else None)
    return {
        "method": _BENCH_SCORE_METHOD,
        "task_score_method": statistics["task_score_method"],
        "maximum": statistics["maximum"],
        "value": value,
        "suite_sha256": statistics["suite_sha256"],
        "configuration_id": configuration_id,
        "run_kind": run_kind,
        "complete": complete,
        "task_count": len(task_rows),
        "family_count": len({manifest["tasks"][task_id]["family"] for task_id in task_rows}),
        "coefficient_total": coefficient_total,
        "missing": missing,
        "unknown": unknown,
        "environment_groups": sorted(environment_groups),
        "tasks": task_rows,
    }


def summarize_batch(destination, *, allow_in_progress=False):
    """Verify a finished batch and recompute its statistics.

    ``execute_plan`` asks for one provisional summary immediately before it
    seals the batch journal.  That internal call opts into the in-progress
    state; public summaries may inspect an interrupted, incomplete batch for
    diagnosis, but cannot treat an unsealed complete batch as scoreable.
    """
    root = Path(destination).absolute()
    batch = json.loads(read_file(root, "batch.json"))
    if batch.get("schema_version") != 1 or batch.get("run_kind") != "local_batch_development":
        raise ValueError("Unsupported batch report")
    if batch.get("phase") not in {"running", "finished"}:
        raise ValueError("Batch is not executable")
    # During execute_plan the runner computes a provisional summary before
    # sealing batch.json. A persisted summary on a non-finished record is
    # therefore an inconsistent/stale final record, not a scoreable batch.
    if batch.get("phase") != "finished" and batch.get("summary") is not None:
        raise ValueError("Batch has an unsealed summary")
    _verify_batch_events(root, batch)
    manifest = _read_json(root, batch["execution"])
    if manifest.get("schema_version") != 1 or manifest.get("run_kind") != "local_batch_development":
        raise ValueError("Unsupported execution manifest")
    statistics = _score_statistics(manifest)
    for task_id, task in manifest["tasks"].items():
        description = _read_archived_asset(root, task["description"], f"task {task_id} description")
        try:
            description = json.loads(description)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Task {task_id} description is not JSON") from error
        scoring = description.get("evaluation", {}).get("scoring") if isinstance(
            description.get("evaluation"), dict) else None
        if (description.get("id") != task_id
                or description.get("task_sha256") != task["task_sha256"]
                or description.get("coefficient") != task["coefficient"]
                or not isinstance(scoring, dict)
                or scoring.get("method") != task["score_method"]):
            raise ValueError(f"Task {task_id} score binding differs from its description")
    if "admission" in manifest:
        policy = restore_policy(root, manifest, manifest["admission"]["policy"]["sha256"])
        reservation = batch.get("admission_reservation", {})
        if (reservation.get("policy_sha256") != policy.source.sha256
                or reservation.get("execution_sha256") != batch["execution"]["sha256"]):
            raise ValueError("Batch has no matching admission reservation")
    slots = {slot["slot_id"]: slot for slot in manifest["schedule"]}
    if len(slots) != len(manifest["schedule"]):
        raise ValueError("Duplicate scheduled slot")
    expected_points = {(task, agent, repeat) for task in manifest["tasks"] for agent in manifest["agents"]
                       for repeat in range(1, manifest["repetitions"] + 1)}
    points = [(s["task_id"], s["configuration_id"], s["repeat"]) for s in slots.values()]
    if not expected_points or len(points) != len(set(points)) or set(points) != expected_points:
        raise ValueError("Schedule is not the declared task/configuration/repetition product")
    results, score_observations, attempts = {}, {}, defaultdict(list)
    for entry in batch["attempts"]:
        slot = slots.get(entry["slot_id"])
        if (slot is None or any(entry[key] != value for key, value in slot.items())
                or entry["execution_sha256"] != batch["execution"]["sha256"]):
            raise ValueError("Attempt is outside the frozen schedule")
        previous = attempts[entry["slot_id"]]
        if (entry["attempt"] != len(previous)+1 or entry["attempt"] > manifest["max_infrastructure_retries"]+1
                or previous and previous[-1][0]["state"] != "infrastructure_error"):
            raise ValueError("Unscheduled retry or duplicate measurement")
        report, evaluation = verify_run(root, entry, manifest, batch["execution"]["sha256"]) if entry["report"] else (None, None)
        state = entry["state"]
        if state not in {"running", "measured", "infrastructure_error", "evaluation_error"}:
            raise ValueError("Unknown attempt state")
        if report:
            actual = ("infrastructure_error" if report["termination"] == "infrastructure_error"
                      else "evaluation_error" if report["outcome"] in {"error", "incomplete"} else "measured")
            if actual != state:
                raise ValueError("Attempt state contradicts its run report")
        elif state not in {"running", "infrastructure_error"}:
            raise ValueError("Completed measurement has no report")
        if state == "measured":
            if (report["termination"] not in {"completed", "agent_error", "budget_exhausted"}
                    or report["outcome"] not in {"passed", "failed", "no_submission"}
                    or type(report["task_success"]) is not bool
                    or report["task_success"] != (report["outcome"] == "passed")):
                raise ValueError("Invalid measured result")
            if report["candidate"] is not None:
                if evaluation is None or evaluation["task_success"] != report["task_success"]:
                    raise ValueError("Candidate result has no matching independent evaluation")
            elif report["outcome"] != "no_submission":
                raise ValueError("Missing candidate is not a successful measurement")
            results[entry["slot_id"]] = (report, evaluation)
            score_observations[entry["slot_id"]] = (report, evaluation)
        elif state == "evaluation_error" and report is not None:
            # A completed non-infrastructure attempt still occupies its
            # planned repetition for BenchScore. The scorer turns an
            # evaluator error into ``None`` while an Agent timeout/error keeps
            # its conclusive zero, even when the attempted candidate could not
            # be evaluated.
            score_observations[entry["slot_id"]] = (report, evaluation)
        attempts[entry["slot_id"]].append((entry, report, evaluation))

    # Recompute every completed non-infrastructure task score from the
    # archived evaluation jobs and observations. The run/evaluation scalar is
    # checked against that result but is never used as the source of the
    # aggregate.
    score_results = {
        slot_id: _score_observation(report, evaluation, statistics)
        for slot_id, (report, evaluation) in score_observations.items()
    }

    groups = []
    for config_id, agent in manifest["agents"].items():
        environment_groups = sorted({task["environment_group"] for task in manifest["tasks"].values()})
        for environment in environment_groups:
            task_ids = [key for key, task in manifest["tasks"].items() if task["environment_group"] == environment]
            families = Counter(manifest["tasks"][key]["family"] for key in task_ids)
            per_task, all_attempts, measured = {}, [], []
            group_failure_modes = Counter()
            for task_id in task_ids:
                selected = [s for s in slots.values() if s["task_id"] == task_id and s["configuration_id"] == config_id]
                observed = [results[s["slot_id"]] for s in selected if s["slot_id"] in results]
                task_attempts = [row for s in selected for row in attempts[s["slot_id"]]]
                all_attempts.extend(task_attempts)
                measured.extend(observed)
                successes = sum(r["task_success"] for r, _ in observed)
                physical = sum(e["physical_valid"] is True for _, e in observed if e)
                missing = len(selected)-len(observed)
                score_values = [score_results[s["slot_id"]] for s in selected
                                if s["slot_id"] in score_results
                                and score_results[s["slot_id"]] is not None]
                score_observed = [score_results[s["slot_id"]] for s in selected
                                  if s["slot_id"] in score_results]
                score_unknown = len(score_observed) - len(score_values)
                score_missing = len(selected) - len(score_observed)
                observed_metrics = defaultdict(list)
                successful_metrics = defaultdict(list)
                failure_modes = Counter()
                for report, evaluation in observed:
                    failure_modes.update(_failure_modes(report, evaluation))
                    if evaluation:
                        for name, metric in evaluation["metrics"].items():
                            if type(metric["value"]) in {int, float} and math.isfinite(metric["value"]):
                                value = {"value": metric["value"], "unit": metric["unit"]}
                                observed_metrics[name].append(value)
                                if report["task_success"]:
                                    successful_metrics[name].append(value)
                replacements = max(0, len(task_attempts) - len(selected))
                per_task[task_id] = {
                    "family": manifest["tasks"][task_id]["family"],
                    "coefficient": manifest["tasks"][task_id]["coefficient"],
                    "scheduled": len(selected),
                    "witnessed": manifest["tasks"][task_id]["witnessed"],
                    "measured": len(observed), "missing": missing, "replacements": replacements,
                    "successes": successes,
                    "physical_valid": physical,
                    "success_rate": successes/len(selected) if not missing else None,
                    "observed_success_rate": successes/len(observed) if observed else None,
                    "observed_wilson95": wilson(successes, len(observed)),
                    "score_values": score_values,
                    "score_known": len(score_values),
                    "score_unknown": score_unknown,
                    "score_missing": score_missing,
                    "score_mean": (sum(score_values) / len(selected)
                                   if len(score_values) == len(selected) else None),
                    "observed_metrics": dict(observed_metrics),
                    "successful_metrics": dict(successful_metrics),
                    "failure_modes": dict(failure_modes)}
                group_failure_modes.update(failure_modes)
            complete = all(t["missing"] == 0 for t in per_task.values())
            finished_attempts = sum(e["state"] != "running" for e, _, _ in all_attempts)
            reported = [r for _, r, _ in all_attempts if r]
            actual_run_kinds = Counter(r.get("run_kind") for r in reported if r.get("run_kind"))
            actual_run_kind = (next(iter(actual_run_kinds)) if len(actual_run_kinds) == 1
                               else "mixed" if actual_run_kinds else agent["run_kind"])
            inference_resources = _inference_resources(reported)
            inference_requests = inference_resources["forwarded"]
            inference_denied = inference_resources["denied"]
            inference_unused = sum(1 for r in reported
                                   if r.get("inference") is not None
                                   and not (r.get("inference") or {}).get("requests"))
            groups.append({
                "configuration_id": config_id, "run_kind": actual_run_kind,
                "configured_run_kind": agent["run_kind"],
                "harness": agent["harness"], "environment_group": environment,
                "environment": manifest["tasks"][task_ids[0]]["environment"],
                "complete": complete, "tasks": per_task, "family_count": len(families),
                "success_rate": sum(t["successes"] for t in per_task.values())
                / sum(t["scheduled"] for t in per_task.values()) if complete else None,
                "physical_valid_rate": sum(t["physical_valid"] for t in per_task.values())
                / sum(t["scheduled"] for t in per_task.values()) if complete else None,
                "attempts": len(all_attempts), "attempts_finished": finished_attempts,
                "replacements": sum(task["replacements"] for task in per_task.values()),
                "infrastructure_errors": sum(e["state"] == "infrastructure_error" for e, _, _ in all_attempts),
                "evaluation_errors": sum(e["state"] == "evaluation_error" for e, _, _ in all_attempts),
                "failure_modes": dict(group_failure_modes),
                "inference_requests": inference_requests,
                "inference_denied_requests": inference_denied,
                "inference_forwarded_requests": inference_resources["forwarded"],
                "inference_failed_requests": inference_resources["failed"],
                "inference_truncated_requests": inference_resources["truncated"],
                "inference_content_filtered_requests": inference_resources["content_filtered"],
                "inference_cancelled_requests": inference_resources["cancelled"],
                "inference_wall_seconds": inference_resources["wall_seconds"],
                "inference_usage": inference_resources["usage"],
                "inference_unused_runs": inference_unused,
                "infrastructure_error_rate": sum(e["state"] == "infrastructure_error" for e, _, _ in all_attempts)/finished_attempts if finished_attempts else None,
                "termination_counts": dict(Counter(r["termination"] for r, _ in measured)),
                "outcome_counts": dict(Counter(r["outcome"] for r, _ in measured)),
                "resources": {"all_attempts": _resources([r for _, r, _ in all_attempts]),
                              "measured": _resources([r for r, _ in measured]),
                              "successful": _resources([r for r, _ in measured if r["task_success"]]),
                              "unsuccessful": _resources([r for r, _ in measured if not r["task_success"]])}})
    # A BenchScore cohort spans all declared task environments. It is formed
    # only for one configuration and one *actual* run kind, with the frozen
    # suite/judge binding above. This lets legitimate per-task EDA environments
    # participate without pooling an offline probe with a real model run.
    bench_scores = []
    for config_id, agent in manifest["agents"].items():
        actual_run_kinds = {
            report.get("run_kind") for slot_id, (report, _) in score_observations.items()
            if slots[slot_id]["configuration_id"] == config_id and report.get("run_kind")
        }
        run_kinds = sorted(actual_run_kinds or {agent["run_kind"]})
        bench_scores.extend(
            _bench_score_cohort(manifest, slots, score_observations, score_results,
                                config_id, run_kind, statistics)
            for run_kind in run_kinds
        )
    summary = {"schema_version": 1, "scope": manifest["scope"], "run_kind": "local_batch_development",
            "execution_sha256": batch["execution"]["sha256"], "statistics": manifest["statistics"],
            "statistics_implementation_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
            "complete": all(group["complete"] for group in groups), "groups": groups,
            "bench_score": {
                "schema_version": 1, "method": _BENCH_SCORE_METHOD,
                "task_score_method": statistics["task_score_method"],
                "maximum": statistics["maximum"], "suite_sha256": statistics["suite_sha256"],
                "complete": all(cohort["complete"] for cohort in bench_scores),
                "cohorts": bench_scores,
            }}
    if batch.get("phase") != "finished" and summary["complete"] and not allow_in_progress:
        raise ValueError("Batch is not finished")
    return summary
