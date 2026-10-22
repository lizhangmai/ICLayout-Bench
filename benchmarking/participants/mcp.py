"""Small stdio MCP adapter for a single scoped HTTP evaluation session.

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


def tool(name, description, properties, required=()):
    return {"name": name, "description": description, "inputSchema": {
        "type": "object", "properties": properties, "required": list(required),
        "additionalProperties": False,
    }}


STRING = {"type": "string"}
WAIT = {"type": "number", "minimum": 0, "maximum": 30}
TOOLS = [
    tool("status", "Get session state, declared capabilities, budget policy and remaining seconds.", {}),
    tool("read", "Read a UTF-8 file at a relative workspace path. Unavailable while an execution is running; use poll or cancel first. Use execute with cat for /task and /resources.", {"path": STRING}, ["path"]),
    tool("write", "Write model-authored UTF-8 content to a relative workspace path.",
         {"path": STRING, "content": STRING}, ["path", "content"]),
    tool("execute", "Run a command in the remote EDA workspace. Returns after wait_seconds (default 10), possibly still running; use poll with execution_id/next_offset for more output, or cancel a failed or stuck command. Only one execution can run at a time; poll or cancel it before another execute, read, write, check or submit. No host execution. In a soft session, an already-started command may finish after the budget; omit seconds for no per-call timeout. At zero remaining time, submit immediately without another optimization round.",
         {"command": STRING, "seconds": {"type": "number", "exclusiveMinimum": 0}, "wait_seconds": WAIT}, ["command"]),
    tool("poll", "Read output and state of an existing execution; does not start work. Use next_offset from the previous reply. Available after budget expiry.",
         {"execution_id": STRING, "offset": {"type": "integer", "minimum": 0}, "wait_seconds": WAIT}, ["execution_id"]),
    tool("cancel", "Cancel an existing failed or stuck execution. Retains workspace files and accepted submissions. Available after budget expiry; poll until it stops before submitting.",
         {"execution_id": STRING}, ["execution_id"]),
    tool("submit", "Snapshot the declared GDS candidate for independent judging. Use the task's output.path with its /workspace/ prefix removed: /workspace/output/final.gds becomes output/final.gds. Acceptance is not success.",
         {"path": STRING}, ["path"]),
    tool("report", "Read diagnostic JSON for a check report_id. Concatenate content pages using next_offset while has_more is true. Report access is scoped to this session.",
         {"report_id": STRING, "offset": {"type": "integer", "minimum": 0}}, ["report_id"]),
    tool("check", "Check the current declared GDS output with the final evaluator's full plan. Returns physical/electrical diagnostics and candidate measurements, without scores or normalized quality factors; does not submit. May return running after wait_seconds (default 10); use poll. Consumes solve time; a started soft-budget check may finish after expiry. Do not request a new check at zero remaining time; submit immediately. Requires process-feedback capability.", {"wait_seconds": WAIT}),
]


def _record(log, value):
    with log.open('a') as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


class Bridge:
    def __init__(self, client, session, log, command_seconds=None, *, instructions=''):
        self.client, self.session = client, session
        self.log, self.command_seconds = Path(log), command_seconds
        self.instructions = instructions

    def record(self, value):
        _record(self.log, value)

    def call(self, name, args):
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if spec is None or not isinstance(args, dict):
            raise ValueError("Unknown tool or invalid arguments")
        schema = spec["inputSchema"]
        if set(args) - set(schema["properties"]) or set(schema["required"]) - set(args):
            raise ValueError("Invalid tool arguments")
        for key, value in args.items():
            if key not in {"seconds", "offset", "wait_seconds"} and not isinstance(value, str):
                raise ValueError("Expected string argument")
        wait = args.get('wait_seconds', 10)
        if type(wait) not in (int, float) or not math.isfinite(wait) or not 0 <= wait <= 30:
            raise ValueError('wait_seconds must be finite and between 0 and 30')
        mutation = name in {"write", "execute", "submit", "check", "cancel"}
        # Each Agent invocation is a new operation. The HTTP client alone retries
        # uncertain transport with this same key; restarting the bridge replays nothing.
        key = "native-" + uuid.uuid4().hex
        seconds = None
        if name in {"execute", "check"}:
            status = self.client.session(self.session)
            if name == "check" and "process-feedback" not in status.get("capabilities", []):
                raise ValueError("Service does not advertise process-feedback")
            remaining = status["remaining_seconds"]
            soft = status.get('budget', {}).get('policy') == 'soft'
            if soft and remaining <= 0:
                raise ClientError('budget_exhausted', 'Submit immediately without another optimization round')
            seconds = args.get("seconds", None if soft else min(remaining, self.command_seconds or remaining))
            if seconds is not None and (type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0):
                raise ValueError("Command seconds must be positive and finite")
            if not soft:
                seconds = min(seconds, remaining, self.command_seconds or remaining)
        request = {"tool": name, "arguments": args, "mutation": mutation, "key": key}
        if name in {"execute", "check"}:
            request["seconds"] = seconds
        self.record(request)
        client, sid = self.client, self.session
        if name == "status":
            result = client.session(sid)
        elif name == "report":
            result = client.report(sid, args["report_id"], offset=args.get("offset", 0))
        elif name == "read":
            raw = client.read(sid, args["path"])
            result = {"content": raw[:48000].decode(errors="replace"), "truncated": len(raw) > 48000}
        elif name == "poll":
            result = self.poll(args['execution_id'], args.get('offset', 0), wait)
        elif name == "write":
            result = client.write(sid, args["path"], args["content"].encode(), key=key)
        elif name == "submit":
            result = client.submit(sid, args["path"], key=key)
        elif name == "cancel":
            result = client.cancel(sid, args['execution_id'], key=key)
        else:
            result = (client.check(sid, seconds, key=key) if name == "check" else
                      client.execute(sid, args["command"], seconds, key=key))
            result = self.poll(result['execution_id'], 0, wait,
                               limit=128 * 1024 if name == 'check' else 48000)
        budget = client.session(sid).get('budget')
        if budget is not None:
            result['budget'] = budget
        self.record({"tool": name, "key": key, "result": result})
        return result

    def poll(self, execution_id, offset, wait, *, limit=128 * 1024):
        deadline = time.monotonic() + wait
        chunks, count = [], 0
        while True:
            polled = self.client.poll(self.session, execution_id, offset=offset)
            raw = base64.b64decode(polled['log_base64'], validate=True)
            chunks.append(raw[:max(0, limit - count)])
            count += len(raw)
            offset = polled['next_offset']
            if (polled['state'] != 'running' and not raw) or time.monotonic() >= deadline or count >= limit:
                break
            time.sleep(.1)
        return {'execution_id': execution_id, 'next_offset': offset,
                'output': b''.join(chunks).decode(errors='replace'),
                'state': polled['state'], 'exit_code': polled['exit_code'],
                'truncated': polled['truncated'] or count > limit,
                'has_more': polled['state'] == 'running' or bool(raw)}


def dispatch(bridge, message):
    if "id" not in message:
        return None
    method, params = message.get("method"), message.get("params", {})
    response = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "iclayout-layout", "version": "1"}}
        if bridge.instructions:
            result['instructions'] = bridge.instructions
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
            if isinstance(error, ValueError) and str(error) == 'wait_seconds must be finite and between 0 and 30':
                detail += ': wait_seconds must be finite and between 0 and 30; use repeated poll calls for longer waits'
            if detail == 'invalid_submission_path':
                # This service error contains only the declared public output path.
                detail += ': ' + str(error)
            if detail == 'budget_exhausted':
                detail += ': finish the current operation and submit immediately; do not start another optimization round'
            if detail == 'conflict':
                detail += ': use status to check active_execution_id; poll or cancel a running execution before another workspace operation'
            if detail in {'transport_error', 'invalid_response'}:
                detail += ': the operation may have completed; inspect status and workspace before deciding further actions'
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
                    if "ICLAYOUT_BENCH_COMMAND_SECONDS" in os.environ else None,
                    instructions=Path(os.environ['ICLAYOUT_BENCH_INSTRUCTIONS_FILE']).read_text(encoding='utf-8')
                    if 'ICLAYOUT_BENCH_INSTRUCTIONS_FILE' in os.environ else '')
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
