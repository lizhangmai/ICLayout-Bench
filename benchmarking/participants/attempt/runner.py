"""Run participant-owned CLI loops with independent evaluation observation."""

import json
import math
import os
import signal
import subprocess
import time
from contextlib import ExitStack
from dataclasses import replace

from benchmarking.client import Client, ClientError
from benchmarking.execution.process import execute
from benchmarking.files import write_json as save
from benchmarking.participants.attempt import evidence as exports
from benchmarking.participants.attempt.launch import ParticipantLaunch
from benchmarking.participants.attempt.recovery import (
    capacity_ready,
    classify,
    continuation_id,
    credential_values,
    failure,
    plan_capacity_resume,
    plan_network_resume,
    policy,
)
from benchmarking.participants.attempt.settlement import (
    participant_expiry,
    participant_timeout,
    settle_session,
)
from benchmarking.participants.attempt.state import (
    ParticipantAttempt,
    protocol_condition,
)
from benchmarking.participants.harnesses import registry as adapters
from benchmarking.participants.harnesses.contracts import ParticipantSelection
from benchmarking.participants.harnesses.scheme import check as check_scheme
from benchmarking.participants.isolation import NativeRuntime
from benchmarking.protocol import evaluation_mode

CONTINUE_PROMPT = (
    "Continue working on the current task in the same service session. "
    "Check status and review the work already completed before continuing unfinished work. "
    "Earlier tool calls may have executed even if their replies are missing from the conversation. "
    "Use status, existing execution IDs and workspace files to decide further actions. "
    "The original deadline still applies."
)


def resume_after_failure(client, sid, row, output, attempt, settings, problem, kind):
    """Keep the service alive while waiting; no new workspace, model or deadline."""
    state = attempt.state
    attempt.record_interruption(kind, problem)
    count = getattr(state, kind + "_resumes")
    limit = settings[kind + "_resumes"]
    status = client.session(sid) if count < limit else None
    native_id = adapters.session_id(row["harness"], output, state) if status is not None else None
    plan = plan_capacity_resume if kind == "capacity" else plan_network_resume
    decision = plan(settings, count, problem, status, native_id)
    attempt.apply_resume_decision(kind, decision)
    if decision.outcome == "waiting":
        print(f"{kind.upper()}_RETRY task={row['task']} model={row.get('model', '')} "
              f"resume={count + 1}/{limit} delay_seconds={decision.delay_seconds:.3f}", flush=True)
        time.sleep(decision.delay_seconds)
        status = client.session(sid)
        decision = capacity_ready(status, adapters.session_id(row["harness"], output, state))
        attempt.apply_resume_decision(kind, decision)
    return decision.native_id if decision.outcome == "continued" else None


def run_participant(access, row, output, selection: ParticipantSelection):
    selection = ParticipantSelection(selection.condition, selection.environment.copy(), selection.settings)
    condition, env, settings = selection.condition, selection.environment, selection.settings
    scheme = row.get("scheme", {})
    check_scheme(scheme)
    instructions = scheme.get("instructions", "")
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
    if state.phase == "finalizing":
        return finalize_session(client, sid, output), state.error
    if status["remaining_seconds"] <= 0:
        attempt.begin_finalization("harness_timeout")
        return finalize_session(client, sid, output), "harness_timeout"
    continuation_prompt = CONTINUE_PROMPT
    if state.launches:
        if not settings_policy["resume_session"]:
            raise ValueError("Session continuation was not enabled in frozen TOML")
        if status.get('recovery', {}).get('workspace_restored'):
            continuation_prompt += (
                '\nThe EDA workspace was restored from its last committed checkpoint. '
                'Commands interrupted before checkpoint commit were rolled back and were not replayed. '
                'Review status, workspace files and these service recovery facts before choosing further actions:\n'
                + json.dumps(status['recovery'], ensure_ascii=False)
            )
        env["ICLAYOUT_BENCH_RESUME_ID"] = continuation_id(output, row, state)
    launch = ParticipantLaunch(row, selection, output, created)
    error, exit_code, receipt, problem = None, None, None, None
    start = time.monotonic()
    observers = ExitStack()
    try:
        observers.enter_context(adapters.observe_usage(row["harness"], output, env))
        context = launch.prepare(access.endpoint, settings_policy, attempt, instructions)
        runtime = observers.enter_context(NativeRuntime(
            context, harness=row['harness'], runtime_paths=scheme.get('runtime_paths', ()),
            files=scheme.get('launch', {}).get('files', ()),
            env_vars=scheme.get('launch', {}).get('env_vars', ())))
        context = runtime.context
        if state.launches:
            context = replace(context, prompt=continuation_prompt)
        args = adapters.prepare(context)
        first_launch = True
        while True:
            error, problem = None, None
            if state.launches:
                context = replace(context, prompt=continuation_prompt)
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
                try:
                    isolated_args, isolated_env = runtime.command(args)
                    exit_code, timed_out = execute(isolated_args, cwd=context.directory, env=isolated_env, stdout=out, stderr=err,
                                                  prompt=context.prompt, timeout=participant_timeout(created, {'remaining_seconds': remaining}),
                                                  pass_fds=tuple(int(env[k]) for k in ["ICLAYOUT_BENCH_LEASE_FD"] if k in env),
                                                  expired=participant_expiry(client, sid, remaining))
                finally:
                    # Keep refreshed secrets in redactions before credential synchronization,
                    # including native process failures and interrupted launches.
                    attempt.add_redactions(adapters.credential_redactions(row['harness'], output))
                    adapters.sync_credentials(row['harness'], output / '.private', env, settings)
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
            kind = None
            rate_limited = (settings_policy["resume_session"] and problem
                            and exit_code is not None and exit_code > 0
                            and problem["category"] == "rate_limit" and problem["source"] == "harness_event"
                            and problem["retryable"])
            if settings_policy["capacity_resumes"] and problem and (problem["category"] == "provider_overloaded" or rate_limited):
                kind = "capacity"
            elif (settings_policy["resume_session"] and settings_policy["network_resumes"] and problem
                    and exit_code is not None and exit_code > 0
                    and problem["category"] == "network_transient" and problem["source"] == "harness_event"
                    and problem["retryable"]):
                kind = "network"
            if kind:
                native_id = resume_after_failure(client, sid, row, output, attempt, settings_policy, problem, kind)
                if native_id:
                    env["ICLAYOUT_BENCH_RESUME_ID"] = native_id
                    continue
            break
    except (OSError, ValueError, ClientError, subprocess.SubprocessError) as exc:
        error = type(exc).__name__
        problem = classify(exc)
    finally:
        observers.close()
    # Persist before cleanup/transport calls, which can themselves fail.
    suspend = (error and settings_policy["resume_session"] and error != "harness_timeout"
               and not (problem and problem["category"] == "harness_configuration")
               and (not state.capacity_interruptions
                    or exit_code in {-signal.SIGINT, -signal.SIGTERM, 128 + signal.SIGINT, 128 + signal.SIGTERM}
                    or problem and problem["category"] in {"network_transient", "rate_limit"}))
    recovery = attempt.complete(error, suspended=bool(suspend))
    save(output / "failure.json", problem)
    save(output / "harness-summary.json", {"error": error, "failure": problem, "exit_code": exit_code,
         "elapsed_seconds": round(time.monotonic() - start, 3), "final_receipt": receipt, **recovery})
    if suspend:
        return {"session_id": sid, "state": "active",
                "evaluation_mode": evaluation_mode(client.result(sid))}, error
    return finalize_session(client, sid, output), error


def finalize_session(client, sid, output):
    summary_path = output / "harness-summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    try:
        try:
            receipt = settle_session(client, sid, output)
        except TimeoutError:
            # A drain timeout does not invalidate the accepted snapshot. Close
            # may already have succeeded in settle_session's finally block;
            # collect its independent verdict and retain the timeout journal.
            journal = output / "finalization.json"
            settlement = json.loads(journal.read_text()) if journal.exists() else {}
            if not settlement.get("closed"):
                raise
            receipt = settlement.get("receipt")
        summary.pop("finalization_error", None)
        summary["final_receipt"] = receipt
        save(summary_path, summary)
        return exports.collect_result(client, sid, output)
    except (OSError, ValueError, RuntimeError, ClientError, KeyboardInterrupt) as exc:
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
    return finalize_session(client, sid, output), error


def run_one(access, row, output, selection, *, collect_only=False):
    condition = selection.condition
    result, error = (recover_participant(access, row, output) if collect_only else
                     run_participant(access, row, output, selection))
    problem_path = output / "failure.json"
    problem = json.loads(problem_path.read_text()) if problem_path.exists() else None
    if result.get("state") == "error":
        problem = failure(result.get("failure_category") or "service_failure", "evaluation_service",
                          result.get("failure_reason"), scope=result.get('failure_scope'))
    elif problem is None and result.get("task_success") is False:
        problem = failure("task_failure", "independent_evaluator", result.get("outcome"))
    retain_recovery = (not collect_only and result.get('failure_reason') in {'checkpoint_timeout', 'checkpoint_failed'}
                       and result.get('submission') is None)
    summary = {"name": row["name"], **condition, "failure": problem,
            "state": "suspended" if result.get("state") == "active" or retain_recovery else "finished", "session_id": result["session_id"],
            "outcome": result.get("outcome"), "score": (result.get("score") or {}).get("value"),
            "task_success": result.get("task_success"), "evaluation_mode": evaluation_mode(result),
            "harness_error": error, **({"result": "analysis/result.json"} if result.get("state") != "active" else {})}
    launch = json.loads((output / "harness-summary.json").read_text()) if (output / "harness-summary.json").exists() else {}
    for key in ("capacity_recovery", "network_recovery"):
        if key in launch:
            summary[key] = launch[key]
    if problem and problem["category"] == "harness_configuration":
        summary["evaluation_result"] = {key: summary[key] for key in ("outcome", "score", "task_success")}
        summary.update(outcome="error", score=None, task_success=None)
    return summary
