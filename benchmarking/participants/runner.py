"""Run participant-owned CLI loops with independent Public observation."""
import hashlib
import json
import math
import os
import secrets
import selectors
import signal
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from benchmarking.analysis import export_session_result
from benchmarking.client import Client, ClientError
from benchmarking.files import atomic_write
from benchmarking.observe import export_observation

from .config import clean_env, digest, package_identity
from .process import execute
from .recovery import classify, credential_values, failure, harness_failure, policy
from .scheme import check as check_scheme
from .scheme import identity as scheme_identity
from .scheme import mcp_servers

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
"""
ROOT = Path(__file__).resolve().parent


def save(path, value):
    path = Path(path)
    atomic_write(path, (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def stop(process, signum=signal.SIGTERM):
    if process.poll() is None:
        os.killpg(process.pid, signum)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


@contextmanager
def service(prepared, output, image):
    """Local mode starts the installed service; remote mode needs no evaluator."""
    private = output / ".private"
    private.mkdir(mode=0o700, exist_ok=True)
    token_file = private / "access.json"
    token = json.loads(token_file.read_text())["token"] if token_file.exists() else secrets.token_urlsafe(32)
    if not token_file.exists():
        save(token_file, {"token": token})
    env = clean_env()
    env["ICLAYOUT_BENCH_LOCAL_TOKEN"] = token
    with (output / "service.log").open("a") as log:
        process = subprocess.Popen([
            sys.executable, "-I", "-m", "benchmarking.service", "--prepared", str(Path(prepared).resolve()),
            "--data", str(output / "service-store"), "--port", "0",
            "--image", image, "--token-env", "ICLAYOUT_BENCH_LOCAL_TOKEN",
        ], cwd=output, env=env, stdout=subprocess.PIPE, stderr=log, text=True, start_new_session=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=45):
                    raise TimeoutError("Local service did not start; see service.log")
            line = process.stdout.readline().strip()
            prefix = "Local development service: "
            if not line.startswith(prefix):
                raise RuntimeError("Local service failed; see service.log")
            yield Client(line.removeprefix(prefix), token, timeout=60)
        finally:
            stop(process, signal.SIGINT)
            process.stdout.close()


def command(condition, env, settings, mcp, directory):
    harness, model = condition["harness"], condition["model"]
    effort = condition["effort_resolved"]
    if harness == "command":
        return settings["launch"]["command"]
    if harness == "claude-code":
        args = ["claude", "-p", "--model", model, "--setting-sources", "", "--settings", json.dumps({k: v for k, v in settings.items() if k != "mcp_servers"}),
                "--strict-mcp-config", "--mcp-config", str(mcp), "--disable-slash-commands",
                "--tools", "", "--allowedTools", ",".join("mcp__" + name for name in ["layout", *settings.get("mcp_servers", {})]), "--permission-mode", "dontAsk",
                "--output-format", "stream-json", "--verbose"]
        # Omitting effort preserves the resolved user environment, not a common default.
        if condition["effort_requested"] is not None:
            args += ["--effort", effort]
        if env.get("ICLAYOUT_BENCH_RESUME_ID"):
            args += ["--resume", env["ICLAYOUT_BENCH_RESUME_ID"]]
        elif env.get("ICLAYOUT_BENCH_NATIVE_ID"):
            args += ["--session-id", env["ICLAYOUT_BENCH_NATIVE_ID"]]
        return args
    args = ["codex", "exec", "--ignore-user-config", "--ignore-rules",
            "--skip-git-repo-check", "--sandbox", "read-only", "--json", "-m", model]
    values = {"approval_policy": "never", "project_doc_max_bytes": 0, "web_search": "disabled",
              "mcp_servers.layout.default_tools_approval_mode": "approve",
              "mcp_servers.layout.command": sys.executable,
              "mcp_servers.layout.args": ["-I", str(ROOT / "bridge.py")],
              "mcp_servers.layout.env_vars": ["ICLAYOUT_BENCH_ENDPOINT", "ICLAYOUT_BENCH_TOKEN",
                                               "ICLAYOUT_BENCH_SESSION", "ICLAYOUT_BENCH_PARTICIPANT_TOOL_LOG",
                                               "ICLAYOUT_BENCH_COMMAND_SECONDS", "ICLAYOUT_BENCH_RECOVERY"],
              "mcp_servers.layout.tool_timeout_sec": int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]),
              "features.skip_host_skill_discovery": True,
              "suppress_unstable_features_warning": True}
    for name, spec in settings.get("mcp_servers", {}).items():
        values.update({f"mcp_servers.{name}.command": spec["command"],
                       f"mcp_servers.{name}.args": spec["args"],
                       f"mcp_servers.{name}.env_vars": list(spec["env"]),
                       f"mcp_servers.{name}.default_tools_approval_mode": "approve",
                       f"mcp_servers.{name}.tool_timeout_sec": int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"])})
    if effort:
        values["model_reasoning_effort"] = effort
    for feature in ("plugins", "apps", "hooks", "multi_agent", "multi_agent_v2", "shell_tool",
                    "unified_exec", "image_generation", "skill_search"):
        values["features." + feature] = False
    for key, value in values.items():
        args += ["-c", key + "=" + json.dumps(value)]
    if env.get("ICLAYOUT_BENCH_RESUME_ID"):
        args += ["resume", env["ICLAYOUT_BENCH_RESUME_ID"]]
    return args + ["-"]


def run_participant(access, row, output, condition, env, settings):
    scheme = row.get("scheme", {})
    check_scheme(scheme)
    instructions = PROMPT + ("\nPARTICIPANT TOOL INSTRUCTIONS:\n" + scheme["instructions"] if scheme.get("instructions") else "")
    output.mkdir(mode=0o700, exist_ok=True)
    private = output / ".private"
    private.mkdir(mode=0o700, exist_ok=True)
    state_path = private / "recovery.json"
    settings_policy = policy(row.get("recovery"))
    if hasattr(access, "retry_policy"):
        access.retry_policy = settings_policy
    frozen = {"selection": condition, "task": row["task"], "package": package_identity(), "prompt": instructions, "scheme": scheme_identity(scheme),
              "recovery": settings_policy,
              "native_store_sha256": digest({"cwd": str(private.resolve()),
                  "home": env.get("CODEX_HOME", str(Path.home() / ".codex")) if row["harness"] == "codex"
                  else env.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))}),
              "adapter_sha256": digest({p.name: p.read_text() for p in ROOT.glob("*.py")})}
    if row["harness"] == "command":
        frozen["cli_version"] = scheme["version"]
    else:
        executable = {"claude-code": "claude", "codex": "codex", "dsh": "dsh"}[row["harness"]]
        frozen["cli_version"] = subprocess.check_output([executable, "--version"], text=True, timeout=20).strip()
    resuming = state_path.exists()
    if resuming:
        state = json.loads(state_path.read_text())
        if json.loads((output / "conditions.json").read_text()) != frozen:
            raise ValueError("Cannot resume changed participant conditions or CLI")
    else:
        save(output / "conditions.json", frozen)
        state = {"create_key": "trial-" + uuid.uuid4().hex, "native_id": str(uuid.uuid4()), "launches": 0,
                 "access_identity": digest(getattr(access, "token", None))}
        save(state_path, state)
    identity = {"harness_kind": "agent", "harness_id": "iclayout-" + row["harness"], "harness_version": "1",
                "model": condition["model"], "prompt_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
                "configuration_sha256": digest({k: v for k, v in frozen.items() if k not in {"task", "native_store_sha256"}})}
    if "created" not in state:
        if state["access_identity"] != digest(getattr(access, "token", None)):
            raise ValueError("Uncertain creation cannot change access identity")
        state["created"] = access.create(row["task"], identity, key=state["create_key"])
        save(state_path, state)
    created = state["created"]
    declared_values = {os.environ[name] for spec in [*scheme.get("mcp", {}).values(),
                       *([scheme["launch"]] if "launch" in scheme else [])]
                       for name in spec["env_vars"] if len(os.environ[name]) >= 4}
    state["redactions"] = sorted(set(state.get("redactions", [])) | declared_values | credential_values(env)
                                 | credential_values(settings) | {created["session_token"]})
    save(state_path, state)
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
        if state.get("phase") == "running" or state["launches"] == 0:
            state["error"] = "runner_interrupted" if state["launches"] else "not_launched"
            save(state_path, state)
            save(output / "failure.json", failure("unknown", "runner", state["error"]))
        return collect_result(client, sid, output), state.get("error")
    if status["remaining_seconds"] <= 0:
        client.close(sid, key="runner-close")
        return collect_result(client, sid, output), "harness_timeout"
    if state.get("phase") == "finalizing":
        return finalize_session(client, sid, created, output), state.get("error")
    if state["launches"]:
        if not settings_policy["resume_session"]:
            raise ValueError("Session continuation was not enabled in frozen TOML")
        if row["harness"] in {"dsh", "command"}:
            raise ValueError("This harness does not support same-session continuation")
        if ((output / "tools.pending.json").exists() or (output / "tools.delivery.json").exists()
                or status.get("active_execution_id")):
            raise ValueError("Unresolved tool operation; reconcile evidence before native continuation")
        native_id = state["native_id"] if row["harness"] == "claude-code" else codex_session_id(output)
        if not native_id:
            raise ValueError("No persisted native session ID; refusing a new session")
        env["ICLAYOUT_BENCH_RESUME_ID"] = native_id
    # Native histories belong to the attempt, alongside (but outside) shareable exports.
    # Refresh only credentials at launch; never copy user hooks, rules or session history.
    if row["harness"] in {"codex", "claude-code"}:
        variable, fallback, filename = (("CODEX_HOME", ".codex", "auth.json") if row["harness"] == "codex"
                                        else ("CLAUDE_CONFIG_DIR", ".claude", ".credentials.json"))
        original_home = Path(env.get(variable, str(Path.home() / fallback)))
        native_home = private / "native-home"
        native_home.mkdir(mode=0o700, exist_ok=True)
        credential = original_home / filename
        if credential.is_file():
            raw_credentials = credential.read_bytes()
            atomic_write(native_home / filename, raw_credentials)
            try:
                state["redactions"] = sorted(set(state["redactions"]) | credential_values(json.loads(raw_credentials)))
                save(state_path, state)
            except ValueError:
                pass  # The native CLI owns validation of its credential file.
        env[variable] = str(native_home.resolve())
    env["ICLAYOUT_BENCH_NATIVE_ID"] = state["native_id"]
    env["ICLAYOUT_BENCH_RECOVERY"] = json.dumps(settings_policy)
    # Only a scoped session credential reaches the native CLI/bridge subprocess.
    env.update(ICLAYOUT_BENCH_ENDPOINT=access.endpoint, ICLAYOUT_BENCH_TOKEN=created["session_token"],
               ICLAYOUT_BENCH_SESSION=sid, ICLAYOUT_BENCH_PARTICIPANT_TOOL_LOG=str(output / "tools.jsonl"),
               ICLAYOUT_BENCH_COMMAND_SECONDS=str(created["limits"]["max_command_seconds"]),
               ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS=str(math.ceil(created["limits"]["wall_seconds"]) + 60))
    env["ICLAYOUT_BENCH_TASK_FILE"] = str((output / "session.json").resolve())
    env["ICLAYOUT_BENCH_MODEL"] = condition["model"]
    env["ICLAYOUT_BENCH_EFFORT"] = condition.get("effort_resolved") or ""
    env["MCP_TOOL_TIMEOUT"] = str(int(env["ICLAYOUT_BENCH_TOOL_TIMEOUT_SECONDS"]) * 1000)
    error, exit_code, receipt, problem = None, None, None, None
    start = time.monotonic()
    try:
        directory = private / "workspace"
        directory.mkdir(mode=0o700, exist_ok=True)
        mcp = directory / "mcp.json"
        # Explicit bridge env is needed because some CLI versions filter inherited env.
        extra_servers = mcp_servers(scheme, {k: v for k, v in env.items() if k.startswith("ICLAYOUT_BENCH_")})
        settings = dict(settings, mcp_servers=extra_servers)
        if "launch" in scheme:
            settings["launch"] = scheme["launch"]
        save(mcp, {"mcpServers": {**extra_servers, "layout": {"command": sys.executable,
             "args": ["-I", str(ROOT / "bridge.py")],
             "env": {k: v for k, v in env.items() if k.startswith("ICLAYOUT_BENCH_")}}}})
        env["ICLAYOUT_BENCH_MCP_CONFIG"] = str(mcp.resolve())
        prompt = instructions + "\nTASK CONTRACT:\n" + json.dumps(created["task"]) + "\nBudget seconds: " + str(created["limits"]["wall_seconds"])
        if row["harness"] == "dsh":
            from .dsh import prepare
            args = prepare(condition, settings, env, directory, output, ROOT / "bridge.py", prompt)
        else:
            args = command(condition, env, settings, mcp, directory)
        if state["launches"]:
            prompt = "Continue the same task and service session. The original deadline still applies. Check status first."
            for filename in ("harness.jsonl", "harness.stderr", "harness-summary.json"):
                source = output / filename
                if source.exists():
                    source.rename(output / f"launch-{state['launches']}-{filename}")
        state["launches"] += 1
        state.update(phase="running", error=None)
        save(state_path, state)
        remaining = client.session(sid)["remaining_seconds"]
        timeout = max(.001, remaining)
        with (output / "harness.jsonl").open("w") as out, (output / "harness.stderr").open("w") as err:
            exit_code, timed_out = execute(args, cwd=directory, env=env, stdout=out, stderr=err,
                                            prompt=prompt, timeout=timeout,
                                            pass_fds=tuple(int(env[k]) for k in ["ICLAYOUT_BENCH_LEASE_FD"] if k in env))
            if timed_out:
                error = "harness_timeout"
            elif exit_code:
                error = "cli_exit_" + str(exit_code)
        check_scheme(scheme)
        problem = harness_failure(output, exit_code, error == "harness_timeout")
        if problem and error is None:
            error = problem["category"]
    except (OSError, ValueError, ClientError, subprocess.SubprocessError) as exc:
        error = type(exc).__name__
        problem = classify(exc)
    # Persist before cleanup/transport calls, which can themselves fail.
    state["error"] = error
    state["phase"] = "suspended" if error and settings_policy["resume_session"] and error != "harness_timeout" else "finalizing"
    save(state_path, state)
    save(output / "failure.json", problem)
    save(output / "harness-summary.json", {"error": error, "failure": problem, "exit_code": exit_code,
         "elapsed_seconds": round(time.monotonic() - start, 3), "final_receipt": receipt})
    if error and settings_policy["resume_session"] and error != "harness_timeout":
        return {"session_id": sid, "state": "active"}, error
    return finalize_session(client, sid, created, output), error


def finalize_session(client, sid, created, output):
    receipt = None
    # Preserve a generated candidate even when the CLI times out or forgets submit.
    if client.session(sid)["state"] == "active":
        path = created["task"]["description"]["output"]["path"].removeprefix("/workspace/")
        try:
            receipt = client.submit(sid, path, key="runner-final-submit")
        except ClientError as exc:
            if exc.status != 400:
                raise
    client.close(sid, key="runner-close")
    summary_path = output / "harness-summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    save(output / "harness-summary.json", dict(summary, final_receipt=receipt))
    return collect_result(client, sid, output)


def codex_session_id(output):
    for path in sorted(output.glob("*harness.jsonl")):
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "thread.started":
                return event.get("thread_id")
    return None


def collect_result(client, sid, output):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        result = client.result(sid)
        if result["state"] in {"complete", "error"}:
            if not (output / "analysis" / "manifest.json").exists():
                if (output / "analysis").exists():
                    (output / "analysis").rename(output / ("partial-analysis-" + uuid.uuid4().hex))
                export_session_result(result, output / "analysis")
            elif json.loads((output / "analysis" / "result.json").read_text()) != result:
                raise ValueError("Terminal service result changed during recovery")
            traces = [p for p in output.iterdir() if p.is_file() and p.name != 'session.json']
            traces.extend((output / 'dsh-sessions').rglob('*.jsonl'))
            if not (output / "observation" / "manifest.json").exists():
                if (output / "observation").exists():
                    (output / "observation").rename(output / ("partial-observation-" + uuid.uuid4().hex))
                private = output / ".private"
                state = json.loads((private / "recovery.json").read_text())
                export_traces = private / "export-traces"
                export_traces.mkdir(mode=0o700, exist_ok=True)
                redacted = []
                for source in traces:
                    content = source.read_bytes()
                    for secret in sorted(state.get("redactions", []), key=len, reverse=True):
                        content = content.replace(secret.encode(), b"<REDACTED>")
                    destination = export_traces / source.name
                    atomic_write(destination, content)
                    redacted.append(destination)
                export_observation(client, sid, output / 'observation', participant_files=redacted)
            break
        time.sleep(.5)
    else:
        raise TimeoutError("Evaluation remains pending; session ID retained in session.json")
    return result


def run_one(access, row, output, selection):
    condition, env, settings = selection
    env = env.copy()
    result, error = run_participant(access, row, output, condition, env, settings)
    problem_path = output / "failure.json"
    problem = json.loads(problem_path.read_text()) if problem_path.exists() else None
    if result.get("state") == "error":
        problem = failure(result.get("failure_category") or "service_failure", "evaluation_service", result.get("failure_reason"))
    elif problem is None and result.get("task_success") is False:
        problem = failure("task_failure", "independent_evaluator", result.get("outcome"))
    summary = {"name": row["name"], **condition, "failure": problem,
            "state": "suspended" if result.get("state") == "active" else "finished", "session_id": result["session_id"],
            "outcome": result.get("outcome"), "score": (result.get("score") or {}).get("value"),
            "task_success": result.get("task_success"), "verification_level": result.get("verification_level"),
            "harness_error": error, **({"result": "analysis/result.json"} if result.get("state") != "active" else {})}
    if problem and problem["category"] == "harness_configuration":
        summary["evaluation_result"] = {key: summary[key] for key in ("outcome", "score", "task_success")}
        summary.update(outcome="error", score=None, task_success=None)
    return summary
