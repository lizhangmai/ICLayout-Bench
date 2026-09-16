import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]


def _harness_module():
    path = Path(__file__).parents[2] / "tests/fixtures/agents/canonical_harness.py"
    spec = importlib.util.spec_from_file_location("iclayout_bench_canonical_harness", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _response(module, **overrides):
    value = {"schema_version": 1, "type": "response", "content": "",
             "tool_calls": [], "stop_reason": "stop"}
    value.update(overrides)
    return value


def test_response_validation_is_order_independent_and_rejects_unknown_tools():
    module = _harness_module()
    call = {"arguments": {"argv": ["true"]}, "name": "run_command", "id": "call-1"}
    result = module.validate_model_response(_response(module, tool_calls=[call], stop_reason="tool_calls"))
    assert result["tool_calls"] == [{"id": "call-1", "name": "run_command", "arguments": {"argv": ["true"]}}]
    with pytest.raises(ValueError, match="Invalid or duplicate"):
        module.validate_model_response(_response(module, tool_calls=[{
            "id": "call-1", "name": "unknown", "arguments": {},
        }], stop_reason="tool_calls"))
    with pytest.raises(ValueError, match="unknown fields"):
        module.validate_model_response(_response(module, extra=True))


def test_adapter_process_uses_jsonl_without_shell_expansion(tmp_path, monkeypatch):
    module = _harness_module()
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    adapter = tmp_path / "adapter with spaces;literal.py"
    adapter.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    print(json.dumps({'schema_version': 1, 'type': 'response', 'content': request['type'], 'stop_reason': 'stop'}), flush=True)\n"
    )
    with module.AdapterProcess([sys.executable, str(adapter)], timeout=2) as process:
        assert process.request({"schema_version": 1, "type": "request"})["content"] == "request"


def test_adapter_process_rejects_malformed_json_response(tmp_path, monkeypatch):
    module = _harness_module()
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    adapter = tmp_path / "adapter.py"
    adapter.write_text("import sys\nfor _ in sys.stdin:\n    print('{not-json}', flush=True)\n")
    with module.AdapterProcess([sys.executable, str(adapter)], timeout=2) as process, pytest.raises(
            ValueError, match="valid JSON"):
        process.request({"schema_version": 1, "type": "request"})


# Existing adapters always write complete lines and read promptly. These real
# subprocesses protect the declared timeout across both pipe I/O directions.
def test_adapter_process_timeout_covers_partial_response(tmp_path, monkeypatch):
    # The JSONL adapter timeout covers a complete exchange, not only readiness for one byte.
    module = _harness_module()
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import sys\n"
        "sys.stdout.write('{')\n"
        "sys.stdout.flush()\n"
        "sys.stdin.read()\n"
    )
    with module.AdapterProcess([sys.executable, str(adapter)], timeout=.1) as process, pytest.raises(
            TimeoutError, match="response timed out"):
        process.request({"schema_version": 1, "type": "request"})


def test_adapter_process_timeout_covers_blocked_request_write(tmp_path, monkeypatch):
    # A non-reading adapter must not make the bounded request path block before its deadline.
    module = _harness_module()
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    adapter = tmp_path / "adapter.py"
    adapter.write_text("import time\ntime.sleep(1)\n")
    with module.AdapterProcess([sys.executable, str(adapter)], timeout=.1) as process, pytest.raises(
            TimeoutError, match="request timed out"):
        process.request({"payload": "x" * (module.MAX_ADAPTER_LINE_BYTES // 2)})


def test_workspace_tool_bounds_output_and_timeout(tmp_path, monkeypatch):
    module = _harness_module()
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    success = module._tool_result("run_command", {"argv": [sys.executable, "-c", "print('hello')"]})
    assert success["ok"] and success["stdout"] == "hello\n"
    limited = module._tool_result("run_command", {"argv": [sys.executable, "-c", f"print('x' * {module.MAX_TOOL_OUTPUT_BYTES + 1})"]})
    assert not limited["ok"] and limited["truncated"]
    timeout = module._tool_result("run_command", {
        "argv": [sys.executable, "-c", "import time; time.sleep(1)"], "timeout_seconds": .1,
    })
    assert not timeout["ok"] and timeout["timed_out"]
    # EOF is not process completion: a tool may close both streams and keep
    # computing. It must still receive the same deadline and failure result.
    closed = module._tool_result("run_command", {
        "argv": [sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(.5)"],
        "timeout_seconds": .1,
    })
    assert not closed["ok"] and closed["timed_out"]
    schema = next(tool for tool in module.TOOLS if tool["name"] == "run_command")["parameters"]
    maximum = schema["properties"]["timeout_seconds"]["maximum"]
    assert not module._tool_result("run_command", {"argv": ["true"], "timeout_seconds": maximum + 1})["ok"]


# The former timeout killed only the shell; a child could mutate output later.
# Observe a child's file effect independently of the harness's reported result.
def test_workspace_tool_timeout_kills_descendants(tmp_path, monkeypatch):
    # Bounded tool execution owns the process tree, including descendants that inherit its pipes.
    module = _harness_module()
    monkeypatch.setattr(module, "WORKSPACE", tmp_path)
    started = tmp_path / "started"
    late = tmp_path / "late"
    child = (
        "from pathlib import Path; import time; "
        f"Path({str(started)!r}).write_text('started'); "
        "time.sleep(1); "
        f"Path({str(late)!r}).write_text('late')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "print('ready', flush=True); time.sleep(5)"
    )
    result = module._run_process([sys.executable, "-c", parent], .5)
    assert result["timed_out"]
    assert started.is_file()
    time.sleep(1.2)
    assert not late.exists()


@pytest.mark.parametrize('stop_reason', ['stop', 'length', 'error'])
def test_run_executes_tools_and_submits_through_the_fixed_loop(tmp_path, monkeypatch, stop_reason):
    module = _harness_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(module, "WORKSPACE", workspace)
    descriptor = tmp_path / "task.json"
    descriptor.write_text(json.dumps({"id": "synthetic", "output": {"path": "output/final.gds"}}))
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Create the layout.")
    submit = tmp_path / "submit.py"
    submit.write_text("print('{\"accepted\": true, \"sequence\": 1}')\n")
    monkeypatch.setattr(module, "TASK_DESCRIPTOR", descriptor)
    monkeypatch.setattr(module, "PROMPT", prompt)
    monkeypatch.setattr(module, "SUBMIT", submit)
    adapter = tmp_path / "adapter.py"
    responses = [
        {"schema_version": 1, "type": "response", "content": "", "stop_reason": "tool_calls",
         "tool_calls": [{"id": "write", "name": "run_command", "arguments": {
             "argv": [sys.executable, "-c",
                      "from pathlib import Path; Path('marker').write_text('ok')"]}}]},
        {"schema_version": 1, "type": "response", "content": "", "stop_reason": "tool_calls",
         "tool_calls": [{"id": "submit", "name": "submit_layout", "arguments": {}}]},
        {"schema_version": 1, "type": "response", "content": "done", "stop_reason": stop_reason},
    ]
    adapter.write_text(
        "import json, sys\n"
        f"responses = json.loads({json.dumps(responses)!r})\n"
        "for index, line in enumerate(sys.stdin, 1):\n"
        "    json.loads(line)\n"
        "    print(json.dumps(responses[index - 1]), flush=True)\n"
    )
    # A prior submission must not turn an adapter error/truncation into normal
    # CLI completion, which the runner would otherwise treat as scoreable.
    monkeypatch.setattr(sys, 'argv', ['canonical_harness.py', '--max-turns', '4',
                                     '--adapter-timeout', '2', '--adapter', sys.executable, str(adapter)])
    if stop_reason == 'stop':
        module.main()
    else:
        with pytest.raises(SystemExit) as error:
            module.main()
        assert error.value.code != 0
    assert (workspace / "marker").read_text() == "ok"


def test_run_rejects_adapter_that_never_stops(tmp_path, monkeypatch):
    module = _harness_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(module, "WORKSPACE", workspace)
    descriptor = tmp_path / "task.json"
    descriptor.write_text(json.dumps({"id": "synthetic"}))
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Create the layout.")
    monkeypatch.setattr(module, "TASK_DESCRIPTOR", descriptor)
    monkeypatch.setattr(module, "PROMPT", prompt)
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json, sys\n"
        "for index, line in enumerate(sys.stdin, 1):\n"
        "    json.loads(line)\n"
        "    response = {'schema_version': 1, 'type': 'response', 'content': '', 'stop_reason': 'tool_calls', 'tool_calls': [{'id': 'call-' + str(index), 'name': 'run_command', 'arguments': {'argv': ['true']}}]}\n"
        "    print(json.dumps(response), flush=True)\n"
    )
    with pytest.raises(TimeoutError, match="max_turns"):
        module.run([sys.executable, str(adapter)], max_turns=1, adapter_timeout=2)
