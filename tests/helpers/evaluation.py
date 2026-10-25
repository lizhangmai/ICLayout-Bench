"""Synthetic evaluation plans and backends shared by contract tests."""

from typing import ClassVar

from benchmarking.evaluation import parse_evaluation
from benchmarking.evaluation.contracts import JobResult, Measurement
from benchmarking.evaluation.runner import run_evaluation
from benchmarking.files import Asset

PLAN = b'''
mode = "post_layout"

[scoring]
method = "layout"
area_metric = "functional_area"
area_target = 1.0
rationale = "Delay and area control."
weights = {delay = 0.5, functional_area = 0.5}

[[jobs]]
id = "slow"
stage = "simulate"
operation = "response"
inputs = { dut = "job:parasitics:netlist" }
[jobs.parameters]
load = 2.0

[[jobs]]
id = "artifact"
stage = "check"
operation = "check"
gate = "artifact"
inputs = { layout = "candidate" }

[[jobs]]
id = "drc"
stage = "check"
operation = "check"
gate = "drc"
inputs = { layout = "candidate" }
requires = ["artifact"]

[[jobs]]
id = "lvs"
stage = "check"
operation = "check"
gate = "lvs"
inputs = { layout = "candidate", schematic = "input:netlist" }
requires = ["artifact"]

[[jobs]]
id = "geometry"
stage = "check"
operation = "check"
gate = "constraint"
inputs = { layout = "candidate" }
requires = ["artifact", "drc", "lvs"]

[[jobs]]
id = "parasitics"
stage = "extract"
operation = "extract"
inputs = { layout = "candidate" }
requires = ["artifact", "drc", "lvs", "geometry"]
outputs = { netlist = "spice" }

[[jobs]]
id = "nominal"
stage = "simulate"
operation = "response"
inputs = { dut = "job:parasitics:netlist" }
[jobs.parameters]
load = 1.0

[[metrics]]
id = "delay"
category = "performance"
observations = ["nominal:delay", "slow:delay"]
unit = "s"
direction = "minimize"
aggregation = "max"
requirement = { upper = 4.0, rationale = "The synthetic event must occur within its stimulus cycle." }
baseline = ["source_nominal:delay", "source_slow:delay"]
normalization = "ratio"
dimension = "response"

[[metrics]]
id = "functional_area"
category = "physical"
observations = ["geometry:area"]
unit = "um2"
direction = "minimize"
aggregation = "max"

[pre_layout]
source_report_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

[pre_layout.backends]
response = "synthetic reference"

[pre_layout.jobs.source_nominal]
operation = "response"

[pre_layout.jobs.source_nominal.inputs]
dut = "input:netlist"

[pre_layout.jobs.source_nominal.parameters]
load = 1.0

[pre_layout.jobs.source_nominal.outputs]

[pre_layout.jobs.source_nominal.input_sha256]
dut = "6604afd98a39f581bd04e52a12c75294eccd42bc69f94d8cc4419807bf8a3620"

[pre_layout.jobs.source_nominal.measurements.delay]
value = 1.0
unit = "s"

[pre_layout.jobs.source_slow]
operation = "response"

[pre_layout.jobs.source_slow.inputs]
dut = "input:netlist"

[pre_layout.jobs.source_slow.parameters]
load = 2.0

[pre_layout.jobs.source_slow.outputs]

[pre_layout.jobs.source_slow.input_sha256]
dut = "6604afd98a39f581bd04e52a12c75294eccd42bc69f94d8cc4419807bf8a3620"

[pre_layout.jobs.source_slow.measurements.delay]
value = 3.0
unit = "s"
'''


class Checks:
    identity: ClassVar[dict] = {"adapter": "synthetic-checks", "version": "1"}

    def __init__(self, reject=None, crash=None, area=1.5):
        self.area = area
        self.reject = reject
        self.crash = crash
        self.calls = []

    def run(self, job, inputs):
        self.calls.append(job.id)
        if job.id == self.crash:
            raise RuntimeError("Tool failed unexpectedly")
        measurements = {"area": Measurement(self.area, "um2")} if job.id == "geometry" else {}
        return JobResult("failed" if job.id == self.reject else "passed",
                         "Synthetic rejection" if job.id == self.reject else "",
                         measurements=measurements,
                         evidence={"log": Asset(job.id.encode(), "text")})


class Extractor:
    identity: ClassVar[dict] = {"adapter": "synthetic-extractor", "version": "1"}

    def run(self, job, inputs):
        assert inputs["layout"].content == b"synthetic-layout"
        return JobResult("passed", outputs={"netlist": Asset(b"derived-from-layout", "spice")},
                         evidence={"log": Asset(b"extraction evidence", "text")})


class Simulator:
    identity: ClassVar[dict] = {"adapter": "synthetic-simulator", "version": "1"}

    def __init__(self, factor=1.0, unit="s", missing=False):
        self.factor, self.unit, self.missing = factor, unit, missing

    def run(self, job, inputs):
        assert inputs["dut"].content in {b"derived-from-layout", b"schematic", b"netlist"}
        value = self.factor * (1.0 if job.parameters["load"] == 1.0 else 3.0)
        return JobResult("passed", measurements={} if self.missing else {"delay": Measurement(value, self.unit)},
                         evidence={"waveform": Asset(b"synthetic response", "text")})


def evaluate(tmp_path, inputs, bindings, raw=PLAN):
    return run_evaluation(parse_evaluation(raw), inputs, bindings, tmp_path / "report")


