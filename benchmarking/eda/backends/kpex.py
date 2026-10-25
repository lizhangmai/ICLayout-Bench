"""KPEX capacitance from a candidate-bound native LVS database."""

import json
import math
import re
from collections import Counter
from pathlib import Path

from benchmarking.eda.layout_derivation import (
    validate_derived_model,
    validate_layout_derivation,
)
from benchmarking.eda.netlists.dspf import bind_ports
from benchmarking.eda.netlists.spice import logical_lines, tokens
from benchmarking.evaluation.contracts import Job, JobResult
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys, text


def validate_process(process):
    """Validate a frozen process interface; no candidate repair/default rules."""
    keys(process, {"pdk", "deck", "variables", "substrate_node", "devices"}, set(), "KPEX process")
    identifier = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
    def name(value):
        return isinstance(value, str) and identifier.fullmatch(value)
    deck = process["deck"]
    if (not isinstance(process["pdk"], str) or not name(process["pdk"].replace('-', '_'))
            or not name(process["substrate_node"])
            or not isinstance(deck, str) or Path(deck).is_absolute()
            or '..' in Path(deck).parts or not deck.endswith('.lvs')):
        raise ValueError("Invalid KPEX process identity or deck")
    reserved = {"input", "topcell", "schematic", "report", "target_netlist"}
    if not isinstance(process["variables"], dict) or any(
            not name(k) or k in reserved or not isinstance(v, str) or '\n' in v
            for k, v in process["variables"].items()):
        raise ValueError("Invalid KPEX runset variables")
    if not isinstance(process["devices"], dict) or not process["devices"]:
        raise ValueError("KPEX process needs device interfaces")
    for model, device in process["devices"].items():
        if not name(model) or model != model.lower():
            raise ValueError("Invalid KPEX model name")
        keys(device, {"terminals", "parameters", "reference_prefix"},
             {"reference_parameters", "required_values"}, "KPEX device")
        terminals = device["terminals"]
        if (not isinstance(terminals, list) or not terminals or any(not name(t) for t in terminals)
                or len(set(terminals)) != len(terminals) or device["reference_prefix"] not in {"Q", "R", "C", "M", "X"}):
            raise ValueError("Invalid KPEX terminal interface")
        for mapping in (device["parameters"], device.get("reference_parameters", {})):
            if not isinstance(mapping, dict) or any(not name(k) or v not in {"", "u", "n", "p", "f", "m", "k", "meg"}
                                                    for k, v in mapping.items()):
                raise ValueError("Invalid KPEX parameter units")
        requirements = device.get("required_values", {})
        if not isinstance(requirements, dict):
            raise TypeError("Invalid KPEX parameter constraints")
        for parameter, rule in requirements.items():
            keys(rule, {"value"}, {"relative_tolerance"}, "KPEX constraint")
            if not name(parameter) or any(type(v) not in {float, int} or not math.isfinite(v) for v in rule.values()) or rule.get("relative_tolerance", 0) < 0:
                raise ValueError("Invalid KPEX parameter constraint")


def validate_binding(layout, database, binding, top):
    keys(binding, {"candidate_sha256", "database_sha256", "top_cell", "layers"}, set(), "LVS binding")
    if (binding["candidate_sha256"] != layout.sha256
            or binding["database_sha256"] != database.sha256
            or binding["top_cell"] != top):
        raise ValueError("LVS database is not bound to this candidate and top cell")


class KpexCCDocker:
    """Nominal 2.5D coupling capacitance; native devices remain blackboxed.

    This explicitly does not claim distributed wire resistance. A prior native
    LVS job supplies a database with candidate geometry and its content binding.
    No source netlist is read or used to reconstruct physical devices.
    """

    wire_resistance = False

    def __init__(self, *, image: str, support: str, profile: str, timeout_seconds: float = 600):
        self.support = load_bundle(Path(support))
        self.process = json.loads(dict(self.support.files)[profile].content)
        validate_process(self.process)
        self.tool = DockerTool(image, ["kpex", "--version"], timeout_seconds)
        self.runner = Asset(package_source("eda/_scripts/kpex_runner.py").read_bytes(), "python")

    @property
    def identity(self):
        return {"adapter": "kpex-cc-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "runner_sha256": self.runner.sha256, "mode": "CC",
                "layout_derivation_sha256": Asset(package_source("eda/layout_derivation.py").read_bytes(), "python").sha256,
                "blackbox_devices": True, "process": self.process,
                "support_sha256": self.support.manifest.sha256}

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        keys(inputs, {"layout", "database", "binding"}, {"task", "original", "derivation", "model"}, "KPEX inputs")
        derivation = validate_layout_derivation({**{key: value for key, value in inputs.items()
                                                    if key in {"layout", "task", "original"}},
            **({"binding": inputs["derivation"]} if "derivation" in inputs else {})})
        if (job.stage != "extract" or dict(job.outputs) != {"netlist": "spice"}
                or inputs["layout"].format != "gds" or inputs["database"].format != "klayout-lvs"
                or inputs["binding"].format != "json"):
            raise ValueError("KPEX requires GDS, native LVS database and JSON binding")
        params = job.parameters
        keys(params, {"ports", "substrate"}, {"top_cell"}, "KPEX parameters")
        top = params.get("top_cell")
        if "task" in inputs:
            configured = json.loads(inputs["task"].content)["output"]["top_cell"]
            if top is not None and top != configured:
                raise ValueError("KPEX top cell differs from task")
            top = configured
        top = text(top, "top cell")
        ports = params["ports"]
        if (not isinstance(ports, list) or not ports or any(not isinstance(p, str) or not p for p in ports)
                or len({p.casefold() for p in ports}) != len(ports) or params["substrate"] not in ports):
            raise ValueError("KPEX requires unique ports and a declared substrate port")
        evidence = {"binding": inputs["binding"], "runner": self.runner, **derivation,
            **validate_derived_model(inputs.get("derivation"), inputs.get("model"))}
        try:
            validate_binding(inputs["layout"], inputs["database"], json.loads(inputs["binding"].content), top)
        except (ValueError, TypeError, KeyError) as error:
            return JobResult("error", str(error), evidence=evidence)
        config = Asset(json.dumps({**params, "top_cell": top, "process": self.process}).encode(), "json")
        result = self.tool.run(["python", "run.py"], {
            "candidate.lvsdb": inputs["database"], "candidate.gds": inputs["layout"],
            "run.py": self.runner, "config.json": config,
        }, {"extracted.spice": "spice", "result.json": "json",
            "geometry.lvsdb": "klayout-lvs", "geometry.log": "text",
            "candidate-reference.spice": "spice", "kpex-native.spice": "spice"})
        evidence.update({**result.evidence, **result.files, "configuration": config})
        if result.reason or result.returncode:
            return JobResult("error", result.reason or "KPEX execution failed", evidence=evidence)
        try:
            verdict = json.loads(result.files["result.json"].content)
            if verdict["status"] != "passed":
                status = "failed" if verdict["status"] == "failed" else "error"
                return JobResult(status, verdict["reason"], evidence=evidence)
            netlist = result.files["extracted.spice"]
            if bind_ports(netlist.content.decode(), top, ports) != netlist.content.decode():
                raise ValueError("KPEX output interface differs from candidate")
            models, names = [], []
            for row in logical_lines(netlist.content):
                fields = tokens(row)
                if not fields or fields[0].startswith('.'):
                    continue
                names.append(fields[0].casefold())
                if fields[0][0].lower() == 'x':
                    values = [f for f in fields[1:] if '=' not in f]
                    if not values:
                        raise ValueError("KPEX emitted an incomplete device")
                    model = values[-1].lower()
                    if model not in self.process['devices']:
                        raise ValueError("KPEX emitted an undeclared physical model")
                    if len(values) != len(self.process['devices'][model]['terminals']) + 1:
                        raise ValueError("KPEX device terminals differ from its declared interface")
                    models.append(model)
                elif fields[0][0].lower() not in {'r', 'c'}:
                    raise ValueError("KPEX emitted an unsupported element")
            if dict(Counter(models)) != verdict["details"]["physical_devices"]:
                raise ValueError("KPEX lost or introduced physical devices")
            if len(names) != len(set(names)):
                raise ValueError("KPEX emitted duplicate physical device names")
        except (ValueError, TypeError, KeyError) as error:
            return JobResult("error", f"Invalid KPEX result: {error}", evidence=evidence)
        if "model" in inputs:
            netlist = Asset(netlist.content + b"\n" + inputs["model"].content, "spice")
        return JobResult("passed", outputs={"netlist": netlist}, evidence=evidence)
