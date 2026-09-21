"""Assertions for the public post-layout score contract.

The integration tests call the real evaluator with maintained layouts.  These
helpers only check the stable score envelope; the evaluator remains the source
of the score value and of all physical/electrical evidence.
"""

import math


def assert_layout_score(report):
    """Check one numeric layout score and return its record."""
    score = report.get("score")
    assert isinstance(score, dict), report
    assert score.get("method") in {"layout"}, score
    assert "value" in score and "maximum" in score, score
    assert "total" not in score and "max" not in score, score
    maximum = score["maximum"]
    value = score["value"]
    assert type(value) in {int, float} and math.isfinite(value), score
    assert value >= 0, score
    assert maximum is None and score["reference"] == 100, score
    return score


def assert_same_layout_score(reference, candidate):
    """Compare scores from equivalent runs without requiring float identity."""
    expected = assert_layout_score(reference)
    actual = assert_layout_score(candidate)
    assert actual["method"] == expected["method"]
    assert actual["maximum"] == expected["maximum"]
    assert math.isclose(actual["value"], expected["value"], rel_tol=1e-6,
                        abs_tol=1e-9)
    assert actual["components"].keys() == expected["components"].keys()
    for name, value in expected["components"].items():
        if value is None:
            assert actual["components"][name] is None
        else:
            assert math.isclose(actual["components"][name], value,
                                rel_tol=1e-6, abs_tol=1e-9)


def assert_characterization_unscored(report):
    """Characterization runs expose measurements but never a benchmark score."""
    assert "score" not in report, report


def unscore_characterization(data):
    """Remove post-layout scoring declarations from a derived plan.

    Characterization uses the same jobs and acceptance limits for calibration,
    but it has no candidate physical gates and must not accidentally inherit
    the task's area score or metric attainment metadata.
    """
    data.pop("scoring", None)
    for metric in data.get("metrics", []):
        metric.pop("dimension", None)
        for key in ("baseline", "normalization", "scale"):
            metric.pop(key, None)
        if metric["direction"] == "target" and not {"lower", "upper"} <= metric.keys():
            metric["direction"] = "minimize"
    return data
