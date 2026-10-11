"""Verify frozen single-run evidence independently of experiment scheduling."""

import json
import math
from pathlib import Path

from benchmarking.engine.container_scripts import benchmark_feedback as opinions
from benchmarking.engine.sessions.recorder import recover_submissions
from benchmarking.engine.source import source_key
from benchmarking.evaluation import parse_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY


def read_archived_asset(root, reference, label):
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
    frozen_plan = read_archived_asset(root, frozen_plan_ref, "frozen evaluation plan")
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
    evaluated_plan = read_archived_asset(run_root, plan_ref, "evaluation plan")
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
        read_archived_asset(run_root, archive, f"evaluation input {reference}")
    return parsed_plan


def _verify_process_feedback(run_root, report, implementation, task):
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
            read_archived_asset(run_root, candidate, "process feedback candidate")
        reference = check.get("report")
        if reference is None:
            if check.get("report_path") is not None:
                raise ValueError("Process feedback report path has no report artifact")
            continue
        raw = read_archived_asset(run_root, reference, "process feedback report")
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
            expected = implementation.get(source_key(name))
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


def read_benchmark_feedback(run_root, report):
    """Verify participant opinions against their receipts, not their truth."""
    declared = opinions.CAPABILITY in report.get("harness", {}).get("capabilities", [])
    recorded = report.get("benchmark_feedback")
    raw_events = read_file(run_root, "events.jsonl")
    if any(report.get('events', {}).get(key) != value for key, value in Asset(raw_events, 'jsonl').identity().items()):
        raise ValueError('Benchmark feedback journal integrity mismatch')
    events = [json.loads(line) for line in raw_events.splitlines()]
    receipts = [event["data"] for event in events if event.get("kind") == "benchmark_feedback.submitted"]
    if not declared:
        if recorded is not None or receipts:
            raise ValueError("Undeclared benchmark feedback")
        return []
    if (not isinstance(recorded, dict) or set(recorded) != {"capability", "reports"}
            or recorded["capability"] != opinions.CAPABILITY or recorded["reports"] != receipts
            or len(receipts) > opinions.MAX_REPORTS):
        raise ValueError("Benchmark feedback differs from durable receipts")
    result = []
    for sequence, item in enumerate(receipts, 1):
        if (set(item) != {"sequence", "elapsed_seconds", "task_sha256", "harness", "content"}
                or item["sequence"] != sequence or item["task_sha256"] != report["task_sha256"]
                or item["harness"] != report["harness"]
                or type(item["elapsed_seconds"]) not in {int, float}
                or not math.isfinite(item["elapsed_seconds"]) or item["elapsed_seconds"] < 0
                or item["elapsed_seconds"] >= report["environment"]["wall_seconds"]):
            raise ValueError("Invalid benchmark feedback binding")
        raw = read_archived_asset(run_root, item["content"], "benchmark feedback")
        if item["content"]["format"] != "json" or len(raw) > opinions.MAX_BYTES:
            raise ValueError("Invalid benchmark feedback content")
        content = opinions.validate_feedback(json.loads(raw))
        result.append({**item, "feedback": content})
    return result


def _run_kind_matches(report, agent):
    """Allow a configured inference profile to record that it was unused."""
    actual = report.get("run_kind")
    configured = agent["run_kind"]
    if agent.get("inference") is None:
        return actual == "offline_cli_development"
    return actual in {"offline_cli_development", configured}


def verify_frozen_run(run_root, report, *, frozen_root, task, agent, execution, implementation):
    """Verify one run against caller-supplied frozen inputs and execution bindings.

    Batch scheduling and membership are the caller's responsibility. The bindings
    contain archived task/agent assets and implementation identities; no operator
    package, admission policy or batch file is read here.
    """
    root, run_root = Path(frozen_root), Path(run_root)
    expected = execution
    if (
        report.get('phase') != 'finished'
        or report.get('execution') != expected
        or report.get('task_sha256') != task['task_sha256']
        or not _run_kind_matches(report, agent)
        or report.get('agent_id') != agent['agent_id']
        or report.get('harness') != agent['harness']
        or report.get('configuration', {}).get('sha256') != agent['source']['sha256']
        or report.get('command') != agent['command']
        or report.get('public_environment') != agent['environment']
        or report.get('environment', {}).get('image_id') != agent['image_id']
    ):
        raise ValueError("Run does not match its frozen execution conditions")
    for name, ref in report.get("implementation", {}).items():
        expected_source = implementation.get(source_key(name))
        if expected_source is None or ref["sha256"] != expected_source["sha256"]:
            raise ValueError("Run implementation differs from frozen framework")
    task_description = json.loads(read_archived_asset(root, task["description"], "task description"))
    for key, value in agent["budget"].items():
        if key == "wall_seconds" and "hours" in task_description:
            value = task_description["hours"] * 3600
        if report["environment"].get(key) != value:
            raise ValueError("Run budget differs from its frozen plan")
    for group, expected_files in (("agent_files", agent["files"]),
                                  ("resources", task.get("resources", agent["resources"])),
                                  ("inputs", task["inputs"])):
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
    events = report.get("events")
    if (
        not isinstance(events, dict)
        or events.get('path') != 'events.jsonl'
        or any((events.get(key) != value for key, value in Asset(read_file(run_root, events['path']), 'jsonl').identity().items()))
    ):
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
            if digest != implementation[source_key(name)]["sha256"]:
                raise ValueError("Evaluation implementation differs from frozen framework")
        expected_backends = {op: task["backends"][op] for op in task["operations"]}
        if (evaluation.get("task_sha256") != task["task_sha256"] or evaluation["backends"] != expected_backends
                or evaluation.get("task_witnessed") != task["witnessed"]):
            raise ValueError("Evaluation does not match its task, candidate or toolchain")
        evaluation["_frozen_plan"] = _verify_evaluation_inputs(root, run_root, evaluation, report, task)
    _verify_process_feedback(run_root, report, implementation, task)
    read_benchmark_feedback(run_root, report)
    return report, evaluation


def verify_service_result(store, result, *, frozen, image_id):
    """Compare a service result with run evidence and caller-frozen task bindings."""
    from benchmarking.engine.sessions.archive import RunArchive

    archive = RunArchive.for_session(store, result['session_id'])
    if archive is None:
        raise ValueError('Missing service archive')
    run_root = archive.root
    report = json.loads((run_root / "run.json").read_bytes())

    outcome = {"passed": "pass", "failed": "fail", "no_submission": "no_submission", "error": "error"}[
        report["outcome"]
    ]
    if (
        result["outcome"] != outcome
        or result["task_success"] != report["task_success"]
        or result["score"] != report.get("score")
        or result["limits"] != frozen["limits"]
        or report["environment"]["image_id"] != image_id
        or result["tool_identity"]["image_id"] != image_id
        or result["tool_identity"]["evaluator"] != frozen["evaluator"]
        or {k: v["sha256"] for k, v in report["resources"].items()} != frozen["resources"]
    ):
        raise ValueError("Result differs from frozen execution evidence")
    recovered = recover_submissions(run_root)
    if recovered["candidate"] != report["candidate"]:
        raise ValueError("Submission recovery mismatch")
    if report["candidate"] and report["candidate"]["sha256"] != result["submission"]["candidate_sha256"]:
        raise ValueError("Result candidate mismatch")
    if report.get("evaluation"):
        evaluation = read_file(run_root, report["evaluation"]["path"])
        if Asset(evaluation, "json").sha256 != report["evaluation"]["sha256"]:
            raise ValueError("Evaluation digest mismatch")
        evaluated = json.loads(evaluation)
        if evaluated["plan"]["sha256"] != frozen["evaluation_plan_sha256"]:
            raise ValueError("Evaluation plan differs from frozen task")
        if evaluated["backends"] != frozen["backends"]:
            raise ValueError("Evaluation backend differs from frozen task")
        if {k: v["sha256"] for k, v in evaluated["inputs"].items() if k != "candidate"} != frozen[
            "evaluation_inputs"
        ]:
            raise ValueError("Evaluation inputs differ from frozen task")
        if evaluated.get("score") != result["score"]:
            raise ValueError("Score differs from trusted evaluation")
