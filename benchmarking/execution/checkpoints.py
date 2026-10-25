"""Bounded workspace recovery policy, shared by transport and durable commits."""

import errno
import math
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CheckpointPolicy:
    total_seconds: float = 300
    idle_seconds: float = 60
    compression_level: int = 1

    def __post_init__(self):
        if (any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                for v in (self.total_seconds, self.idle_seconds))
                or self.idle_seconds > self.total_seconds
                or type(self.compression_level) is not int or not 0 <= self.compression_level <= 9):
            raise ValueError('Invalid workspace checkpoint policy')

    def identity(self):
        return asdict(self)


DEFAULT_CHECKPOINT_POLICY = CheckpointPolicy()


def checkpoint_failure(error):
    """Known shared storage failures stop that runtime; other failures isolate a session."""
    return {'code': 'checkpoint_timeout' if isinstance(error, subprocess.TimeoutExpired) else 'checkpoint_failed',
            'scope': 'runtime' if isinstance(error, OSError) and error.errno in {
                errno.ENOSPC, errno.EDQUOT, errno.EROFS} else 'session',
            'exception_type': type(error).__name__,
            **{k: getattr(error, k) for k in ('stage', 'elapsed_seconds', 'archive_bytes') if hasattr(error, k)}}
