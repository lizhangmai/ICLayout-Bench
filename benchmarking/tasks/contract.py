"""Load a task configuration and materialize only its verified input files.

Loading checks configuration and content integrity. It does not qualify the
circuit/evaluator or grant access to a hidden task; those are maintainer duties.
"""

import hashlib
import json
import math
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from benchmarking.evaluation import EvaluationPlan, identifier, parse_evaluation
from benchmarking.files import Asset, is_hub_file
from benchmarking.files import keys as _keys
from benchmarking.files import read_file as _read_file
from benchmarking.files import relative as _relative
from benchmarking.files import text as _text
from benchmarking.tasks.dataset import select_core


@dataclass(frozen=True)
class InputFile:
    role: str
    path: str
    sha256: str
    content: bytes
    format: str = "text"
    derived_from: tuple[str, ...] = ()


@dataclass(frozen=True)
class LayoutOutput:
    path: str
    top_cell: str
    max_bytes: int


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    family: str
    status: str
    environment: str
    netlist_subcircuit: str
    inputs: tuple[InputFile, ...]
    output: LayoutOutput
    digest: str
    evaluation: EvaluationPlan | None = None
    inline_constraints: Asset | None = None
    witnessed: bool = False
    coefficient: int = 1
    hours: float | None = None
    evaluator_inputs: tuple[InputFile, ...] = ()

    @property
    def solver_inputs(self) -> tuple[InputFile, ...]:
        """Declared solve materials; a file evaluation plan is framework-only."""
        return tuple(item for item in self.inputs if item.role != "evaluation")

    @property
    def problem(self) -> str:
        """The original author-provided problem, without framework metadata."""
        description = next((item for item in self.inputs if item.role == "description"), None)
        if description is None:
            raise ValueError("Task must declare inputs.description before serving a solve")
        problem = description.content.decode("utf-8")
        if not problem.strip():
            raise ValueError("Task inputs.description must contain a nonempty problem")
        return problem

    @property
    def wall_seconds(self):
        if self.hours is None:
            raise ValueError("Task must explicitly declare hours before serving a solve")
        return self.hours * 3600

    def input_assets(self) -> dict[str, Asset]:
        """Frozen file and inline inputs for evaluation and evidence archival.

        Only solver_inputs are materialized as solver files; inline requirements
        are published through the task description.
        """
        inputs = {item.role: Asset(item.content, item.format)
                  for item in (*self.inputs, *self.evaluator_inputs)}
        if self.inline_constraints is not None:
            inputs["constraints"] = self.inline_constraints
        if self.evaluation is not None:
            inputs.setdefault("evaluation", Asset(self.evaluation.raw, self.evaluation.format))
        return inputs

    def evaluation_inputs(self) -> dict[str, Asset]:
        return {
            "task": Asset(json.dumps(self.description(), sort_keys=True).encode(), "json"),
            **{f"input:{role}": asset for role, asset in self.input_assets().items()},
        }

    def description(self) -> dict:
        """Trusted evaluation contract; never publish this to the solver."""
        description = {
            "id": self.id,
            "title": self.title,
            "family": self.family,
            "coefficient": self.coefficient,
            "status": self.status,
            "task_sha256": self.digest,
            "environment": self.environment,
            "netlist_subcircuit": self.netlist_subcircuit,
            "witnessed": self.witnessed,
            "input_root": "/task",
            "inputs": {item.role: f"/task/{item.path}" for item in self.inputs},
            "evaluation": self.evaluation.description() if self.evaluation else None,
            "output": {
                "path": f"/workspace/{self.output.path}",
                "format": "gds",
                "top_cell": self.output.top_cell,
                "max_bytes": self.output.max_bytes,
            },
        }
        if self.hours is not None:
            description["hours"] = self.hours
        if self.inline_constraints is not None:
            description["constraints"] = json.loads(self.inline_constraints.content)
        if self.evaluator_inputs:
            description["evaluator_inputs"] = {
                item.role: ({"derived_from": list(item.derived_from), "format": item.format}
                            if item.derived_from else Asset(item.content, item.format).identity())
                for item in self.evaluator_inputs}
        return description

    def solver_description(self) -> dict:
        """Allowlisted file, constraint and submission information for tool use.

        This is built independently of the trusted evaluation contract so new
        evaluator fields cannot accidentally become solver inputs.
        """
        description = {
            "inputs": {item.role: f"/task/{item.path}" for item in self.solver_inputs},
            "netlist_subcircuit": self.netlist_subcircuit,
            "output": {"path": f"/workspace/{self.output.path}", "format": "gds",
                       "top_cell": self.output.top_cell, "max_bytes": self.output.max_bytes},
        }
        if self.hours is not None:
            description["hours"] = self.hours
        if self.inline_constraints is not None:
            description["constraints"] = json.loads(self.inline_constraints.content)
        return description

    def materialize(self, destination: Path) -> None:
        """Publish a fresh input directory from the bytes already validated.

        The caller mounts this directory at /task, read-only. No source checkout,
        task metadata, reference solution or other neighboring file is copied.
        """
        destination = destination.absolute()
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            stage = Path(temporary) / "inputs"
            stage.mkdir()
            for item in self.solver_inputs:
                target = stage / item.path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.content)
                target.chmod(0o444)
            stage.rename(destination)


def _validate_case(data: dict) -> None:
    """Validate maintained case metadata and source attribution."""
    _keys(data, {"kind", "id", "title", "status", "origin"},
          {"role", "task", "toolchain", "assets", "qualification", "screening", "presentation", "in_core", "core_order", "distribution"}, "case")
    if data.get("distribution", "public") not in {"public", "private"}:
        raise ValueError("Case distribution must be public or private")
    if "in_core" in data and type(data["in_core"]) is not bool:
        raise ValueError("case.in_core must be boolean")
    select_core([data])
    if data["kind"] != "layout_case":
        raise ValueError("Only layout_case cases are supported")
    if "toolchain" in data and not isinstance(data["toolchain"], dict):
        raise TypeError("case.toolchain must be a table")
    for field in ("id", "title", "status"):
        _text(data[field], f"case.{field}")
    if "presentation" in data:
        _keys(data["presentation"], {"category", "summary"}, set(), "case.presentation")
        for field in ("category", "summary"):
            _text(data["presentation"][field], f"case.presentation.{field}")
    if data["status"] not in {"candidate", "qualified", "source-only", "supporting-source"}:
        raise ValueError("Case status is not recognized")
    screening = data.get("screening")
    if screening is not None:
        _keys(screening, {"decision", "reason"}, set(), "case.screening")
        if screening["decision"] not in {"include", "defer", "exclude"}:
            raise ValueError("Case screening decision is not recognized")
        _text(screening["reason"], "case.screening.reason")
    origin = data["origin"]
    _keys(origin, {"url"}, set(), "case.origin")
    _text(origin["url"], "case.origin.url")
    assets = data.get("assets", [])
    if not isinstance(assets, list):
        raise TypeError("case.assets must be an array")
    for asset in assets:
        _keys(asset, {"path", "role", "visibility", "format", "sha256"}, set(), "case.assets")
        _relative(asset["path"], "case.assets.path")
        _text(asset["role"], "case.assets.role")
        if asset["visibility"] not in {"agent", "evaluator", "maintainer"}:
            raise ValueError("case.assets.visibility is not recognized")
        _text(asset["format"], "case.assets.format")
        if not isinstance(asset["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
            raise ValueError("case.assets.sha256 must be a lowercase SHA-256")
    qualification = data.get("qualification")
    if qualification is not None:
        _keys(qualification, set(), {"reference"}, "case.qualification")
        if "reference" in qualification:
            _relative(qualification["reference"], "case.qualification.reference")


def _load_task_data(data: dict, config: Path, raw: bytes, *, label: str) -> Task:
    """Load a standalone executable task or the task section of a case."""
    config = config.absolute()
    _keys(data, {"id", "title", "kind", "family", "status",
                 "environment", "inputs", "output"},
          {"provenance", "constraints", "evaluation", "_witnessed", "coefficient", "hours", "evaluator_inputs"}, "task")
    if data["kind"] != "netlist_to_gds":
        raise ValueError("Only netlist_to_gds tasks are supported")
    if data["status"] not in {"candidate", "qualified"}:
        raise ValueError("Task status must be candidate or qualified")
    hours = data.get("hours")
    if "hours" in data and (type(hours) not in (int, float) or not math.isfinite(hours)
                            or hours <= 0 or not math.isfinite(hours * 3600)):
        raise ValueError("Task hours must be a positive finite number")
    coefficient = data.get("coefficient", 1)
    if type(coefficient) is not int or not 1 <= coefficient <= 10:
        raise ValueError("Task coefficient must be an integer from 1 through 10")
    for field in ("id", "title", "family", "environment"):
        _text(data[field], field)
    if not isinstance(data["inputs"], dict):
        raise TypeError("inputs must be a table")
    _keys(data["inputs"], {"netlist"}, set(data["inputs"]), "inputs")
    if "evaluation" in data and "evaluation" in data["inputs"]:
        raise ValueError("Declare at most one of evaluation or inputs.evaluation")
    if ("constraints" in data) == ("constraints" in data["inputs"]):
        raise ValueError("Declare exactly one of constraints or inputs.constraints")
    inline_constraints = None
    if "constraints" in data:
        if not isinstance(data["constraints"], dict):
            raise TypeError("Task constraints must be a table")
        inline_constraints = Asset(json.dumps(data["constraints"], sort_keys=True, allow_nan=False).encode(), "json")
    inputs = []
    evaluator_inputs = []
    private = data.get("evaluator_inputs", {})
    if not isinstance(private, dict):
        raise TypeError("evaluator_inputs must be a table")
    if private.keys() & (data["inputs"].keys() | {"netlist", "constraints", "evaluation"}):
        raise ValueError("Evaluator input roles must be distinct from solver and inline inputs")
    seen_paths: set[str] = set()
    declarations = [(role, entry, inputs) for role, entry in data["inputs"].items()]
    declarations.extend((role, entry, evaluator_inputs) for role, entry in private.items())
    for role, entry, destination in declarations:
        identifier(role)
        derived = entry.get("derived_from", ()) if destination is evaluator_inputs else ()
        if "derived_from" in entry and (
                destination is not evaluator_inputs or not isinstance(derived, list) or not derived
                or any(not isinstance(name, str) or name not in data["inputs"] for name in derived)
                or len(set(derived)) != len(derived)):
            raise ValueError("Derived evaluator inputs must name their authoritative solver inputs")
        required = ({"path", "derived_from"} if derived else
                    {"path", "sha256", "subcircuit"} if role == "netlist" else {"path", "sha256"})
        _keys(entry, required, {"format", "source"}, f"inputs.{role}")
        relative = _relative(entry["path"], f"inputs.{role}.path")
        source_root = config.parent
        source_relative = _relative(entry.get("source", relative), f"inputs.{role}.source")
        if any(relative == p or relative.startswith(p + "/") or p.startswith(relative + "/")
               for p in seen_paths):
            raise ValueError(f"Overlapping task input paths: {relative}")
        seen_paths.add(relative)
        content = _read_file(source_root, source_relative)
        actual = hashlib.sha256(content).hexdigest()
        digest = actual if derived else entry["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"inputs.{role}.sha256 must be a lowercase SHA-256")
        if actual != digest:
            raise ValueError(f"Task input checksum mismatch: {relative}")
        destination.append(InputFile(role, relative, digest, content,
                                     _text(entry.get("format", "text"), "input format"), tuple(derived)))
    evaluation = next((parse_evaluation(item.content) for item in inputs if item.role == "evaluation"), None)
    if "evaluation" in data:
        if not isinstance(data["evaluation"], dict):
            raise TypeError("Task evaluation must be a table")
        evaluation = parse_evaluation(
            json.dumps(data["evaluation"], sort_keys=True, allow_nan=False).encode(), file_format="json")
    if evaluation:
        available = {"candidate", "task", "input:evaluation"} | {
            f"input:{item.role}" for item in (*inputs, *evaluator_inputs)}
        if inline_constraints is not None:
            available.add("input:constraints")
        if not evaluation.external_inputs() <= available:
            raise ValueError("Evaluation references an undeclared task input")
        identities = {f"input:{item.role}": item.sha256 for item in (*inputs, *evaluator_inputs)}
        for source in evaluation.pre_layout.values():
            for role, reference in source["inputs"].items():
                if reference.startswith("input:") and identities.get(reference) != source["input_sha256"][role]:
                    raise ValueError(f"Frozen pre-layout input changed: {reference}")
    output = data["output"]
    subcircuit = _text(data["inputs"]["netlist"]["subcircuit"], "inputs.netlist.subcircuit")
    _keys(output, {"path", "format", "top_cell", "max_bytes"}, set(), "output")
    if output["format"] != "gds":
        raise ValueError("Only GDS output is supported")
    output_path = _relative(output["path"], "output.path")
    top_cell = _text(output["top_cell"], "output.top_cell")
    if type(output["max_bytes"]) is not int or output["max_bytes"] <= 0:
        raise ValueError("output.max_bytes must be a positive integer")
    if "provenance" in data:
        origin = data["provenance"]
        _keys(origin, {"path", "sha256"}, {"source"}, "provenance")
        path = _relative(origin["path"], "provenance.path")
        if path in seen_paths:
            raise ValueError("Preparation provenance must not be an Agent input")
        source = _relative(origin.get("source", path), "provenance.source")
        if hashlib.sha256(_read_file(config.parent, source)).hexdigest() != origin["sha256"]:
            raise ValueError("Preparation provenance checksum mismatch")
    return Task(
        data["id"], data["title"], data["family"], data["status"], data["environment"], subcircuit,
        tuple(inputs), LayoutOutput(output_path, top_cell, output["max_bytes"]),
        hashlib.sha256(raw).hexdigest(), evaluation, inline_constraints,
        witnessed=bool(data.get("_witnessed", False)),
        coefficient=coefficient, hours=hours, evaluator_inputs=tuple(evaluator_inputs),
    )


def load_task(config: Path) -> Task:
    """Read a standalone task or the executable section of a circuit case."""
    config = config.absolute()
    resolved = config.resolve(strict=True)
    if not config.is_file() or (resolved != config and not is_hub_file(config)):
        raise ValueError("Task configuration must be a regular, non-symlink file")
    raw = config.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    if data.get("kind") != "layout_case":
        return _load_task_data(data, config, raw, label="task")
    _validate_case(data)
    task_data = data.get("task")
    if task_data is None:
        raise ValueError(f"Case {data['id']} does not declare an executable task")
    if not isinstance(task_data, dict):
        raise TypeError("case.task must be a table")
    task_data = dict(task_data)
    task_data.update({"id": data["id"], "title": data["title"],
                      "status": data["status"],
                      "_witnessed": (data.get("qualification") or {}).get("reference") is not None})
    return _load_task_data(task_data, config, raw, label="case.task")


def contract_digest(description, inputs):
    """Compare canonical and prepared tasks without host tool paths or references."""
    value = {key: description[key] for key in
             ("id", "title", "family", "coefficient", "environment", "netlist_subcircuit", "output")}
    value["input_paths"] = description["inputs"]
    derivations = {role: spec for role, spec in description.get("evaluator_inputs", {}).items()
                   if spec.get("derived_from")}
    if derivations:
        value["evaluator_derivations"] = derivations
    value["inputs"] = {role: {key: ref[key] for key in ("sha256", "format", "bytes")}
                       for role, ref in inputs.items() if role not in derivations}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def task_contract(task):
    return contract_digest(task.description(), {role: asset.identity() for role, asset in task.input_assets().items()})
