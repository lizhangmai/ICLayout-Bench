"""Recognize explicit native startup/crash diagnostics without retaining secrets."""

import re


def native_failure(logs):
    """Inspect native log bytes only; exit numbers alone do not identify a signal."""
    for raw in logs:
        if re.search(rb'(?m)^\s*ERROR \((?:LMF-02002|ELI-00111)\)', raw):
            return {'category': 'license_unavailable', 'source': 'native_tool', 'code': 'license_checkout_failed'}
        if re.search(rb'(?m)^Fatal error \(signal SIG(?:FPE|SEGV|ABRT|ILL)\) - crash handler invoked\s*$', raw):
            return {'category': 'evaluation_tool_error', 'source': 'native_tool', 'code': 'native_crash'}
    return None
