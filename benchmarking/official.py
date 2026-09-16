"""Official observe/action harness over the public client.

Provider adapters return one action; they never receive service credentials or
execute EDA. The harness owns history, budgets, retries and timely submissions.
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .analysis import export_session_result
from .client import Client, ClientError
from .files import atomic_write
from .protocol import USAGE_FIELDS, json_bytes

VERSION = "1"
PROMPT = """Design the declared integrated circuit layout from its authoritative inputs.
Return exactly one JSON action. You may execute shell commands in the remote EDA
workspace, write your own generator there, submit the declared output, or finish.
Read /task/problem.md and the declared netlist first. Reviewed PDK resources are
under /resources. The working directory is /workspace. Use installed EDA tools.
Construct real devices, interconnect and named pins. Never copy a reference,
create a placeholder, or claim success from an empty layout. Submit a real first
candidate early and refine it within the budget. The harness snapshots the
output after each successful command when it exists. Commands run in foreground;
leftover processes are terminated. Only the service executes your action: do not
use host tools, files, network, skills or other agents. A receipt means delivery;
independent evaluation determines success after the session closes.
Actions: exec (command and seconds), write (path and content), submit, finish.
Use null for unused fields. Finish after your best candidate is submitted."""
ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "command", "seconds", "path", "content"],
    "properties": {
        "action": {"type": "string", "enum": ["exec", "write", "submit", "finish"]},
        "command": {"type": ["string", "null"]},
        "seconds": {"type": ["number", "null"]},
        "path": {"type": ["string", "null"]},
        "content": {"type": ["string", "null"]},
    },
}


@dataclass(frozen=True)
class Config:
    model: str
    effort: str = "medium"
    max_steps: int = 32
    max_context_chars: int = 80000
    max_observation_chars: int = 16000
    reserve_seconds: int = 45
    provider_seconds: int = 240
    codex: str = "codex"

    def __post_init__(self):
        if not self.model or self.effort not in {
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("Invalid model or effort")
        if any(
            type(v) is not int or v <= 0
            for v in (
                self.max_steps,
                self.max_context_chars,
                self.max_observation_chars,
                self.reserve_seconds,
                self.provider_seconds,
            )
        ):
            raise ValueError("Budgets must be positive integers")


def implementation():
    return {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("official.py", "client.py", "protocol.py")
    }


class CodexProvider:
    """Codex as a structured model transport, without its tool/solver loop."""

    def __init__(self, config):
        self.config = config
        self.version = subprocess.check_output(
            [config.codex, "--version"], text=True, timeout=20
        ).strip()

    def __call__(self, prompt, timeout):
        config = self.config
        with tempfile.TemporaryDirectory(prefix="layout-model-") as temporary:
            root = Path(temporary)
            schema = root / "action.schema.json"
            schema.write_bytes(json_bytes(ACTION_SCHEMA))
            command = [
                config.codex,
                "exec",
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--json",
                "--output-schema",
                str(schema),
                "-m",
                config.model,
                "-c",
                'approval_policy="never"',
                "-c",
                "project_doc_max_bytes=0",
                "-c",
                'web_search="disabled"',
                "-c",
                "model_reasoning_effort=" + json.dumps(config.effort),
            ]
            for feature in (
                "plugins",
                "apps",
                "hooks",
                "multi_agent",
                "multi_agent_v2",
                "shell_tool",
                "unified_exec",
                "image_generation",
                "skill_search",
            ):
                command += ["-c", f"features.{feature}=false"]
            command += [
                "-c",
                "features.skip_host_skill_discovery=true",
                "-c",
                "suppress_unstable_features_warning=true",
                "-",
            ]
            env = {
                k: v for k, v in os.environ.items() if not k.startswith(("ICLAYOUT_BENCH_", "LAYOUT_BENCH_"))
            }
            result = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                cwd=root,
                env=env,
                timeout=timeout,
                check=False,
            )
            events = [
                json.loads(line) for line in result.stdout.splitlines() if line.strip()
            ]
            for event in events:
                item = event.get("item", {})
                if item and item.get("type") not in {"agent_message", "reasoning"}:
                    raise ValueError(
                        "Provider emitted a non-model item: " + str(item.get("type"))
                    )
            messages = [
                e["item"]["text"]
                for e in events
                if e.get("type") == "item.completed"
                and e.get("item", {}).get("type") == "agent_message"
            ]
            if result.returncode or not messages:
                raise RuntimeError("Model transport failed; no action accepted")
            action = json.loads(messages[-1])
            usage = [e["usage"] for e in events if e.get("type") == "turn.completed"]
            return action, {
                "events": events,
                "usage": usage,
                "transport_version": self.version,
            }


def mutation(operation):
    """Retry uncertain delivery with the caller's unchanged key/body only."""
    for attempt in range(3):
        try:
            return operation()
        except ClientError as error:
            if not error.retryable or attempt == 2:
                raise
            time.sleep(0.2 * (attempt + 1))


def run(
    access, task_id, config, destination, *, provider=None, creation_key="official-run"
):
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    provider = provider or CodexProvider(config)
    frozen = {
        "config": asdict(config),
        "implementation": implementation(),
        "provider_version": provider.version,
        "prompt": PROMPT,
        "action_schema": ACTION_SCHEMA,
    }
    condition = {
        "harness_kind": "official",
        "harness_id": "iclayout-bench",
        "harness_version": VERSION,
        "model": config.model,
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "configuration_sha256": hashlib.sha256(json_bytes(frozen)).hexdigest(),
    }
    atomic_write(output / "conditions.json", json_bytes(frozen))
    created = mutation(lambda: access.create(task_id, condition, key=creation_key))
    sid = created["session_id"]
    client = Client(access.endpoint, created["session_token"], timeout=access.timeout)
    atomic_write(
        output / "session.json",
        json_bytes({k: v for k, v in created.items() if k != "session_token"}),
    )
    history, receipts, failure = [], [], None
    transcript = output / "interactions.jsonl"
    transcript.touch(mode=0o600)
    usage = dict.fromkeys(USAGE_FIELDS)

    def record(event):
        with transcript.open("ab") as stream:
            stream.write(json_bytes(event) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def submit(key, optional=False):
        try:
            receipt = mutation(
                lambda: client.submit(
                    sid,
                    created["task"]["description"]["output"]["path"].removeprefix(
                        "/workspace/"
                    ),
                    key=key,
                )
            )
            receipts.append(receipt)
            return receipt
        except ClientError as error:
            if optional and error.status == 400:
                return {"candidate": "not_yet_available"}
            raise

    try:
        for step in range(config.max_steps):
            status = client.session(sid)
            if (
                status["state"] != "active"
                or status["remaining_seconds"] <= config.reserve_seconds
            ):
                break
            context = json.dumps(history, ensure_ascii=False)
            while len(context) > config.max_context_chars and len(history) > 1:
                history.pop(0)
                context = json.dumps(history, ensure_ascii=False)
            prompt = (
                PROMPT
                + "\nTASK:\n"
                + json.dumps(created["task"])
                + "\nSTATUS:\n"
                + json.dumps(status)
                + "\nHISTORY:\n"
                + context
            )
            action, evidence = provider(
                prompt,
                min(
                    config.provider_seconds,
                    status["remaining_seconds"] - config.reserve_seconds,
                ),
            )
            record(
                {
                    "step": step,
                    "prompt": prompt,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "action": action,
                    "provider": evidence,
                }
            )
            if not isinstance(action, dict) or set(action) != set(
                ACTION_SCHEMA["required"]
            ):
                raise ValueError("Invalid action fields")
            name = action["action"]
            key = f"step-{step}"
            if name == "finish":
                break
            if name == "exec":
                started = mutation(
                    lambda action=action, key=key: client.execute(
                        sid, action["command"], action["seconds"], key=key
                    )
                )
                offset, chunks, characters = 0, [], 0
                while True:
                    polled = client.poll(sid, started["execution_id"], offset=offset)
                    raw = base64.b64decode(polled["log_base64"], validate=True)
                    text = raw.decode(errors="replace")
                    chunks.append(
                        text[: max(0, config.max_observation_chars - characters)]
                    )
                    characters += len(text)
                    offset = polled["next_offset"]
                    if polled["state"] != "running" and not raw:
                        break
                    time.sleep(0.1)
                observation = {
                    "execution": {
                        k: polled[k] for k in ("state", "exit_code", "truncated")
                    },
                    "output": "".join(chunks),
                    "context_truncated": characters > config.max_observation_chars,
                }
                if polled["state"] == "complete" and polled["exit_code"] == 0:
                    observation["submission"] = submit(key + "-auto", optional=True)
            elif name == "write":
                observation = mutation(
                    lambda action=action, key=key: client.write(
                        sid, action["path"], action["content"].encode(), key=key
                    )
                )
            elif name == "submit":
                observation = submit(key)
            else:
                raise ValueError("Unknown action")
            record({"step": step, "observation": observation})
            history.append({"action": action, "observation": observation})
        if client.session(sid)["state"] == "active":
            submit("final-candidate", optional=True)
    except (
        ClientError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        failure = type(error).__name__
        record({"harness_error": failure})
    finally:
        if client.session(sid)["state"] == "active":
            mutation(lambda: client.close(sid, key="official-close"))
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        result = client.result(sid)
        if result["state"] in {"complete", "error"}:
            break
        time.sleep(0.2)
    export_session_result(result, output / "analysis")
    atomic_write(
        output / "harness.json",
        json_bytes(
            {
                "condition": condition,
                "session_id": sid,
                "receipts": receipts,
                "error": failure,
                "usage": usage,
                "usage_provenance": "unknown",
                "interactions_sha256": hashlib.sha256(
                    transcript.read_bytes()
                ).hexdigest(),
            }
        ),
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("ICLAYOUT_BENCH_ENDPOINT"))
    parser.add_argument("--token-env", default="ICLAYOUT_BENCH_TOKEN")
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    result = run(
        Client(args.endpoint, os.environ[args.token_env], timeout=60),
        args.task,
        Config(args.model, effort=args.effort, max_steps=args.steps),
        args.output,
        creation_key=args.key,
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("session_id", "outcome", "score", "verification_level")
            }
        )
    )


if __name__ == "__main__":
    main()
