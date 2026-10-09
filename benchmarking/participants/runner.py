"""Run participant-owned CLI loops with independent Public observation."""
import json
import math
import os
import subprocess
import time
from dataclasses import replace

from benchmarking.client import Client, ClientError
from benchmarking.files import write_json as save
from benchmarking.protocol import evaluation_mode

from . import adapters, exports
from .adapters.contracts import ParticipantSelection
from .attempt import ParticipantAttempt, protocol_condition
from .launch import ParticipantLaunch
from .lifecycle import settle_session
from .process import execute
from .recovery import (
    capacity_ready,
    classify,
    continuation_id,
    credential_values,
    failure,
    plan_capacity_resume,
    policy,
)
from .scheme import check as check_scheme

PROMPT = """Design the integrated circuit layout required by the task contract below.
You control your own conversation and tool loop. Use the declared tools; use layout MCP for the evaluation workspace;
Layout MCP file paths and commands refer to the remote EDA workspace, never this host.
Read /task/problem.md and the declared netlist first. Work in /workspace and use
reviewed resources under /resources. Write your own generator, construct real
devices/interconnect/pins, execute it and submit the declared GDS output early.
Do not copy reference solutions, create placeholders, or request other agents.
Use remaining time to diagnose and improve your candidate with available tools.
Use status to check remaining time. Submission acceptance is delivery, not a
passing verdict. Finish after submitting your best candidate; the runner closes
the session and obtains an independent evaluation. Never claim a pass yourself.
The solve budget is soft when status reports budget.policy = "soft". Every tool
reply reports remaining time. At zero remaining time, finish the operation already
in progress and submit immediately. Do not start another optimization round,
write a new generator, execute another command or request another check.
When status advertises process-feedback, use check on your current output GDS
before the final submission. It runs the same complete plan as final judging,
including strict port checks, distributed RC and electrical conditions. Checks
return engineering diagnostics, not scores or scoring breakdowns. Read the
candidate metric values and bounds; a passed job means execution succeeded, not that specs
passed. Use report with the returned report_id for paginated diagnostics. Checks
have no count limit and consume the existing wall-clock budget. Correct your
candidate while time remains. Hand-written local
tool commands are exploratory checks and do not establish evaluator acceptance.
"""
CONTINUE_PROMPT = (
    "Continue working on the current task in the same service session. "
    "Check status and review the work already completed before continuing unfinished work. "
    "The original deadline still applies."
)


def _safe_continuation(output, row, state, status):
    try:
        return continuation_id(output, row, state, status)
    except ValueError:
        return None


def resume_after_capacity(client, sid, row, output, attempt, settings, problem):
    """Keep the service alive while waiting; no new workspace, model or deadline."""
    state = attempt.state
    attempt.record_capacity_interruption(problem)
    count = state.capacity_resumes
    status = client.session(sid) if count < settings["capacity_resumes"] else None
    native_id = _safe_continuation(output, row, state, status) if status is not None else None
    decision = plan_capacity_resume(settings, count, problem, status, native_id)
    attempt.apply_capacity_decision(decision)
    if decision.outcome == "waiting":
        print(f"CAPACITY_RETRY task={row['task']} model={row.get('model', '')} "
              f"resume={count + 1}/{settings['capacity_resumes']} delay_seconds={decision.delay_seconds:.3f}", flush=True)
        time.sleep(decision.delay_seconds)
        status = client.session(sid)
        decision = capacity_ready(status, _safe_continuation(output, row, state, status))
        attempt.apply_capacity_decision(decision)
    return decision.native_id if decision.outcome == "continued" else None


def run_participant(access, row, output, selection: ParticipantSelection):
    selection = ParticipantSelection(selection.condition, selection.environment.copy(), selection.settings)
    condition, env, settings = selection.condition, selection.environment, selection.settings
    scheme = row.get("scheme", {})
    check_scheme(scheme)
    instructions = PROMPT + ("\nPARTICIPANT TOOL INSTRUCTIONS:\n" + scheme["instructions"] if scheme.get("instructions") else "")
    output.mkdir(mode=0o700, exist_ok=True)
    settings_policy = policy(row.get("recovery"), harness=row["harness"])
    if hasattr(access, "retry_policy"):
        access.retry_policy = settings_policy
    attempt = ParticipantAttempt.open(access, row, output, condition, env, instructions, settings_policy)
    state = attempt.state
    created = attempt.created
    declared_values = {os.environ[name] for spec in [*scheme.get("mcp", {}).values(),
                       *([scheme["launch"]] if "launch" in scheme else [])]
                       for name in spec["env_vars"] if len(os.environ[name]) >= 4}
    attempt.add_redactions(declared_values | credential_values(env) | credential_values(settings)
                           | {created["session_token"]})
    sid = created["session_id"]
    client = Client(access.endpoint, created["session_token"], timeout=60, retry_policy=settings_policy)
    save(output / "session.json", {k: v for k, v in created.items() if k != "session_token"})
    expected_image = scheme.get("solver_image")
    if expected_image and created.get("tool_identity", {}).get("image_id") != expected_image:
        client.close(sid, key="solver-image-mismatch-close")
        raise ValueError("Service solver image differs from the participant scheme")
    task_hours = created["task"]["description"].get("hours")
    if (type(task_hours) not in (int, float) or not math.isfinite(task_hours) or task_hours <= 0
            or not math.isfinite(task_hours * 3600)
            or not math.isclose(created["limits"]["wall_seconds"], task_hours * 3600, rel_tol=1e-9, abs_tol=1e-6)):
        client.close(sid, key="budget-mismatch-close")
        raise ValueError("Service wall_seconds must match task hours; session closed before model calls")
    status = client.session(sid)
    if status["state"] != "active":
        if state.phase == "running" or state.launches == 0:
            attempt.mark_unavailable()
            save(output / "failure.json", failure("unknown", "runner", state.error))
        return exports.collect_result(client, sid, output), state.error
    if status["remaining_seconds"] <= 0:
        client.close(sid, key="runner-close")
        return exports.collect_result(client, sid, output), "harness_timeout"
    if state.phase == "finalizing":
        return finalize_session(client, sid, created, output), state.error
    if state.launches:
        if not settings_policy["resume_session"]:
            raise ValueError("Session continuation was not enabled in frozen TOML")
        env["ICLAYOUT_BENCH_RESUME_ID"] = continuation_id(output, row, state, status)
    launch = ParticipantLaunch(row, selection, output, created)
    error, exit_code, receipt, problem = None, None, None, None
    start = time.monotonic()
    try:
        context = launch.prepare(access.endpoint, settings_policy, attempt, instructions)
        if state.launches:
            context = replace(context, prompt=CONTINUE_PROMPT)
        args = adapters.prepare(context)
        first_launch = True
        while True:
            error, problem = None, None
            if state.launches:
                context = replace(context, prompt=CONTINUE_PROMPT)
                if not first_launch:
                    args = adapters.prepare(context)
                for filename in ("harness.jsonl", "harness.stderr", "harness-summary.json"):
                    source = output / filename
                    if source.exists():
                        source.rename(output / f"launch-{state.launches}-{filename}")
            remaining = client.session(sid)["remaining_seconds"]
            if remaining <= 0:
                error, problem = "harness_timeout", failure("budget_exhausted", "deadline")
                break
            attempt.begin_launch()
            first_launch = False
            with (output / "harness.jsonl").open("w") as out, (output / "harness.stderr").open("w") as err:
                exit_code, timed_out = execute(args, cwd=context.directory, env=env, stdout=out, stderr=err,
                                              prompt=context.prompt, timeout=None if created['limits'].get('budget_policy') == 'soft' else remaining,
                                              pass_fds=tuple(int(env[k]) for k in ["ICLAYOUT_BENCH_LEASE_FD"] if k in env))
            # Retain each launch's refreshed secrets even if a later launch
            # rotates the native credential store again before terminal export.
            attempt.add_redactions(adapters.credential_redactions(row['harness'], output))
            if timed_out:
                error = "harness_timeout"
            elif exit_code:
                error = "cli_exit_" + str(exit_code)
            check_scheme(scheme)
            problem = adapters.harness_failure(row["harness"], output, exit_code, error == "harness_timeout")
            if problem and error is None:
                error = problem["category"]
            attempt.record_error(error)
            save(output / "failure.json", problem)
            save(output / "harness-summary.json", {"error": error, "failure": problem, "exit_code": exit_code,
                 "elapsed_seconds": round(time.monotonic() - start, 3), "final_receipt": receipt})
            if (settings_policy["capacity_resumes"] and problem
                    and problem["category"] == "provider_overloaded"):
                native_id = resume_after_capacity(client, sid, row, output, attempt, settings_policy, problem)
                if native_id:
                    env["ICLAYOUT_BENCH_RESUME_ID"] = native_id
                    continue
            break
    except (OSError, ValueError, ClientError, subprocess.SubprocessError) as exc:
        error = type(exc).__name__
        problem = classify(exc)
    # Persist before cleanup/transport calls, which can themselves fail.
    suspend = (error and settings_policy["resume_session"] and error != "harness_timeout"
               and not state.capacity_interruptions)
    recovery = attempt.complete(error, suspended=bool(suspend))
    save(output / "failure.json", problem)
    save(output / "harness-summary.json", {"error": error, "failure": problem, "exit_code": exit_code,
         "elapsed_seconds": round(time.monotonic() - start, 3), "final_receipt": receipt, **recovery})
    if suspend:
        return {"session_id": sid, "state": "active",
                "evaluation_mode": evaluation_mode(client.result(sid))}, error
    return finalize_session(client, sid, created, output), error


def finalize_session(client, sid, created, output, *, snapshot=True):
    summary_path = output / "harness-summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    path = created["task"]["description"]["output"]["path"].removeprefix("/workspace/")
    try:
        receipt = settle_session(client, sid, path, output, snapshot=snapshot)
        summary.pop("finalization_error", None)
        summary["final_receipt"] = receipt
        save(summary_path, summary)
        return exports.collect_result(client, sid, output)
    except (OSError, ValueError, RuntimeError, ClientError) as exc:
        journal = output / "finalization.json"
        if journal.exists():
            summary["final_receipt"] = json.loads(journal.read_text()).get("receipt")
        summary["finalization_error"] = {"error": type(exc).__name__, "failure": classify(exc)}
        save(summary_path, summary)
        raise


def recover_participant(access, row, output):
    """Collect an existing session using its frozen identity, without a launch."""
    attempt = ParticipantAttempt.load(output)
    state, frozen = attempt.state, attempt.conditions
    created = attempt.created
    sid = created["session_id"]
    client = Client(access.endpoint, created["session_token"], timeout=60,
                    retry_policy=policy(frozen.get("recovery"), harness=frozen["selection"]["harness"]))
    expected = protocol_condition(frozen)
    observed = client.result(sid)
    if observed["session_id"] != sid or observed["task_id"] != row["task"] or observed["condition"] != expected:
        raise ValueError("Existing service does not match the frozen session identity")
    summary_path = output / "harness-summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    error = summary.get("error") or state.error
    if state.phase == "running" and not summary and not error:
        error = "runner_interrupted"
    problem = summary.get("failure")
    if problem is None and (output / "failure.json").exists():
        problem = json.loads((output / "failure.json").read_text())
    if problem is None and error:
        problem = failure("unknown", "runner", error)
    attempt.begin_finalization(error)
    save(output / "failure.json", problem)
    save(summary_path, dict(summary, error=error, failure=problem,
                           recovery={"mode": "collect_only", "original_package": frozen["package"]}))
    if client.session(sid)["state"] != "active":
        return exports.collect_result(client, sid, output), error
    return finalize_session(client, sid, created, output, snapshot=False), error


def run_one(access, row, output, selection, *, collect_only=False):
    condition = selection.condition
    result, error = (recover_participant(access, row, output) if collect_only else
                     run_participant(access, row, output, selection))
    problem_path = output / "failure.json"
    problem = json.loads(problem_path.read_text()) if problem_path.exists() else None
    if result.get("state") == "error":
        problem = failure(result.get("failure_category") or "service_failure", "evaluation_service", result.get("failure_reason"))
    elif problem is None and result.get("task_success") is False:
        problem = failure("task_failure", "independent_evaluator", result.get("outcome"))
    summary = {"name": row["name"], **condition, "failure": problem,
            "state": "suspended" if result.get("state") == "active" else "finished", "session_id": result["session_id"],
            "outcome": result.get("outcome"), "score": (result.get("score") or {}).get("value"),
            "task_success": result.get("task_success"), "evaluation_mode": evaluation_mode(result),
            "harness_error": error, **({"result": "analysis/result.json"} if result.get("state") != "active" else {})}
    launch = json.loads((output / "harness-summary.json").read_text()) if (output / "harness-summary.json").exists() else {}
    if "capacity_recovery" in launch:
        summary["capacity_recovery"] = launch["capacity_recovery"]
    if problem and problem["category"] == "harness_configuration":
        summary["evaluation_result"] = {key: summary[key] for key in ("outcome", "score", "task_success")}
        summary.update(outcome="error", score=None, task_success=None)
    return summary
