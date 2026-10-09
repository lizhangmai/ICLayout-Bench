"""Claude Code stream-JSON errors; prose alone never authorizes recovery."""

import re

from .events import ErrorEvidence, classify_evidence, structured_errors
from .native import json_events


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, True)
    events = list(json_events(output / 'harness.jsonl'))
    # Native retries and errors recovered within a successful turn are diagnostic.
    results = [e for e in events if e.get('type') == 'result']
    if not exit_code and results and results[-1].get('is_error') is False:
        return classify_evidence(structured_errors(events), exit_code)
    codes = []
    native_messages = []
    for event in events:
        if event.get('type') != 'assistant' or 'error' not in event:
            continue
        native_code = event['error']
        code = {'authentication_failed': 'authentication_error',
                'billing_error': 'billing_error', 'rate_limit': 'rate_limit_error'}.get(native_code) if isinstance(native_code, str) else None
        message = event.get('message')
        content = message.get('content', []) if isinstance(message, dict) else []
        text = ''.join(item.get('text', '') for item in content
                       if isinstance(item, dict) and item.get('type') == 'text'
                       and isinstance(item.get('text'), str)) if isinstance(content, list) else ''
        native_messages.append(text)
        if (event['error'] == 'server_error' and isinstance(content, list)
                and any(isinstance(item, dict) and item.get('type') == 'text'
                        and isinstance(item.get('text'), str)
                        and re.match(r'^API Error: 529(?:\s|$)', item['text']) for item in content)):
            code = 'server_overloaded'
        codes.append(code)
    # The result repeats the assistant error without a code. Preserve unknown
    # structured failures, but don't let that redundant marker hide HTTP 529.
    redundant = (results[-1] if native_messages and results
                 and results[-1].get('subtype') == 'success'
                 and results[-1].get('is_error') is True
                 and results[-1].get('result') == native_messages[-1] else None)
    evidence = structured_errors(event for event in events if event is not redundant)
    return classify_evidence(ErrorEvidence(tuple(codes) + evidence.codes, evidence.retry_after), exit_code)
