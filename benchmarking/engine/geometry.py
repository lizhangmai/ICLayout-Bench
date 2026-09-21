"""Task-defined geometry constraints, checked against native LVS connectivity."""

import json
from pathlib import Path

from benchmarking.evaluation import identifier, number
from benchmarking.files import Asset, keys, text

from .docker import DockerTool
from .evaluate import JobResult, Measurement


def validate_constraints(data):
    keys(data, {"hard", "quality"}, set(), "geometry constraints")
    if not isinstance(data["hard"], list) or not data["hard"] or not isinstance(data["quality"], list):
        raise ValueError("Geometry constraints require hard and quality lists")
    ids, outlines = set(), set()

    def layer(value):
        if not isinstance(value, list) or len(value) != 2 or any(type(n) is not int or n < 0 for n in value):
            raise ValueError("Layer must be [nonnegative layer, datatype]")

    for spec in data["hard"]:
        name = identifier(spec.get("id"))
        if name in ids:
            raise ValueError("Duplicate constraint id")
        ids.add(name)
        if spec.get("type") == "bbox_max":
            keys(spec, {"id", "type", "functional_layers", "max_width_um", "max_height_um"}, set(), "bbox constraint")
            if not isinstance(spec["functional_layers"], list) or not spec["functional_layers"]:
                raise ValueError("Bounding box requires functional layers")
            for value in spec["functional_layers"]:
                layer(value)
            if min(number(spec["max_width_um"]), number(spec["max_height_um"])) <= 0:
                raise ValueError("Bounding box limits must be positive")
            outlines.add(name)
        elif spec.get("type") == "cell_frame":
            keys(spec, {"id", "type", "functional_layers", "height_um", "width_grid_um", "rails"}, set(), "cell frame")
            if not isinstance(spec["functional_layers"], list):
                raise ValueError("Cell frame requires functional layers")
            for value in spec["functional_layers"]:
                layer(value)
            if not spec["functional_layers"] or min(number(spec["height_um"]), number(spec["width_grid_um"])) <= 0:
                raise ValueError("Cell frame dimensions must be positive")
            if not isinstance(spec["rails"], list) or not spec["rails"]:
                raise ValueError("Cell frame needs supply rails")
            names = set()
            for rail in spec["rails"]:
                keys(rail, {"name", "layer", "connectivity_layer", "y_um", "thickness_um", "left_um", "right_um"}, set(), "supply rail")
                layer(rail["layer"])
                name = text(rail["name"], "supply name").upper()
                if name in names:
                    raise ValueError("Supply rail names must be unique")
                names.add(name)
                text(rail["connectivity_layer"], "rail connectivity layer")
                if number(rail["thickness_um"]) <= 0:
                    raise ValueError("Rail thickness must be positive")
                for key in ("y_um", "left_um", "right_um"):
                    if number(rail[key]) < 0:
                        raise ValueError("Rail offsets must be nonnegative")
        elif spec.get("type") == "named_metal_ports":
            keys(spec, {"id", "type", "names", "drawing_layer", "pin_layer", "text_layer",
                        "connectivity_layer", "min_access_square_um"}, set(), "port constraint")
            names = spec["names"]
            if not isinstance(names, list) or not names or len(set(names)) != len(names):
                raise ValueError("Port names must be a nonempty unique list")
            for value in names:
                text(value, "port name")
            text(spec["connectivity_layer"], "extracted layer name")
            for name in ("drawing_layer", "pin_layer", "text_layer"):
                layer(spec[name])
            if number(spec["min_access_square_um"]) <= 0:
                raise ValueError("Port access width must be positive")
        else:
            raise ValueError(f"Unsupported geometry constraint: {spec.get('type')}")
    for spec in data["quality"]:
        keys(spec, {"id", "type", "layers_from"}, set(), "geometry measurement")
        name = identifier(spec["id"])
        if name in ids or spec["type"] != "functional_bbox_area" or spec["layers_from"] not in outlines:
            raise ValueError("Invalid geometry measurement or duplicate id")
        ids.add(name)


class KLayoutGeometryDocker:
    def __init__(self, *, image: str, timeout_seconds: float = 60):
        self.tool = DockerTool(image, ["klayout", "-v"], timeout_seconds)
        self.scripts = {name: Asset(Path(__file__).with_name(name).read_bytes(), "python")
                        for name in ("geometry_runner.py", "klayout_runner.py")}

    @property
    def identity(self):
        return {"adapter": "klayout-geometry-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "scripts": {name: a.sha256 for name, a in self.scripts.items()}}

    def run(self, job, inputs):
        keys(inputs, {"layout", "task", "constraints", "database", "binding"}, set(), "geometry inputs")
        if job.stage != "check" or job.gate not in {None, "constraint"} or job.outputs or job.parameters:
            raise ValueError("Geometry checks take task constraints, without outputs or job parameters")
        if inputs["layout"].format != "gds" or inputs["database"].format != "klayout-lvs":
            raise ValueError("Geometry requires GDS and its native LVS database")
        if inputs["task"].format != "json" or inputs["binding"].format != "json" or inputs["constraints"].format not in {"json", "text"}:
            raise ValueError("Geometry configuration and binding must be JSON")
        data = json.loads(inputs["constraints"].content)
        validate_constraints(data)
        task = json.loads(inputs["task"].content)
        binding = json.loads(inputs["binding"].content)
        keys(binding, {"candidate_sha256", "database_sha256", "top_cell", "layers"}, set(), "LVS binding")
        if {k: v for k, v in binding.items() if k != "layers"} != {"candidate_sha256": inputs["layout"].sha256,
                       "database_sha256": inputs["database"].sha256, "top_cell": task["output"]["top_cell"]}:
            raise ValueError("LVS database binding differs from the frozen candidate")
        config = Asset(json.dumps({"top_cell": task["output"]["top_cell"],
            "max_bytes": task["output"]["max_bytes"], "subcircuit": task["netlist_subcircuit"],
            "constraints": data, "layers": binding["layers"]}).encode(), "json")
        result = self.tool.run(["python", "geometry_runner.py"], {**self.scripts,
            "config.json": config, "candidate.gds": inputs["layout"], "lvs.db": inputs["database"]},
            {"result.json": "json"})
        evidence = {**result.evidence, **result.files, **self.scripts, "configuration": config}
        if result.returncode or result.reason:
            return JobResult("error", result.reason, evidence=evidence)
        verdict = json.loads(result.files["result.json"].content)
        measurements = {name: Measurement(v["value"], v["unit"]) for name, v in verdict["measurements"].items()}
        return JobResult(verdict["status"], verdict["reason"], measurements=measurements, evidence=evidence)
