"""Candidate uniform-line geometry to a declared calibrated RLC interface."""

import json
from pathlib import Path

from benchmarking.eda._scripts.rlc_line_runner import (
    render_line_netlist,
    validate_process,
)
from benchmarking.eda.layout_derivation import validate_layout_derivation
from benchmarking.evaluation.contracts import JobResult
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys

__all__ = ["RLCLineDocker", "render_line_netlist"]


class RLCLineDocker:
    """An explicit restricted geometry/model boundary, with no candidate repair."""

    def __init__(self, *, image, support, profile, timeout_seconds=120):
        self.support = load_bundle(Path(support))
        self.process_asset = Asset(dict(self.support.files)[profile].content, "json")
        self.process = json.loads(self.process_asset.content)
        validate_process(self.process)
        self.tool = DockerTool(image, ["klayout", "-v"], timeout_seconds)
        self.runner = Asset(package_source("eda/_scripts/rlc_line_runner.py").read_bytes(), "python")

    @property
    def identity(self):
        return {"adapter": "rlc-line-docker", **self.tool.identity,
            "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
            "runner_sha256": self.runner.sha256,
            "layout_derivation_sha256": Asset(package_source("eda/layout_derivation.py").read_bytes(), "python").sha256,
            "process_sha256": self.process_asset.sha256,
            "support_sha256": self.support.manifest.sha256, "mode": "calibrated-uniform-RLC"}

    def run(self, job, inputs):
        keys(inputs, {"layout", "original", "binding", "task", "specification"}, set(), "RLC line inputs")
        if (job.stage != "check" or job.gate is not None or job.parameters
                or dict(job.outputs) != {"layout": "gds", "binding": "json", "netlist": "spice"}):
            raise ValueError("RLC line verification requires layout, binding and model outputs")
        for key, format_ in {"layout": "gds", "original": "gds", "binding": "json",
                             "task": "json", "specification": "json"}.items():
            if inputs[key].format != format_:
                raise ValueError("Invalid RLC line input format: " + key)
        derivation = validate_layout_derivation(inputs)
        top = json.loads(inputs["task"].content)["output"]["top_cell"]
        result = self.tool.run(["python", "run.py"], {"run.py": self.runner,
            "candidate.gds": inputs["layout"], "specification.json": inputs["specification"],
            "original.gds": inputs["original"],
            "process.json": self.process_asset,
            "config.json": Asset(json.dumps({"top_cell": top}).encode(), "json")},
            {"cut.gds": "gds", "line.spice": "spice", "result.json": "json"})
        evidence = {**derivation, **result.evidence, **result.files,
            "runner": self.runner, "process": self.process_asset, "specification": inputs["specification"]}
        if result.reason or result.returncode:
            return JobResult("error", result.reason or "Candidate line extraction failed", evidence=evidence)
        verdict = json.loads(result.files["result.json"].content)
        if verdict["status"] != "passed":
            return JobResult("failed", verdict["reason"], evidence=evidence)
        specification = json.loads(inputs["specification"].content)
        expected = render_line_netlist(self.process, verdict["line"]["length_um"], specification["subcircuit"])
        if result.files["line.spice"].content.decode() != expected:
            return JobResult("error", "Native line output differs from declared passive model", evidence=evidence)
        binding = Asset(json.dumps({"kind": "uniform-line-abstraction-v1", "top_cell": top,
            "candidate_sha256": inputs["original"].sha256, "cut_sha256": result.files["cut.gds"].sha256,
            "process_sha256": self.process_asset.sha256,
            "specification_sha256": inputs["specification"].sha256,
            "parent_binding_sha256": inputs["binding"].sha256,
            "netlist_sha256": result.files["line.spice"].sha256,
            "line": verdict["line"]}, sort_keys=True).encode(), "json")
        return JobResult("passed", outputs={"layout": result.files["cut.gds"],
            "binding": binding, "netlist": result.files["line.spice"]}, evidence=evidence)
