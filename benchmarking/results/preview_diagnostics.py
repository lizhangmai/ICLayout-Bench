"""Bounded, redacted diagnostics for optional layout rendering failures."""

import hashlib
import json
import os
import re
import subprocess
import traceback
from datetime import UTC, datetime
from pathlib import Path

from benchmarking.files import atomic_write

MAX_TEXT_BYTES = 64 * 1024
_SECRET_NAME = r'(?:token|secret|password|passwd|api[_-]?key|credential|license|lic_file)'
_SECRET_ENV = re.compile(_SECRET_NAME + r'|auth', re.IGNORECASE)
_ASSIGNMENT = re.compile(
    rf'''(["']?[\w.-]*{_SECRET_NAME}[\w.-]*["']?\s*[:=]\s*)("[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}}\]]+)''',
    re.IGNORECASE,
)
_AUTHORIZATION = re.compile(
    r'''(["']?\b(?:proxy-)?authorization["']?\s*[:=]\s*)("[^"\r\n]*"|'[^'\r\n]*'|[^\r\n]+)''',
    re.IGNORECASE,
)
_ABSOLUTE_PATH = re.compile(r'''(?<![\w:/>])/(?:[^/\s"'<>(),;\[\]{}]+/)*([^/\s"'<>(),;\[\]{}]+)''')
_WINDOWS_PATH = re.compile(r'''\b[A-Za-z]:[\\/](?:[^\\/\s"'<>(),;]+[\\/])*([^\\/\s"'<>(),;]+)''')


class PreviewRenderError(RuntimeError):
    """Keep tool evidence alive until the optional-preview boundary persists it."""

    def __init__(self, message, *, stage, renderer, result):
        super().__init__(message)
        self.details = {
            'stage': stage, 'renderer': renderer,
            'returncode': result.returncode, 'reason': result.reason,
            'logs': {name: asset.content for name, asset in result.evidence.items()
                     if asset.format in {'text', 'json'}},
        }


def _text(value, secrets):
    value = value.decode('utf-8', errors='replace') if isinstance(value, bytes) else str(value)
    for secret in secrets:
        value = value.replace(secret, '<REDACTED>')
    value = _AUTHORIZATION.sub(r'\1<REDACTED>', value)
    value = re.sub(r'(?i)(\bbearer\s+)[\w.~+/=-]+', r'\1<REDACTED>', value)
    value = _ASSIGNMENT.sub(r'\1<REDACTED>', value)
    value = re.sub(r'(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@', r'\1<REDACTED>@', value)
    value = _WINDOWS_PATH.sub(r'<path>/\1', value)
    value = _ABSOLUTE_PATH.sub(r'<path>/\1', value)
    encoded = value.encode('utf-8')
    if len(encoded) > MAX_TEXT_BYTES:
        marker = b'\n<truncated>\n'
        head = (MAX_TEXT_BYTES - len(marker)) // 2
        tail = MAX_TEXT_BYTES - len(marker) - head
        value = (encoded[:head].decode('utf-8', errors='ignore') + marker.decode()
                 + encoded[-tail:].decode('utf-8', errors='ignore'))
    return value


def _sanitize(value, secrets):
    if isinstance(value, dict):
        return {_text(k, secrets): _sanitize(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, secrets) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _text(value, secrets)


def save_diagnostics(case_dir, error):
    """Return an immutable relative artifact path; never put raw logs in result.json."""
    report = {
        'format': 'layout-preview-error', 'version': 1,
        'recorded_at': datetime.now(UTC).isoformat(),
        'error_type': type(error).__name__, 'message': str(error),
        'traceback': ''.join(traceback.format_exception(error)),
    }
    if isinstance(error, PreviewRenderError):
        report['details'] = error.details
    # Subprocess failures can happen before a tool result exists (image inspection,
    # native rasterizer startup), and their output is absent from str(error).
    cause, seen = error, set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
            report['process'] = {
                'command': cause.cmd, 'returncode': getattr(cause, 'returncode', None),
                'timeout_seconds': getattr(cause, 'timeout', None),
                'stdout': cause.stdout, 'stderr': cause.stderr,
            }
            break
        cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
    secrets = sorted({v for k, v in os.environ.items() if v and _SECRET_ENV.search(k)}, key=len, reverse=True)
    content = (json.dumps(_sanitize(report, secrets), indent=2, ensure_ascii=False) + '\n').encode()
    # Unique names preserve earlier failures and avoid conflicting immutable
    # artifacts when a result is imported again after a preview retry.
    name = f'layout-preview-errors/{hashlib.sha256(content).hexdigest()}.json'
    path = Path(case_dir) / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write(path, content)
    return name
