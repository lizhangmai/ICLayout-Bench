"""Independent solve, command, settlement and evaluation budgets for one session."""

import math
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PhaseBudgets:
    solve_seconds: float
    command_seconds: float = 3600
    settlement_seconds: float = 60
    evaluation_seconds: float = 7200

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
            if name != 'settlement_seconds' and value == 0:
                raise ValueError(f'{name} must be positive')

    def identity(self):
        return asdict(self)

    @classmethod
    def from_limits(cls, limits):
        if 'phase_budgets' in limits:
            return cls(**limits['phase_budgets'])
        # Read historical sessions without restoring their unlimited soft waits.
        return cls(limits.get('wall_seconds', 3600))

    @classmethod
    def for_evaluation(cls, solve_seconds, plan, backends):
        # A serial upper bound permits every declared job its own tool allowance.
        # Actual parallel scheduling can only reduce this time. Archival/cleanup
        # has its own fixed allowance, independent of solve difficulty.
        total = 60
        for job in plan.jobs:
            backend = backends.get(job.operation)
            tool = getattr(backend, 'tool', None)
            while tool is not None and not hasattr(tool, 'timeout_seconds') and hasattr(tool, 'tool'):
                tool = tool.tool
            total += getattr(tool, 'timeout_seconds', 300)
        return cls(solve_seconds, evaluation_seconds=total)


class SessionBudget:
    """Own monotonic transitions; neither polls nor completed work renew a budget."""

    def __init__(self, limits, solve_deadline, *, clock=time.monotonic):
        self.limits, self.solve_deadline, self.clock = limits, solve_deadline, clock
        self.operation_deadline = None
        self.operation_ended = None

    def begin_operation(self, requested=None):
        if self.phase != 'solving':
            raise TimeoutError('Solve budget exhausted; only submit or close is allowed')
        if self.operation_deadline is not None:
            raise RuntimeError('An operation is already active')
        seconds = self.limits.command_seconds if requested is None else min(requested, self.limits.command_seconds)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Command timeout must be positive and finite')
        self.operation_deadline = self.clock() + seconds
        self.operation_ended = None
        return seconds

    def end_operation(self):
        if self.operation_deadline is not None:
            self.operation_ended = min(self.clock(), self.operation_deadline)
            self.operation_deadline = None

    @property
    def settlement_deadline(self):
        end = self.operation_deadline if self.operation_deadline is not None else self.operation_ended
        return max(self.solve_deadline, end or self.solve_deadline) + self.limits.settlement_seconds

    @property
    def phase(self):
        now = self.clock()
        if now < self.solve_deadline:
            return 'solving'
        if self.operation_deadline is not None and now < self.operation_deadline:
            return 'draining'
        return 'settling' if now < self.settlement_deadline else 'expired'

    def snapshot(self):
        now = self.clock()
        return {'phase': self.phase, 'solve_remaining_seconds': max(0, self.solve_deadline-now),
                'command_remaining_seconds': max(0, (self.operation_deadline or now)-now),
                'settlement_remaining_seconds': max(0, self.settlement_deadline-now),
                'phase_budgets': self.limits.identity()}
