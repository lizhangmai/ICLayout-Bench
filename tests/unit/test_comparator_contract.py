"""Comparator stimuli must interpret both signs of differential input consistently."""


import pytest

from benchmarking.tasks import load_task

pytestmark = pytest.mark.unit
from helpers.catalog import ROOT

COMPARATOR = ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/comparator/case.toml"


def test_comparator_observes_the_output_polarity_of_each_input_difference():
    if not COMPARATOR.exists():
        pytest.skip("Set ICLAYOUT_BENCH_DATASET to run dataset checks")
    task = load_task(COMPARATOR)
    simulations = [job for job in task.evaluation.jobs if job.stage == "simulate"]
    assert simulations
    for job in simulations:
        values = job.parameters["values"]
        assert values["input_difference"] != 0
        assert values["polarity"] == (1 if values["input_difference"] > 0 else -1)
