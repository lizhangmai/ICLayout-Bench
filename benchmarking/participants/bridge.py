"""Small stdio MCP adapter for a single scoped Public HTTP session.

The native harness owns its conversation and tool loop. All layout operations
run through the installed client against the remote EDA workspace.
"""
import base64
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path

from benchmarking.client import Client, ClientError
from benchmarking.files import atomic_write


def tool(name, description, properties, required=()):
    return {"name": name, "description": description, "inputSchema": {
        "type": "object", "properties": properties, "required": list(required),
        "additionalProperties": False,
    }}


STRING = {"type": "string"}
TOOLS = [
    tool("status", "Get task contract, session state and remaining seconds.", {}),
    tool("read", "Read a UTF-8 file at a relative workspace path. Use execute with cat for /task and /resources.", {"path": STRING}, ["path"]),
    tool("write", "Write model-authored UTF-8 content to a relative workspace path.",
         {"path": STRING, "content": STRING}, ["path", "content"]),
    tool("execute", "Run a command in the remote EDA workspace and return its output. No host execution. Omit seconds to use the remaining service command allowance.",
         {"command": STRING, "seconds": {"type": "number", "exclusiveMinimum": 0}}, ["command"]),
    tool("submit", "Snapshot the declared GDS candidate for independent judging. Acceptance is not success.",
         {"path": STRING}, ["path"]),
]


class Bridge:
    def __init__(self, client, session, log, command_seconds=None):
        self.client, self.session = client, session
        self.log, self.command_seconds = Path(log), command_seconds
        self.pending = self.log.with_suffix(".pending.json")
        self.delivery = self.log.with_suffix(".delivery.json")
        self.delivery_unknown = self.delivery.exists()

    def record(self, value):
        with self.log.open("a") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def call(self, name, args):
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if spec is None or not isinstance(args, dict):
            raise ValueError("Unknown tool or invalid arguments")
        schema = spec["inputSchema"]
        if set(args) - set(schema["properties"]) or set(schema["required"]) - set(args):
            raise ValueError("Invalid tool arguments")
        for key, value in args.items():
            if key != "seconds" and not isinstance(value, str):
                raise ValueError("Expected string argument")
        mutation = name in {"write", "execute", "submit"}
        if mutation and self.delivery_unknown:
            raise ClientError("operation_unresolved", "Previous bridge reply delivery is unknown; refusing a new mutation")
        if not self.delivery_unknown:
            # A subsequent request in this connection acknowledges the previous reply.
            self.delivery.unlink(missing_ok=True)
        key = "native-" + uuid.uuid4().hex
        pending = None
        if mutation and self.pending.exists():
            pending = json.loads(self.pending.read_text())
            if pending["tool"] != name or pending["arguments"] != args:
                raise ClientError("operation_unresolved", "Replay the unresolved tool with identical arguments before another mutation")
            key = pending["key"]
        if mutation and pending is None:
            pending = {"tool": name, "arguments": args, "key": key}
            if name == "execute":
                remaining = self.client.session(self.session)["remaining_seconds"]
                seconds = args.get("seconds", min(remaining, self.command_seconds or remaining))
                if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
                    raise ValueError("Command seconds must be positive and finite")
                pending["seconds"] = min(seconds, remaining, self.command_seconds or remaining)
            atomic_write(self.pending, json.dumps(pending).encode())
        self.record({"tool": name, "arguments": args, "mutation": mutation, "key": key})
        client, sid = self.client, self.session
        if name == "status":
            result = client.session(sid)
        elif name == "read":
            raw = client.read(sid, args["path"])
            result = {"content": raw[:48000].decode(errors="replace"), "truncated": len(raw) > 48000}
        elif name == "write":
            result = client.write(sid, args["path"], args["content"].encode(), key=key)
        elif name == "submit":
            result = client.submit(sid, args["path"], key=key)
        else:
            seconds = pending["seconds"]
            started = client.execute(sid, args["command"], seconds, key=key)
            offset, chunks, count = 0, [], 0
            deadline = time.monotonic() + seconds + 60
            while True:
                polled = client.poll(sid, started["execution_id"], offset=offset)
                raw = base64.b64decode(polled["log_base64"], validate=True)
                chunks.append(raw[:max(0, 48000 - count)])
                count += len(raw)
                offset = polled["next_offset"]
                if polled["state"] != "running" and not raw:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Execution polling timed out; inspect session status")
                time.sleep(.1)
            result = {"output": b"".join(chunks).decode(errors="replace"),
                      "state": polled["state"], "exit_code": polled["exit_code"],
                      "truncated": polled["truncated"] or count > 48000}
        self.record({"tool": name, "key": key, "result": result})
        if mutation:
            atomic_write(self.delivery, json.dumps({"key": key, "tool": name, "result": result}).encode())
            self.pending.unlink()
        return result


def dispatch(bridge, message):
    if "id" not in message:
        return None
    method, params = message.get("method"), message.get("params", {})
    response = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "iclayout-layout", "version": "1"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            value = bridge.call(params["name"], params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
        except (ClientError, ValueError, KeyError, OSError) as error:
            # Never expose HTTP headers, process environments or exception chains.
            detail = error.code if isinstance(error, ClientError) else type(error).__name__
            if isinstance(error, ClientError) and error.status in {400, 401, 404, 413, 429}:
                # Explicit rejection has no unknown side effect; a corrected call may proceed.
                bridge.pending.unlink(missing_ok=True)
            bridge.record({"error": detail})
            result = {"isError": True, "content": [{"type": "text", "text": detail}]}
    else:
        response["error"] = {"code": -32601, "message": "Method not found"}
        return response
    response["result"] = result
    return response


def main():
    bridge = Bridge(Client(os.environ["ICLAYOUT_BENCH_ENDPOINT"], os.environ["ICLAYOUT_BENCH_TOKEN"], timeout=60,
                           retry_policy=json.loads(os.environ.get("ICLAYOUT_BENCH_RECOVERY", "null"))),
                    os.environ["ICLAYOUT_BENCH_SESSION"], os.environ["ICLAYOUT_BENCH_PARTICIPANT_TOOL_LOG"],
                    float(os.environ["ICLAYOUT_BENCH_COMMAND_SECONDS"])
                    if "ICLAYOUT_BENCH_COMMAND_SECONDS" in os.environ else None)
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = dispatch(bridge, message)
        except (ValueError, TypeError, KeyError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid request"}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
