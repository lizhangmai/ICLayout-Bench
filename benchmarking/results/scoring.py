"""Recompute a verified run's score using the shared evaluation contract."""

import math

from benchmarking.evaluation.scoring import attempt_score, recompute_score
from benchmarking.protocol import layout_score_value


def verified_run_score(report, evaluation, *, method="layout"):
    """Return one frozen repetition's score, or ``None`` when it is unknown."""
    conclusive = attempt_score(report.get("termination"), report.get("outcome"), None, method=method)
    if report.get("termination") == "infrastructure_error":
        return None
    if conclusive is not None:
        if report.get("outcome") == "no_submission" and report.get("candidate") is not None:
            raise ValueError("No-submission report contains a candidate")
        return layout_score_value(conclusive)
    if evaluation is None:
        return None
    plan = evaluation.get("_frozen_plan")
    recomputed = recompute_score(plan, evaluation) if plan is not None else None
    if recomputed is None:
        return None
    recomputed_value = layout_score_value(recomputed)
    declared = evaluation.get("score")
    if declared is None:
        if isinstance(recomputed, dict):
            raise ValueError("Evaluation task score is missing")
        return None
    declared_value = layout_score_value(declared)
    if any(item.get("method") != method for item in (declared, recomputed)):
        raise ValueError("Evaluation score contract differs from batch")
    if (
        (recomputed_value is None) != (declared_value is None)
        or recomputed_value is not None and (not math.isclose(recomputed_value, declared_value, rel_tol=1e-12, abs_tol=1e-12))
    ):
        raise ValueError("Evaluation task score differs from recomputation")
    # run_session copies the evaluator score into run.json for convenience. It
    # remains untrusted evidence, so verify it when present and use only the
    # independently recomputed value below.
    reported = report.get("score")
    if reported is not None:
        reported_value = layout_score_value(reported)
        if reported["method"] != method:
            raise ValueError("Run score contract differs from batch")
        if (
            (recomputed_value is None) != (reported_value is None)
            or recomputed_value is not None and (not math.isclose(recomputed_value, reported_value, rel_tol=1e-12, abs_tol=1e-12))
        ):
            raise ValueError("Run task score differs from recomputation")
    elif isinstance(recomputed, dict):
        raise ValueError("Run task score is missing")
    return recomputed_value
