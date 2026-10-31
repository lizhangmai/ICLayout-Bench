"""Independent solve, command, settlement and evaluation budgets for one session."""

import math
import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PhaseBudgets:
    solve_seconds: float
    command_seconds: float | None = None
    settlement_seconds: float = 60
    evaluation_seconds: float | None = None

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name in {'command_seconds', 'evaluation_seconds'} and value is None:
                continue
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
        # Historical finite evaluation budgets remain readable; new sessions
        # wait for independent EDA evaluation without an automatic deadline.
        return cls(limits.get('wall_seconds', 3600), command_seconds=limits.get('max_command_seconds'))

    @classmethod
    def for_evaluation(cls, solve_seconds, plan, backends):
        # Backend timeouts are bounded-probe settings, not a final-judging budget.
        return cls(solve_seconds)


def command_timeout(requested=None, maximum=None):
    """Honor explicit finite allowances without manufacturing an automatic cap."""
    values = [value for value in (requested, maximum) if value is not None]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
           for value in values):
        raise ValueError('Command timeout must be positive and finite')
    return min(values) if values else None


class SessionBudget:
    """Own monotonic transitions; neither polls nor completed work renew a budget."""

    def __init__(self, limits, solve_deadline, *, clock=time.monotonic):
        self.limits, self.solve_deadline, self.clock = limits, solve_deadline, clock
        self.operation_deadline = None
        self.operation_ended = None
        self.operation_active = False

    def begin_operation(self, requested=None):
        if self.phase != 'solving':
            raise TimeoutError('Solve budget exhausted; only submit or close is allowed')
        if self.operation_active:
            raise RuntimeError('An operation is already active')
        seconds = command_timeout(requested, self.limits.command_seconds)
        self.operation_deadline = self.clock() + seconds if seconds is not None else None
        self.operation_ended = None
        self.operation_active = True
        return seconds

    def end_operation(self):
        if self.operation_active:
            self.operation_ended = (min(self.clock(), self.operation_deadline)
                                    if self.operation_deadline is not None else self.clock())
            self.operation_deadline = None
            self.operation_active = False

    @property
    def settlement_deadline(self):
        if self.operation_active and self.operation_deadline is None:
            return None
        end = self.operation_deadline if self.operation_deadline is not None else self.operation_ended
        return max(self.solve_deadline, end or self.solve_deadline) + self.limits.settlement_seconds

    @property
    def phase(self):
        now = self.clock()
        if now < self.solve_deadline:
            return 'solving'
        if self.operation_active and (self.operation_deadline is None or now < self.operation_deadline):
            return 'draining'
        return 'settling' if now < self.settlement_deadline else 'expired'

    def snapshot(self):
        now = self.clock()
        return {'phase': self.phase, 'solve_remaining_seconds': max(0, self.solve_deadline-now),
                'command_remaining_seconds': (None if self.operation_active and self.operation_deadline is None
                                               else max(0, (self.operation_deadline or now)-now)),
                'settlement_remaining_seconds': (max(0, self.settlement_deadline-now)
                                                  if self.settlement_deadline is not None else None),
                'phase_budgets': self.limits.identity()}
