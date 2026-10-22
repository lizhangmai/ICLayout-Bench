"""Provider-neutral host inference gateway and wire adapters.

The package facade preserves the established ``benchmarking.execution.inference``
imports while implementation modules depend on shared contracts.
"""

from benchmarking.execution.inference.config import load_inference_config
from benchmarking.execution.inference.contracts import (
    FAILED_OUTCOMES,
    GENERIC_HTTP_ERROR,
    GENERIC_RESPONSE_ERROR,
    INFERENCE_SOCKET,
    MAX_BODY,
    MAX_RESPONSE,
    USAGE_FIELDS,
    InferenceConfig,
    InferenceUsage,
    WireAdapter,
    WireRequest,
    normalize_usage,
)
from benchmarking.execution.inference.gateway import (
    INFERENCE_SOURCE_FILES,
    InferenceGateway,
)
from benchmarking.execution.inference.messages import MessagesWireAdapter
from benchmarking.execution.inference.registry import (
    available_wire_adapters,
    register_wire_adapter,
    response_semantics,
    unregister_wire_adapter,
    validate_harness_wire,
    validate_request,
    wire_adapter,
)

__all__ = [
    "FAILED_OUTCOMES",
    "GENERIC_HTTP_ERROR",
    "GENERIC_RESPONSE_ERROR",
    "INFERENCE_SOCKET",
    "INFERENCE_SOURCE_FILES",
    "MAX_BODY",
    "MAX_RESPONSE",
    "USAGE_FIELDS",
    "InferenceConfig",
    "InferenceGateway",
    "InferenceUsage",
    "MessagesWireAdapter",
    "WireAdapter",
    "WireRequest",
    "available_wire_adapters",
    "load_inference_config",
    "normalize_usage",
    "register_wire_adapter",
    "response_semantics",
    "unregister_wire_adapter",
    "validate_harness_wire",
    "validate_request",
    "wire_adapter",
]
