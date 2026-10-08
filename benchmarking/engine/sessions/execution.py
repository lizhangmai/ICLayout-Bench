"""Record an explicitly supplied session and independently evaluate its accepted snapshot."""

import json
import time
from dataclasses import replace
from pathlib import Path

from benchmarking.engine.container_scripts import benchmark_feedback as opinions
from benchmarking.files import Asset, ReadOnlyMount, atomic_write
from benchmarking.harnesses import PROCESS_FEEDBACK_CAPABILITY

from ..evaluate import run_evaluation
from ..feedback import feedback_details
from ..inference import INFERENCE_SOURCE_FILES, USAGE_FIELDS, validate_harness_wire
from ..source import SESSION_SOURCE_FILES, evaluation_identity, package_source
from .environment import task_message
from .recorder import RecordingError, RunRecorder

__all__ = ["run_session"]


def _zero_attempt_score(method="layout"):
    """Return zero for a conclusive incomplete solve."""
    return {"method": method, "value": 0.0, "maximum": 100, "reference": 100,
            "components": {"G": 0.0, "E": None, "Q": None}}


def run_session(task, config, resources, backends, destination: Path, *, session, inference=None, execution=None):
    if task.hours is not None:
        config = replace(config, wall_seconds=task.wall_seconds)
    if task.evaluation is None or task.evaluation.mode != "post_layout":
        raise ValueError("Agent runs require a post_layout task plan")
    operations = {job.operation for job in task.evaluation.jobs}
    if not operations <= backends.keys():
        raise ValueError("Missing evaluation backend bindings")
    if inference:
        validate_harness_wire(config.harness.wire_api, inference.config.wire_api)
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    execution = json.loads(json.dumps(execution, allow_nan=False))
    recorder = RunRecorder(destination)
    archive = recorder.archive
    message = task_message(task, config)
    report = {"events": {"path": "events.jsonl"}, "run_kind": "offline_cli_development", "task_sha256": task.digest,
              "task_witnessed": task.witnessed,
              "agent_id": config.id, "harness": config.harness.identity(),
              "configuration": archive(config.source), "execution": execution,
              "command": list(config.command), "public_environment": config.environment,
              "prompt": archive(Asset(message.encode(), "text")),
              "task": archive(task.evaluation_inputs()["task"]),
              "inputs": {role: archive(asset) for role, asset in task.input_assets().items()},
              "agent_files": {name: archive(a) for name, a in config.files.items()},
              "resources": {name: archive(a.provenance if isinstance(a, ReadOnlyMount) else a)
                            for name, a in resources.items()},
              "implementation": {name: archive(Asset(package_source(name).read_bytes(), "python"))
                                 for name in ("engine/feedback.py", *SESSION_SOURCE_FILES,
                                              "engine/container_scripts/snapshot.py",
                                              "engine/container_scripts/workspace.py",
                                              "engine/container_scripts/submit.py",
                                              "engine/container_scripts/process_check.py",
                                              "engine/container_scripts/benchmark_feedback.py",
                                              "harnesses.py")},
              "usage": {field: None for field in USAGE_FIELDS},
              "phase": "running", "outcome": None, "task_success": None, "evaluation": None,
              "budget_policy": "soft" if config.soft_budget else "hard"}
    if (task.evaluation.scoring is not None
            and task.evaluation.scoring.method == "layout"):
        # Keep evaluator or infrastructure failures visibly pending for a
        # scored task. Unscored standalone runs do not claim an official score.
        report["score"] = None
    def save():
        recorder.save(report)

    if inference:
        inference.recorder = recorder
        report.update(run_kind="model_protocol_test" if inference.is_test else "model_cli_development",
                      inference_profile=archive(inference.config.source), inference=inference.public)
        for filename in INFERENCE_SOURCE_FILES:
            name = "engine/inference/" + filename
            report["implementation"][name] = archive(Asset(package_source(name).read_bytes(), "python"))
    save()
    recorder.event("run.started", task_sha256=task.digest, agent_id=config.id)
    feedback_enabled = PROCESS_FEEDBACK_CAPABILITY in config.harness.capabilities

    def process_feedback(candidate, sequence):
        feedback_root = destination / "feedback" / f"check-{sequence}"
        feedback_root.parent.mkdir(parents=True, exist_ok=True)
        evaluated = run_evaluation(
            task.evaluation,
            {**task.evaluation_inputs(), "candidate": candidate},
            backends,
            feedback_root,
            task_sha256=task.digest,
            task_witnessed=task.witnessed,
            limit_tools=not config.soft_budget,
        )
        raw = (feedback_root / "report.json").read_bytes()
        participant_report = {
            "report_id": f"check-{sequence}", "candidate_sha256": candidate.sha256,
            "evaluator_identity": evaluation_identity(task, backends),
            **{key: evaluated.get(key) for key in
               ("outcome", "physical_valid", "specs_pass", "task_success")},
            "details": feedback_details(evaluated, feedback_root, bounded=False),
        }
        atomic_write(feedback_root / "participant-report.json",
                     json.dumps(participant_report, ensure_ascii=False, allow_nan=False).encode())
        return {
            "report": evaluated,
            "evaluator_identity": evaluation_identity(task, backends),
            "details": feedback_details(evaluated, feedback_root),
            "report_id": f"check-{sequence}",
            "report_ref": archive(Asset(raw, "json")),
        }

    session_kwargs = {"inference": inference, "recorder": recorder}
    if feedback_enabled:
        session_kwargs["feedback"] = process_feedback
    result = session.run(task, config, resources, message, **session_kwargs)
    if inference:
        if inference.shutdown_incomplete:
            raise RecordingError("Inference worker did not stop; run evidence remains incomplete")
        report["inference"] = inference.summary()
        # An inference profile alone does not prove model usage.  A request
        # that was denied before forwarding must remain an offline probe, while
        # deterministic transports retain the protocol-test label once they
        # actually receive a request.
        report["run_kind"] = report["inference"]["run_kind"]
        report["usage"] = report["inference"]["usage"]
        if report["inference"]["infrastructure_error"]:
            result.termination, result.reason = "infrastructure_error", "Inference service failed; see request statuses"
        elif report["inference"]["limit_reached"] and result.termination != "infrastructure_error":
            result.termination, result.reason = "budget_exhausted", "Inference request budget exhausted"
    report.update(phase="stopped", termination=result.termination, reason=result.reason,
                  elapsed_seconds=result.elapsed_seconds, exit_code=result.exit_code,
                  budget_overrun_seconds=max(0.0, result.elapsed_seconds - config.wall_seconds),
                  submissions=result.submissions, console=archive(result.console),
                  console_truncated=result.console_truncated, environment=result.environment,
                  candidate=archive(result.candidate) if result.candidate is not None else None)
    if feedback_enabled:
        report["process_feedback"] = {"capability": PROCESS_FEEDBACK_CAPABILITY,
                                      "checks": result.process_feedback}
    if opinions.CAPABILITY in config.harness.capabilities:
        report["benchmark_feedback"] = {"capability": opinions.CAPABILITY,
                                        "reports": result.benchmark_feedback}
    save()  # Preserve submission/termination even if independent evaluation cannot finish.
    if result.candidate is not None:
        started = time.monotonic()
        try:
            evaluated = run_evaluation(task.evaluation,
                                       {**task.evaluation_inputs(), "candidate": result.candidate},
                                       backends, destination / "evaluation", task_sha256=task.digest,
                                       task_witnessed=task.witnessed, limit_tools=not config.soft_budget)
            report.update(evaluation={"path": "evaluation/report.json",
                                     "sha256": Asset((destination/"evaluation/report.json").read_bytes(), "json").sha256},
                          outcome=evaluated["outcome"], task_success=evaluated["task_success"])
            if evaluated.get("score") is not None:
                report["score"] = evaluated["score"]
        except Exception as error:  # noqa: BLE001 -- retain the accepted snapshot on infrastructure failure
            report.update(outcome="error", task_success=None, evaluation_error=str(error))
        report["evaluation_seconds"] = time.monotonic() - started
    else:
        report.update(outcome="no_submission", task_success=False)
    if result.termination == "infrastructure_error":
        report.update(outcome="error", task_success=None)
        report["score"] = None
    elif (task.evaluation.scoring is not None
          and task.evaluation.scoring.method == "layout"
          and (result.termination in {"agent_error", "budget_exhausted"}
               or report["outcome"] == "no_submission")):
        # A timed-out or otherwise incomplete Agent attempt is a conclusive
        # zero for the planned repetition, even when it left a candidate that
        # the evaluator could inspect. A no-submission attempt has the same
        # model outcome and needs an explicit score envelope for scored tasks.
        report["score"] = _zero_attempt_score(task.evaluation.scoring.method)
    recorder.finish(report)
    return report
