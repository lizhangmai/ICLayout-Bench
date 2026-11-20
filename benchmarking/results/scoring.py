"""Recompute a verified run's score using the shared evaluation contract."""

from benchmarking.evaluation.scoring import attempt_score, recompute_score, same_score
from benchmarking.protocol import layout_score_value


def verified_run_score(run, *, method="layout"):
    """Return one frozen repetition's score, or ``None`` when it is unknown.

    ``run`` is the FrozenRun returned by verify_frozen_run. The evaluator and run
    reports copy the score for convenience; both must agree with the score
    recomputed from the frozen plan, and only the recomputed value is returned.
    """
    report, evaluation, plan = run
    conclusive = attempt_score(report.get("termination"), report.get("outcome"), None, method=method)
    if report.get("termination") == "infrastructure_error":
        return None
    if conclusive is not None:
        if report.get("outcome") == "no_submission" and report.get("candidate") is not None:
            raise ValueError("No-submission report contains a candidate")
        return layout_score_value(conclusive)
    if evaluation is None or plan is None:
        return None
    recomputed = recompute_score(plan, evaluation)
    if recomputed is None:
        return None
    if recomputed.get("method") != method:
        raise ValueError("Evaluation score contract differs from batch")
    for name, declared in (("Evaluation", evaluation.get("score")), ("Run", report.get("score"))):
        if declared is None:
            raise ValueError(f"{name} task score is missing")
        if declared.get("method") != method:
            raise ValueError(f"{name} score contract differs from batch")
        if not same_score(recomputed, declared):
            raise ValueError(f"{name} task score differs from recomputation")
    return layout_score_value(recomputed)
