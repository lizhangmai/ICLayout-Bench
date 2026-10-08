"""Request validation, service errors and task-bound session limits."""

import math
from datetime import UTC, datetime


def utc(epoch):
    return datetime.fromtimestamp(epoch, UTC).isoformat().replace('+00:00', 'Z')


class APIError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def fields(body, expected):
    if not isinstance(body, dict) or set(body) != set(expected):
        raise ValueError('Unexpected request fields')


def session_limits(task, seconds=None):
    if task.hours is not None:
        if seconds is not None and not math.isclose(seconds, task.wall_seconds):
            raise ValueError("Service budget cannot override task hours")
        seconds = task.wall_seconds
    if seconds is None:
        raise ValueError("Task must explicitly declare hours before serving a solve")
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Session budget must be positive and finite')
    return {'wall_seconds': seconds, 'budget_policy': 'soft', 'cpus': 4, 'memory_mb': 8192, 'pids': 512, 'workspace_mb': 2048,
                           'max_file_bytes': 4*1024*1024, 'max_response_bytes': 8*1024*1024,
                           'max_candidate_bytes': task.output.max_bytes, 'max_command_seconds': seconds,
                           'max_log_bytes': 4*1024*1024, 'opinion_requests': 0}
