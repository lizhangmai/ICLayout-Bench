"""Native RC extraction with a separately declared external layout fixture."""

import json
import re
from dataclasses import replace
from pathlib import Path

from benchmarking.eda.backends.magic import MagicRCDocker
from benchmarking.evaluation.contracts import JobResult
from benchmarking.evidence.identity import package_source
from benchmarking.files import Asset, keys


class MagicFixtureRCDocker(MagicRCDocker):
    def __init__(self, **settings):
        super().__init__(**{**settings, "resistance_net_selection": "canonical"})

    @property
    def identity(self):
        return {**super().identity, "adapter": "magic-fixture-rc-docker",
                "fixture_adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "fixture_preparation_sha256": Asset(package_source("eda/_scripts/gds_fixture.py").read_bytes(), "python").sha256}

    def run(self, job, inputs):
        if set(inputs) != {"layout", "fixture", "constraints"} or any(
                inputs[n].format != f for n, f in [("layout", "gds"), ("fixture", "gds"), ("constraints", "json")]):
            raise ValueError("External RC fixture requires candidate/fixture GDS and constraints JSON")
        parameters = dict(job.parameters)
        keys(parameters, {"top_cell", "ports", "fixture_top", "fixture_ports", "fixture_nets", "outline_constraint", "fixture_flag"},
             {"excluded_layers"}, "external RC fixture")
        ports, added, flag = parameters["ports"], parameters["fixture_ports"], parameters["fixture_flag"]
        nets = parameters["fixture_nets"]
        if (not isinstance(ports, list) or not isinstance(added, list) or not added
                or len(set(ports + added)) != len(ports + added)
                or not isinstance(nets, list) or len(nets) != len(added)
                or any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) for n in ports + added + nets)
                or not isinstance(flag, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", flag)):
            raise ValueError("Invalid external RC fixture interface")
        source = Asset(package_source("eda/_scripts/gds_fixture.py").read_bytes(), "python")
        extracted_top = "LB_EXTERNAL_EXTRACTED"
        if parameters["top_cell"].casefold() == extracted_top.casefold():
            raise ValueError("Candidate top collides with the external extraction top")
        prepared = self.tool.run(["python", "gds_fixture.py"],
                                 {"candidate.gds": inputs["layout"], "fixture.gds": inputs["fixture"],
                                  "constraints.json": inputs["constraints"], "gds_fixture.py": source,
                                  "fixture.json": Asset(json.dumps({**parameters, "extracted_top": extracted_top}).encode(), "json")},
                                 {"combined.gds": "gds", "result.json": "json"})
        evidence = {"fixture_source.gds": inputs["fixture"], "fixture_preparation_script": source,
                    **{f"fixture_preparation/{k}": a for k, a in {**prepared.evidence, **prepared.files}.items()}}
        if prepared.returncode or prepared.reason and "result.json" not in prepared.files:
            return JobResult("error", prepared.reason or "External fixture preparation failed", evidence=evidence)
        try:
            verdict = json.loads(prepared.files["result.json"].content)
            if verdict["status"] != "passed":
                return JobResult(verdict["status"], verdict["reason"], evidence=evidence)
            if prepared.reason:
                return JobResult("error", prepared.reason, evidence=evidence)
            combined = prepared.files["combined.gds"]
        except (KeyError, ValueError) as error:
            return JobResult("error", f"Invalid fixture preparation: {error}", evidence=evidence)
        native = super().run(replace(job, parameters_json=json.dumps({"top_cell": extracted_top, "ports": ports + added})),
                             {"layout": combined})
        evidence.update(native.evidence)
        if native.status != "passed":
            return replace(native, evidence=evidence)
        raw = native.outputs["netlist"].content
        if re.search(rb"(?im)^\s*\.end\s*$", raw) or flag.encode().lower() in raw.lower():
            return JobResult("error", "Native netlist conflicts with external fixture flag", evidence=evidence)
        wrapper = Asset((f'\n.subckt {parameters["top_cell"]} {" ".join(ports)}\n'
                         f'Xexternal {" ".join(ports + nets)} {extracted_top}\n'
                         f'.ends {parameters["top_cell"]}\n.param {flag}=1\n').encode(), "spice")
        evidence["fixture_port_wrapper.spice"] = wrapper
        return JobResult("passed", outputs={"netlist": Asset(raw + wrapper.content, "spice")},
                         evidence=evidence)
