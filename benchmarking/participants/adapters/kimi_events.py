"""Kimi Code native record interpretation, never shared with other harnesses."""

import json
import re
from pathlib import Path

from ..failures import failure
from .events import ErrorEvidence, classify_evidence, structured_evidence

PREFIX = 'error: failed to run prompt: '
ERROR = re.compile(r'(?P<code>[a-z][a-z_.]+): (?:(?P<status>[0-9]{3}) )?(?P<message>.*)')
QUOTA_MESSAGES = ("you've reached your 5-hour usage limit", "you've reached your weekly (7-day) usage limit",
                  "you've reached your monthly usage limit")


def json_events(path):
    if Path(path).is_file():
        for line in Path(path).read_text(errors='replace').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event


def conversation_messages(events):
    """Read legacy messages and main-agent loop events in journal order."""
    messages, open_steps, pending = [], set(), set()
    use_loop = any(record.get('type') == 'context.append_loop_event' and record.get('agentId') == 'main'
                   for record in events)
    for record in events:
        kind = record.get('type')
        if kind == 'agent.message.appended' and record.get('agentId', 'main') == 'main':
            # New journals also append transcript events that mirror the loop.
            # Only context records govern native restoration in this format.
            if not use_loop:
                messages.append(record['message']['message'])
        elif record.get('agentId') != 'main':
            continue
        elif kind in {'context.clear', 'context.undo', 'context.apply_compaction'}:
            # Native history rewrites invalidate earlier delivery evidence.
            messages.append({'role': 'context_reset'})
            open_steps.clear()
            pending.clear()
        elif kind == 'context.append_loop_event':
            event = record['event']
            if event['type'] == 'step.begin':
                # Kimi closes outstanding replies before starting a new step;
                # a late result for a prior step does not enter its context.
                pending.clear()
                open_steps.add(event['uuid'])
            elif event['type'] == 'step.end':
                open_steps.discard(event['uuid'])
            elif event['type'] == 'tool.call':
                if (event.get('stepUuid') not in open_steps
                        or not isinstance(event.get('uuid'), str) or not event['uuid']
                        or not isinstance(event.get('toolCallId'), str) or not event['toolCallId']
                        or not isinstance(event.get('args'), dict)):
                    raise ValueError('Invalid Kimi loop tool call')
                call = {'type': 'function', 'id': event['toolCallId'], 'name': event['name'],
                        'arguments': json.dumps(event['args']), 'nativeUuid': event['uuid']}
                messages.append({'role': 'assistant', 'toolCalls': [call]})
                pending.add(call['id'])
            elif event['type'] == 'tool.result':
                call_id = event['toolCallId']
                if call_id not in pending:
                    continue
                native_result = event['result']
                messages.append({'role': 'tool', 'toolCallId': call_id,
                                 'parentUuid': event.get('parentUuid'),
                                 'isError': native_result.get('isError'),
                                 'note': native_result.get('note'),
                                 'content': [{'type': 'text', 'text': native_result['output']}]})
                pending.remove(call_id)
    return messages


def _code(detail):
    if detail == 'The provided authorization grant is invalid':
        return 'authentication_error'
    match = ERROR.fullmatch(detail)
    if match is None:
        return None
    code, status, message = match['code'], match['status'], match['message'].casefold()
    if status in {'403', '429'} and message.startswith(QUOTA_MESSAGES):
        return 'insufficient_quota'
    if status == '403' and message.startswith("you've reached your concurrent request limit"):
        return 'rate_limit_error'
    if code == 'provider.overloaded' or (status == '429' and message.startswith('the engine is currently overloaded')):
        return 'server_overloaded'
    if code == 'provider.auth_error' or status == '401':
        return 'authentication_error'
    if code == 'provider.connection_error':
        return 'connection_error'
    if code == 'provider.rate_limit' or status == '429':
        return 'rate_limit_error'
    return None


def harness_failure(output, exit_code=None, timed_out=False):
    if timed_out:
        return classify_evidence(ErrorEvidence(), exit_code, timed_out)
    evidence = structured_evidence(output)
    if timed_out or not exit_code:
        return classify_evidence(evidence, exit_code, timed_out)
    codes = list(evidence.codes)
    configuration = False
    stderr = Path(output, 'harness.stderr')
    for line in stderr.read_text(errors='replace').splitlines() if stderr.is_file() else ():
        if line.startswith(PREFIX):
            detail = line.removeprefix(PREFIX)
            configuration |= detail.startswith('provider ') and detail.endswith(' has no credential configured')
            codes.append(_code(detail))
    result = classify_evidence(ErrorEvidence(tuple(codes), evidence.retry_after), exit_code, timed_out)
    if configuration and result['category'] == 'unknown':
        return failure('harness_configuration', 'harness_stderr', 'missing_provider_credential')
    return result
