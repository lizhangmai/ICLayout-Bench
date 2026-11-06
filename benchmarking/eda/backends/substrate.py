"""Projected sheet extraction using native primitive MOS and conductor geometry."""

import json
from pathlib import Path

from benchmarking.eda.backends.klayout import KLayoutDocker
from benchmarking.evaluation.contracts import Job, JobResult
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys, relative


class SubstrateSheetDocker:
    """Explicit two-dimensional body model, independent of signal-wire RC.

    The resource owns layers, materials and native extraction options. The job
    owns the external environment. No source devices are copied into the result.
    """

    def __init__(self, *, image: str, support: str, profile: str,
                 physical_support: str, physical_profile: str,
                 timeout_seconds: float = 240):
        self.support = load_bundle(Path(support))
        self.profile = relative(profile, "substrate profile")
        self.model = json.loads(dict(self.support.files)[self.profile].content)
        self.native = KLayoutDocker(image=image, check="lvs", support=physical_support,
                                    profile=physical_profile, timeout_seconds=timeout_seconds)
        self.native.settings = {
            **self.native.settings,
            "variables": {**self.native.settings["variables"], **self.model["extraction_variables"]},
            "layer_names": {m["name"]: m["native"] for m in self.model["metals"]},
        }
        self.tool = DockerTool(image, ["python", "--version"], timeout_seconds)
        self.script = Asset(package_source("eda/_scripts/substrate.py").read_bytes(), "python")

    @property
    def identity(self):
        return {"adapter": "substrate-sheet-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "script_sha256": self.script.sha256,
                "support_sha256": self.support.manifest.sha256,
                "profile": self.profile, "native": self.native.identity,
                "model": "projected_ohmic_sheet_with_native_body_loading",
                "signal_wire_rc": False, "vertical_transport": False}

    def run(self, job, inputs):
        keys(inputs, {"layout", "netlist", "constraints"}, {"task"}, "substrate extraction inputs")
        if job.stage != "extract" or dict(job.outputs) != {"netlist": "spice"}:
            raise ValueError("Substrate extraction requires an extraction job and SPICE output")
        keys(job.parameters, {"ports", "fixture"}, {"top_cell", "subcircuit", "max_bytes"},
             "substrate extraction parameters")
        params = {k: v for k, v in job.parameters.items() if k != "fixture" and k != "ports"}
        native_job = Job(job.id, "check", "layout.lvs", (), (), (), None, json.dumps(params))
        native = self.native.run(native_job, {k: v for k, v in inputs.items() if k != "constraints"})
        evidence = {f"native/{k}": v for k, v in native.evidence.items()}
        # Uncombined source comparison is not a validity check. The evaluated
        # plan must separately gate on ordinary combined LVS. Tool errors and
        # missing native extraction remain errors, never an excuse to use source.
        if native.status == "error" or not {"report.db", "extracted.spice", "layer-map.json"} <= native.evidence.keys():
            return JobResult("error", native.reason or "Missing primitive extraction", evidence=evidence)
        config = {"model": self.model, **job.parameters}
        constraints = json.loads(inputs["constraints"].content)
        outline = next(c for c in constraints["hard"] if c["id"] == config["fixture"]["outline_constraint"])
        if outline["type"] != "bbox_max":
            raise ValueError("Projected sheet registration requires a bounding-box constraint")
        config["fixture"] = {**config["fixture"], "functional_layers": outline["functional_layers"],
                             "window_um": [outline["max_width_um"], outline["max_height_um"]]}
        if "task" in inputs:
            config["top_cell"] = json.loads(inputs["task"].content)["output"]["top_cell"]
        files = {"substrate.py": self.script, "candidate.gds": inputs["layout"],
                 "config.json": Asset(json.dumps(config).encode(), "json"),
                 "native.db": native.evidence["report.db"],
                 "native.spice": native.evidence["extracted.spice"],
                 "layers.json": native.evidence["layer-map.json"],
                 **self.support.mounted_files()}
        result = self.tool.run(["python", "substrate.py"], files,
                               {"substrate.spice": "spice", "audit.json": "json", "impedance.npz": "npz",
                                "model-check.json": "json"})
        evidence.update({**self.support.evidence(), "config": files["config.json"], "script": self.script,
                         **result.evidence, **result.files})
        cleanup_failed = any(k.endswith(("execution_error", "cleanup_error")) for k in result.evidence)
        try:
            verdict = json.loads(result.files["model-check.json"].content)
        except (KeyError, ValueError):
            return JobResult("error", "Missing or malformed projected-model verdict", evidence=evidence)
        if (not result.returncode and not cleanup_failed and verdict.get("status") == "failed" and verdict.get("reason")
                and (not result.reason or result.reason.startswith("Declared tool output is missing:"))):
            return JobResult("failed", verdict["reason"], evidence=evidence)
        if (result.returncode or result.reason or cleanup_failed or verdict.get("status") != "passed"
                or "substrate.spice" not in result.files):
            return JobResult("error", result.reason or "Substrate extraction failed", evidence=evidence)
        return JobResult("passed", outputs={"netlist": result.files["substrate.spice"]}, evidence=evidence)
