"""Exclusive local file leases, including inherited case ownership."""

import errno
import fcntl
import os
from pathlib import Path


class BatchLeaseError(OSError):
    """Another process currently owns the exclusive lease for a batch."""


class BatchLease:
    """Coordinate local recovery owners without changing batch evidence."""

    filename = ".batch.lock"
    unlock_on_exit = True

    def __init__(self, destination):
        self.root = Path(destination).absolute()
        self.path = self.root / self.filename
        self._stream = None

    def __enter__(self):
        if self._stream is not None:
            raise BatchLeaseError(errno.EBUSY, f"Batch is already leased: {self.root}")
        stream = self.path.open("a+b")
        try:
            os.fchmod(stream.fileno(), 0o600)
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise BatchLeaseError(errno.EWOULDBLOCK,
                                       f"Batch is already leased: {self.root}") from error
            raise
        self._stream = stream
        return self

    def fileno(self):
        """Descriptor inherited by a worker that shares this lease."""
        if self._stream is None:
            raise ValueError("Lease is not held")
        return self._stream.fileno()

    def __exit__(self, exception_type, exception, traceback):
        stream, self._stream = self._stream, None
        if stream is None:
            return False
        try:
            if self.unlock_on_exit:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
        return False
