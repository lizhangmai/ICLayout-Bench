"""Service cohort analysis is independent of legacy private batch verification.

Expectations follow missing-value and condition-separation contracts, rather than
copying generated CSVs. Synthetic input scores exercise statistics only.
"""

import csv

import pytest

from benchmarking.analysis import export_results
from benchmarking.protocol import PROTOCOL, USAGE_FIELDS

pytestmark = pytest.mark.unit


def sample(sid, kind="official", outcome="pass", score=80):
    return {
        "protocol": PROTOCOL,
        "session_id": sid,
        "task_id": "task",
        "task_sha256": "a" * 64,
        "condition": {
            "harness_kind": kind,
            "harness_id": "fixture",
            "harness_version": "1",
            "model": "model",
            "prompt_sha256": None,
            "configuration_sha256": None,
        },
        "limits": {},
        "tool_identity": {},
        "verification_level": "local_development",
        "state": "complete",
        "outcome": outcome,
        "score": {"value": score},
        "usage": dict.fromkeys(USAGE_FIELDS),
    }


def test_unknown_errors_do_not_become_zero_or_merge_custom_conditions(tmp_path):
    output = export_results(
        [
            sample("one"),
            sample("two", outcome="error", score=0),
            sample("three", "custom", outcome="no_submission", score=0),
        ],
        tmp_path / "out",
    )
    with (output / "tasks.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    incomplete = next(row for row in rows if row["trials"] == "2")
    assert float(incomplete["mean"]) == 80 and incomplete["unknown"] == "1"
    unsubmitted = next(row for row in rows if row["trials"] == "1")
    assert float(unsubmitted["mean"]) == 0 and unsubmitted["no_submission"] == "1"
    with (output / "runs.csv").open() as f:
        runs = list(csv.DictReader(f))
    assert next(row for row in runs if row["session_id"] == "two")["score"] == ""
    assert all(row["input_tokens"] == "" for row in runs)


def test_protocol_simulator_cannot_be_analyzed_as_measurement(tmp_path):
    with pytest.raises(ValueError, match="real protocol"):
        export_results([sample("simulation") | {"test_only": True}], tmp_path / "out")
