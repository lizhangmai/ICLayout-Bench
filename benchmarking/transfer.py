"""Compatibility interface; implementation lives in results.transfer."""

from benchmarking.results.transfer import (
    main,
    pack,
    request,
    safe_name,
    unpack,
)

if __name__ == "__main__":
    main()

__all__ = ['main', 'pack', 'request', 'safe_name', 'unpack']
