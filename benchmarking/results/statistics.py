"""Shared score arithmetic without cohort, evaluator or database policy."""

from dataclasses import dataclass
from statistics import mean, stdev


@dataclass(frozen=True)
class ScoreSummary:
    measured: int
    mean: float | None
    sample_stddev: float | None


def score_summary(values):
    measured = [value for value in values if value is not None]
    return ScoreSummary(len(measured), mean(measured) if measured else None,
                        stdev(measured) if len(measured) > 1 else None)
