"""Shared EDA results and bounded recovery of infrastructure failures."""

import json
import subprocess
import time
from dataclasses import dataclass, replace

from benchmarking.execution.tools.budget import (
    tool_deadline,
    tool_timeout,
    wait_for_retry,
)
from benchmarking.execution.tools.diagnostics import (
    native_failure,
    retryable_native_failure,
)
from benchmarking.files import Asset


@dataclass
class ToolResult:
    returncode: int | None
    reason: str
    files: dict[str, Asset]
    evidence: dict[str, Asset]


def tool_retry_policy():
    """One policy for native/container jobs and all their callers."""
    return {'max_attempts': 3, 'backoff_seconds': 1, 'max_backoff_seconds': 2}


def run_with_retries(attempt, timeout_seconds):
    """Replay a fresh-workspace attempt with identical frozen inputs; retain failed attempts."""
    policy = tool_retry_policy()
    seconds = tool_timeout(timeout_seconds)
    records, retained = [], {}
    started = time.monotonic()

    def finish(result, termination):
        if len(records) == 1 and not retained:
            return result
        metadata = {'policy': policy, 'attempts': records, 'termination': termination,
                    'elapsed_seconds': time.monotonic()-started}
        return replace(result, evidence={**result.evidence, **retained,
            'tool-attempts.json': Asset(json.dumps(metadata, sort_keys=True).encode(), 'json')})

    def interrupted(termination):
        reason = 'EDA retry cancelled' if termination == 'cancelled' else 'EDA retry reached its enclosing deadline'
        return finish(ToolResult(None, reason, {}, {'execution_error': Asset(reason.encode(), 'text')}), termination)

    with tool_deadline(None if seconds is None else started+seconds):
        for number in range(1, policy['max_attempts']+1):
            stopped = wait_for_retry(0)
            if stopped:
                return interrupted(stopped)
            begin = time.monotonic()
            try:
                result = attempt()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                if not records:
                    raise
                reason = f'EDA retry could not complete: {type(error).__name__}'
                result = ToolResult(None, reason, {}, {'execution_error': Asset(reason.encode(), 'text')})
            failed = bool(result.reason) or result.returncode != 0
            logs = [a.content for a in (*result.evidence.values(), *result.files.values()) if a.format == 'text']
            retryable = (retryable_native_failure(logs, result.returncode)
                         if failed and 'cleanup_error' not in result.evidence else None)
            record = {'attempt': number, 'returncode': result.returncode,
                      'elapsed_seconds': time.monotonic()-begin,
                      'failure': retryable or (native_failure(logs) if failed else None),
                      'evidence_prefix': ''}
            records.append(record)
            if retryable is None:
                return finish(result, 'non_retryable' if failed else 'completed')
            if number == policy['max_attempts']:
                return finish(result, 'exhausted')
            prefix = f'tool-attempts/{number}'
            record['evidence_prefix'] = prefix
            for group, assets in (('evidence', result.evidence), ('outputs', result.files)):
                retained.update({f'{prefix}/{group}/{name}': asset for name, asset in assets.items()})
            delay = min(policy['max_backoff_seconds'], policy['backoff_seconds'] * 2**(number-1))
            record['retry_delay_seconds'] = delay
            stopped = wait_for_retry(delay)
            if stopped:
                return interrupted(stopped)
    raise AssertionError('EDA retry policy did not finish')
