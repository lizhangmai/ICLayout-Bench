"""ZCode terminal turn failures; provider prose never establishes a failure."""

from .events import ErrorEvidence, classify_evidence, read_events, structured_errors


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, True)
    normalized = []
    failed_result = False
    for event in read_events(output):
        payload = event.get('payload', {})
        if event.get('type') == 'turn.failed' and isinstance(payload, dict) and isinstance(payload.get('error'), dict):
            detail = payload['error']
            attribution = detail.get('attribution', {})
            code = detail.get('code')
            if isinstance(attribution, dict):
                if attribution.get('source') == 'provider':
                    code = attribution.get('providerErrorCode') or code
                elif (attribution.get('source') == 'network' and attribution.get('exceptionKind') == 'transport'
                      and attribution.get('retryable') is True
                      and attribution.get('reason') in {'timeout', 'stream_idle_timeout', 'network_error', 'proxy_error'}):
                    code = 'connection_error'
            normalized.append({'type': 'turn.failed', 'code': code})
        else:
            normalized.append(event)
        if event.get('type') == 'result' and isinstance(event.get('projection'), dict):
            failed_result = failed_result or event['projection'].get('status') == 'error'
    if failed_result and not any(event.get('type') in {'error', 'turn.failed'} for event in normalized):
        normalized.append({'type': 'error'})
    return classify_evidence(structured_errors(normalized), exit_code)
