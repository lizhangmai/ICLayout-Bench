"""Frozen evaluation declarations and scalar validation."""

import hashlib
import json
import math
import re
import tomllib
from dataclasses import dataclass


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value



def number(value: object) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("Expected a finite numeric value")
    return float(value)



@dataclass(frozen=True)
class Job:
    id: str
    stage: str
    operation: str
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]
    requires: tuple[str, ...]
    gate: str | None
    parameters_json: str

    @property
    def parameters(self) -> dict:
        # Each backend receives its own copy, keeping the frozen plan immutable.
        return json.loads(self.parameters_json)



@dataclass(frozen=True)
class Metric:
    id: str
    category: str
    observations: tuple[str, ...]
    unit: str
    direction: str
    aggregation: str
    lower: float | None
    upper: float | None
    dimension: str | None = None
    baseline: tuple[str, ...] = ()
    normalization: str | None = None
    scale: float | None = None
    requirement_rationale: str | None = None
    quality_target: float | None = None
    quality_target_rationale: str | None = None

    @property
    def is_requirement(self) -> bool:
        return self.lower is not None or self.upper is not None



@dataclass(frozen=True)
class EvaluationPlan:
    mode: str
    jobs: tuple[Job, ...]
    metrics: tuple[Metric, ...]
    raw: bytes
    format: str = "toml"
    scoring: "ScoringSpec | None" = None
    pre_layout_json: str = "{}"

    @property
    def pre_layout(self) -> dict:
        return json.loads(self.pre_layout_json)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    def description(self) -> dict:
        return _decode_evaluation(self.raw, self.format)

    def external_inputs(self) -> frozenset[str]:
        references = {ref for job in self.jobs for _, ref in job.inputs
                      if ref in {"candidate", "task"} or ref.startswith("input:")}
        references.update(ref for job in self.pre_layout.values() for ref in job["inputs"].values()
                          if ref.startswith("input:"))
        return frozenset(references)



def _decode_evaluation(raw: bytes, file_format: str) -> dict:
    if file_format == "toml":
        return tomllib.loads(raw.decode("utf-8"))
    if file_format == "json":
        return json.loads(raw)
    raise ValueError("Evaluation plan format must be toml or json")



@dataclass(frozen=True)
class ScoringSpec:
    """Area reference and explicit metric weights for the task score."""

    method: str
    area_metric: str
    area_target: float
    weights: tuple[tuple[str, float], ...]
    rationale: str



SCORING_METHOD = "layout"



SCORING_DIMENSIONS = frozenset({"response", "bias", "supply"})
