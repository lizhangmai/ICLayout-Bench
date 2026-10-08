"""Terminal result, observation and redacted trace exports."""
import json
import time
import uuid

from benchmarking.files import atomic_write
from benchmarking.observe import export_observation
from benchmarking.results.analysis import export_session_result

from .attempt import ParticipantAttempt


def collect_result(client, sid, output):
    deadline = time.monotonic() + 600
    while deadline is None or time.monotonic() < deadline:
        result = client.result(sid)
        if result.get('limits', {}).get('budget_policy') == 'soft':
            deadline = None
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
                state = ParticipantAttempt.read_state(output)
                export_traces = private / "export-traces"
                export_traces.mkdir(mode=0o700, exist_ok=True)
                redacted = []
                for source in traces:
                    content = source.read_bytes()
                    for secret in sorted(state.redactions, key=len, reverse=True):
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
