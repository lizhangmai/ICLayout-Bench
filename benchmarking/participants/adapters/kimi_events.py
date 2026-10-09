"""Kimi Code terminal stderr interpretation, never shared with other harnesses."""

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


def _code(detail):
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
