"""Recognize explicit native startup/crash diagnostics without retaining secrets."""

import re


def _diagnose(logs):
    crash = license_error = retryable_license = permanent_license = False
    for raw in logs:
        license_error |= bool(re.search(rb'(?m)^\s*ERROR \((?:LMF-\d+|ELI-00111)\)', raw))
        # Cadence can report this checkout response intermittently. Retry the
        # explicit LMF/FLEXnet pair within the normal bound, without treating
        # other invalid-file, host, key or expiration diagnostics as transient.
        syntax_pattern = rb'FLEXnet ERROR\(-2,\s*0,\s*0\):\s*Invalid license file syntax\.'
        syntax_checkout = (re.search(rb'\bERROR \(LMF-02002\):', raw)
                           and re.search(syntax_pattern, raw, re.IGNORECASE))
        license_log = re.sub(syntax_pattern, b'', raw, flags=re.IGNORECASE) if syntax_checkout else raw
        permanent_license |= bool(re.search(
            rb'Invalid (?:license file|host|.*license key)|Feature has expired', license_log, re.IGNORECASE))
        retryable_license |= bool(syntax_checkout) or bool(re.search(
            rb'No such feature exists|Licensed number of users already reached|All licenses (?:are )?in use|'
            rb'Cannot connect to license server system|License server machine is down or not responding|'
            rb'Desired vendor daemon is down', raw, re.IGNORECASE))
        crash |= bool(re.search(
            rb'(?m)^Fatal error \(signal SIG(?:FPE|SEGV|ABRT|ILL|BUS)\) - crash handler invoked\s*$|'
            rb'ERROR: Process \d+ terminated unexpectedly, signal num: (?:4|6|7|8|11)\. Exiting\.|'
            rb'(?m:^.*\b(?:Segmentation fault|Floating point exception|Aborted) \(core dumped\))', raw))
    if license_error or retryable_license or permanent_license:
        failure = {'category': 'license_unavailable', 'source': 'native_tool', 'code': 'license_checkout_failed'}
        return failure, retryable_license and not permanent_license
    if crash:
        return {'category': 'evaluation_tool_error', 'source': 'native_tool', 'code': 'native_crash'}, True
    return None, False


def native_failure(logs):
    """Inspect native log bytes only; positive exit codes do not identify a signal."""
    return _diagnose(logs)[0]


def retryable_native_failure(logs, returncode):
    """Retry explicit crashes and recoverable license responses, never an arbitrary nonzero exit."""
    failure, retryable = _diagnose(logs)
    if failure is not None:
        return failure if retryable else None
    # Popen's negative status is an OS signal, unlike shell/container status 139.
    if returncode in {-4, -6, -7, -8, -11}:
        return {'category': 'evaluation_tool_error', 'source': 'native_tool', 'code': 'native_crash'}
    return None
