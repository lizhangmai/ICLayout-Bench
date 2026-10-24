"""Verify immutable layout macros before extracting the remaining circuit."""

import json
from pathlib import Path

from benchmarking.evaluation.contracts import JobResult
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys


class FixedMacrosDocker:
    """Replace proven macro bodies with their original terminal landing shapes.

    The library and specification are declared trusted task inputs. No source
    device or missing candidate wire is inserted. Native LVS must subsequently
    check the resulting circuit, including each newly exposed macro terminal.
    """

    def __init__(self, *, image: str, timeout_seconds: float = 120):
        self.tool = DockerTool(image, ["klayout", "-v"], timeout_seconds)
        self.runner = Asset(package_source("eda/_scripts/fixed_macros_runner.py").read_bytes(), "python")

    @property
    def identity(self):
        return {"adapter": "fixed-macros-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "runner_sha256": self.runner.sha256}

    def run(self, job, inputs):
        keys(inputs, {"layout", "task", "library", "specification"}, set(), "fixed macro inputs")
        if (job.stage != "check" or job.gate not in {None, "constraint"}
                or job.parameters or dict(job.outputs) != {"layout": "gds", "binding": "json"}):
            raise ValueError("Fixed macro verification requires layout and binding outputs")
        for name, format_ in {"layout": "gds", "library": "gds", "task": "json",
                              "specification": "json"}.items():
            if inputs[name].format != format_:
                raise ValueError(f"Fixed macro {name} must be {format_}")
        task = json.loads(inputs["task"].content)
        config = Asset(json.dumps({"top_cell": task["output"]["top_cell"]}).encode(), "json")
        result = self.tool.run(["python", "run.py"], {
            "run.py": self.runner, "candidate.gds": inputs["layout"],
            "library.gds": inputs["library"], "specification.json": inputs["specification"],
            "config.json": config,
        }, {"result.json": "json", "cut.gds": "gds"})
        evidence = {**result.evidence, **result.files, "runner": self.runner, "configuration": config}
        if result.returncode or result.reason:
            return JobResult("error", result.reason or "Fixed macro verification failed", evidence=evidence)
        verdict = json.loads(result.files["result.json"].content)
        if verdict["status"] != "passed":
            return JobResult(verdict["status"], verdict["reason"], evidence=evidence)
        binding = Asset(json.dumps({"kind": "fixed-macro-abstraction-v1", "top_cell": task["output"]["top_cell"],
            "candidate_sha256": inputs["layout"].sha256,
            "library_sha256": inputs["library"].sha256,
            "specification_sha256": inputs["specification"].sha256,
            "cut_sha256": result.files["cut.gds"].sha256,
            "macros": verdict["macros"]}, sort_keys=True).encode(), "json")
        return JobResult("passed", outputs={"layout": result.files["cut.gds"], "binding": binding},
                         evidence=evidence)
