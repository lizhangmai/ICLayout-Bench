"""Transport retry settings, independent of participant launch and recovery."""

DEFAULTS = {"http_attempts": 1, "backoff_seconds": 0, "max_backoff_seconds": 0}


def policy(value=None):
    """Read transport fields from a retry or fully validated recovery mapping."""
    if value is None:
        return dict(DEFAULTS)
    if not isinstance(value, dict) or not set(DEFAULTS) <= value.keys():
        raise ValueError("retry requires http_attempts, backoff_seconds, max_backoff_seconds")
    settings = {name: value[name] for name in DEFAULTS}
    if type(settings["http_attempts"]) is not int or not 1 <= settings["http_attempts"] <= 10:
        raise ValueError("http_attempts must be between 1 and 10")
    for key in ("backoff_seconds", "max_backoff_seconds"):
        if type(settings[key]) not in (int, float) or not 0 <= settings[key] <= 60:
            raise ValueError(key + " must be finite and between 0 and 60")
    if settings["max_backoff_seconds"] < settings["backoff_seconds"]:
        raise ValueError("Invalid retry backoff")
    return settings
