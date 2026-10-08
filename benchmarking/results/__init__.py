"""Durable result archives. Optional dependencies are installed with iclayout-bench[results]."""

__all__ = ["ResultStore"]


def __getattr__(name):
    if name == "ResultStore":
        from .store import ResultStore

        globals()[name] = ResultStore
        return ResultStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
