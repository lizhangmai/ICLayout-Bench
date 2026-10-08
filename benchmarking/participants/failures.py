"""Normalized participant failures, independent of provider event formats."""

from benchmarking.client import ClientError


def failure(category, source, code=None):
    return {"category": category, "source": source, "code": code,
            "retryable": category in {"network_transient", "rate_limit", "provider_overloaded"},
            "stop_dispatch": category in {"quota_exhausted", "authentication", "service_failure", "harness_configuration"}}


def classify(error):
    if isinstance(error, ClientError):
        category = {"transport_error": "network_transient", "unauthorized": "authentication",
                    "budget_exhausted": "budget_exhausted", "unavailable": "service_failure",
                    "infrastructure_error": "service_failure"}.get(error.code, "unknown")
        return failure(category, "http", error.code)
    return failure("unknown", "runner", type(error).__name__)
