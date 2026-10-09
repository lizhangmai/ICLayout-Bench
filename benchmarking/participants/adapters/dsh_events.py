"""DSH headless JSON status evidence; SERVER alone does not mean capacity."""

from .events import ErrorEvidence, classify_evidence, structured_evidence
from .native import json_events


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, True)
    evidence = structured_evidence(output)
    codes = list(evidence.codes)
    for event in json_events(output / 'harness.jsonl'):
        reason = event.get('reason')
        if (event.get('type') != 'status' or event.get('phase') != 'turn_end'
                or not isinstance(reason, dict) or reason.get('kind') != 'error'):
            continue
        detail = reason.get('error')
        code = detail.get('code') if isinstance(detail, dict) else None
        codes.append({'AUTH': 'authentication_error', 'QUOTA': 'insufficient_quota',
                      'RATE_LIMIT': 'rate_limit_error', 'TRANSPORT': 'connection_error',
                      'TIMEOUT': 'connection_error', 'STREAM_CLOSED': 'connection_error'}.get(code)
                     if isinstance(code, str) else None)
    return classify_evidence(ErrorEvidence(tuple(codes), evidence.retry_after), exit_code)
