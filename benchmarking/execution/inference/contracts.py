"""Shared inference configuration, request, and usage contracts."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from benchmarking.files import Asset
from benchmarking.protocol import USAGE_FIELDS

MAX_BODY = 8 * 1024 * 1024
MAX_RESPONSE = 16 * 1024 * 1024
INFERENCE_SOCKET = "/protocol/inference.sock"
GENERIC_HTTP_ERROR = b'{"error":"Inference upstream rejected request"}'
GENERIC_RESPONSE_ERROR = b'{"error":"Inference response failed validation"}'
FAILED_OUTCOMES = frozenset({"service_error", "http_error", "protocol_or_transport_error",
                             "incomplete_error", "cancelled"})


@dataclass(frozen=True)
class InferenceConfig:
    base_url: str
    model: str
    api_key_env: str
    max_requests: int
    request_timeout_seconds: int
    source: Asset
    wire_api: str
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_wall_seconds: int | None = None
    proxy_url: str | None = None


@dataclass(frozen=True)
class WireRequest:
    """Provider-wire HTTP request prepared by a registered adapter.

    ``path`` is relative to the fixed profile base URL.  An adapter may choose
    the method, path suffix, and authentication/header convention, while the
    gateway still owns the destination, body/response limits, and deadline.
    """

    method: str
    path: str
    headers: Mapping[str, str]


@dataclass(frozen=True)
class InferenceUsage:
    """Normalized observable usage shared by all wire families."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    cost: float | None = None

    def as_dict(self):
        return {field: getattr(self, field) for field in USAGE_FIELDS}


def normalize_usage(value, *, input_details=None, output_details=None):
    """Normalize adapter-specific usage to the common nullable fields.

    Missing values remain ``None``.  Invalid values are a wire-protocol error;
    the gateway never guesses a zero or fills a missing provider field.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("Inference usage must be an object")
    input_details = input_details if isinstance(input_details, dict) else {}
    output_details = output_details if isinstance(output_details, dict) else {}
    raw = {
        "input_tokens": value.get("input_tokens"),
        "output_tokens": value.get("output_tokens"),
        "cached_input_tokens": value.get("cached_input_tokens", input_details.get("cached_tokens")),
        "reasoning_output_tokens": value.get("reasoning_output_tokens", output_details.get("reasoning_tokens")),
        "cost": value.get("cost"),
    }
    normalized = {}
    for field, item in raw.items():
        if item is None:
            normalized[field] = None
        elif field == "cost":
            if isinstance(item, bool) or type(item) not in {int, float} or not math.isfinite(item) or item < 0:
                raise ValueError(f"Invalid usage field: {field}")
            normalized[field] = float(item)
        elif type(item) is not int or item < 0:
            raise ValueError(f"Invalid usage field: {field}")
        else:
            normalized[field] = item
    return InferenceUsage(**normalized).as_dict()


class WireAdapter(Protocol):
    """Interface implemented by one provider-wire family.

    Adapters own wire-specific request validation, HTTP authentication/header
    conventions, terminal response parsing, and usage mapping.  They must not
    start threads, persist evidence, or enforce session budgets; those remain
    the gateway's responsibilities.
    """

    id: str

    def validate_request(self, path: str, body: bytes, model: str) -> bytes: ...

    def prepare_request(self, path: str, body: bytes, model: str, credential: str) -> WireRequest: ...

    def response_semantics(self, path: str, content_type: str, body: bytes) -> dict: ...
