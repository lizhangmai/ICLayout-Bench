"""Trusted process-local registry for inference wire adapters."""

from .contracts import WireAdapter
from .messages import MessagesWireAdapter
from .responses import _ResponsesWireAdapter

_WIRE_ADAPTERS: dict[str, WireAdapter] = {}


def register_wire_adapter(adapter: WireAdapter, *, replace=False):
    """Register a trusted wire-family adapter at the gateway seam.

    An adapter is selected only by the frozen ``wire_api`` profile field.
    Registration is process-local and intended for framework integrations and
    deterministic tests; it is not a plugin loader for task-controlled code.
    """
    name = getattr(adapter, "id", None)
    if (not isinstance(name, str) or not name or name != name.strip()
            or any(not (character.isalnum() or character in "-_.") for character in name)):
        raise ValueError("Wire adapter id must be a nonempty stable name")
    required = ("validate_request", "prepare_request", "response_semantics")
    if any(not callable(getattr(adapter, method, None)) for method in required):
        raise TypeError(f"Wire adapter {name!r} does not implement the gateway interface")
    if name in _WIRE_ADAPTERS and not replace:
        raise ValueError(f"Wire adapter already registered: {name}")
    _WIRE_ADAPTERS[name] = adapter


def unregister_wire_adapter(name):
    """Remove a process-local adapter, primarily for isolated tests."""
    if name in {"responses", "messages"}:
        raise ValueError("Built-in wire adapters cannot be removed")
    _WIRE_ADAPTERS.pop(name, None)


def available_wire_adapters():
    """Return the registered wire-family ids in deterministic order."""
    return tuple(sorted(_WIRE_ADAPTERS))


register_wire_adapter(_ResponsesWireAdapter())
register_wire_adapter(MessagesWireAdapter())


def wire_adapter(name: str) -> WireAdapter:
    adapter = _WIRE_ADAPTERS.get(name)
    if adapter is None:
        raise ValueError(
            f"Unsupported inference wire_api: {name!r}; "
            "add a wire adapter instead of coupling a harness to the runner"
        )
    return adapter


def validate_harness_wire(harness_wire_api, gateway_wire_api):
    """Ensure an explicitly declared harness bridge uses this gateway family."""
    if harness_wire_api is not None and harness_wire_api != gateway_wire_api:
        raise ValueError("Harness wire_api differs from the inference profile")


def validate_request(path, body, model, wire_api):
    """Validate a request using the selected provider-wire adapter."""
    return wire_adapter(wire_api).validate_request(path, body, model)


def response_semantics(path, content_type, body, wire_api):
    """Validate a response using the selected provider-wire adapter."""
    return wire_adapter(wire_api).response_semantics(path, content_type, body)
