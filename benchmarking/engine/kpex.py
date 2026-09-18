"""SG13G2 KPEX capacitance from a candidate-bound native LVS database."""

import json
from collections import Counter
from pathlib import Path

from benchmarking.evaluation import Job
from benchmarking.files import Asset, keys, text

from .docker import DockerTool
from .evaluate import JobResult
from .hbt import parse_spice_netlist


def validate_binding(layout, database, binding, top):
    keys(binding, {"candidate_sha256", "database_sha256", "top_cell", "layers"}, set(), "LVS binding")
    if (binding["candidate_sha256"] != layout.sha256
            or binding["database_sha256"] != database.sha256
            or binding["top_cell"] != top):
        raise ValueError("LVS database is not bound to this candidate and top cell")


class SG13G2KpexCCDocker:
    """Nominal 2.5D coupling capacitance; native devices remain blackboxed.

    This explicitly does not claim distributed wire resistance. A prior native
    LVS job supplies a database with candidate geometry and its content binding.
    No source netlist is read or used to reconstruct physical devices.
    """

    wire_resistance = False

    def __init__(self, *, image: str, timeout_seconds: float = 600):
        self.tool = DockerTool(image, ["kpex", "--version"], timeout_seconds)
        self.runner = Asset(Path(__file__).with_name("kpex_runner.py").read_bytes(), "python")

    @property
    def identity(self):
        return {"adapter": "sg13g2-kpex-cc-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "runner_sha256": self.runner.sha256, "mode": "CC",
                "blackbox_devices": True, "pdk": "ihp-sg13g2"}

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        keys(inputs, {"layout", "database", "binding"}, {"task"}, "KPEX inputs")
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
        evidence = {"binding": inputs["binding"], "runner": self.runner}
        try:
            validate_binding(inputs["layout"], inputs["database"], json.loads(inputs["binding"].content), top)
        except (ValueError, TypeError, KeyError) as error:
            return JobResult("error", str(error), evidence=evidence)
        config = Asset(json.dumps({**params, "top_cell": top}).encode(), "json")
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
                raise ValueError(verdict["reason"])
            netlist = result.files["extracted.spice"]
            parsed = parse_spice_netlist(netlist.content)
            if parsed.name != top or list(parsed.ports) != ports:
                raise ValueError("KPEX output interface differs from candidate")
            if dict(Counter(d.model for d in parsed.devices)) != verdict["details"]["physical_devices"]:
                raise ValueError("KPEX lost or introduced physical devices")
            names = [d.name.casefold() for d in parsed.devices]
            if len(names) != len(set(names)):
                raise ValueError("KPEX emitted duplicate physical device names")
        except (ValueError, TypeError, KeyError) as error:
            return JobResult("error", f"Invalid KPEX result: {error}", evidence=evidence)
        return JobResult("passed", outputs={"netlist": netlist}, evidence=evidence)
