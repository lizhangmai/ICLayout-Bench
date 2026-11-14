"""KPEX coupling capacitance and distributed RC from candidate-bound geometry."""

import json
import math
import re
from collections import Counter
from pathlib import Path

from benchmarking.eda.layout_derivation import validate_layout_derivation
from benchmarking.eda.netlists.dspf import bind_ports
from benchmarking.eda.netlists.spice import logical_lines, tokens
from benchmarking.evaluation.contracts import Job, JobResult
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys, relative, text


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

    A prior native LVS job supplies a database with candidate geometry and its content binding.
    No source netlist is read or used to reconstruct physical devices.
    """

    wire_resistance = False
    mode = "CC"

    def __init__(self, *, image: str, support: str | None = None, profile: str | None = None,
                 pdk: str | None = None, deck: str | None = None, technology: str | None = None,
                 variables: dict | None = None, top_cell_variable: str = "topcell",
                 substrate_node: str = "VSUBS", substrate_variable: str | None = None,
                 timeout_seconds: float = 600):
        managed = any(value is not None for value in (pdk, deck, technology))
        if managed and (support is None or profile is not None or
                        any(value is None for value in (pdk, deck, technology))):
            raise ValueError("KPEX native resources require support, pdk, deck and technology together")
        if not managed and (support is None) != (profile is None):
            raise ValueError("KPEX legacy support and profile must be supplied together")
        self.support = load_bundle(Path(support)) if support is not None else None
        self.managed = managed
        if managed:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', pdk):
                raise ValueError("Invalid KPEX process name")
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top_cell_variable):
                raise ValueError("Invalid KPEX top-cell variable")
            if substrate_variable is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', substrate_variable):
                raise ValueError("Invalid KPEX substrate variable")
            self.process = {"pdk": pdk, "deck": relative(deck, "KPEX deck"),
                            "technology": relative(technology, "KPEX technology"),
                            "variables": dict(variables or {}), "top_cell_variable": top_cell_variable,
                            "substrate_node": text(substrate_node, "KPEX substrate node"),
                            "substrate_variable": substrate_variable}
            reserved = {"input", "topcell", "top_cell", "schematic", "report", "target_netlist",
                        top_cell_variable, substrate_variable}
            if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) or k in reserved or
                   not isinstance(v, str) or '\n' in v for k, v in self.process["variables"].items()):
                raise ValueError("Invalid KPEX runset variables")
        else:
            self.process = json.loads(dict(self.support.files)[profile].content) if self.support else None
        if self.process is not None and not managed:
            validate_process(self.process)
        self.tool = DockerTool(image, ["kpex", "--version"], timeout_seconds)
        self.runner = Asset(package_source("eda/_scripts/kpex_runner.py").read_bytes(), "python")

    @property
    def identity(self):
        return {"adapter": "kpex-rc-docker" if self.wire_resistance else "kpex-cc-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "runner_sha256": self.runner.sha256, "mode": self.mode,
                "layout_derivation_sha256": Asset(package_source("eda/layout_derivation.py").read_bytes(), "python").sha256,
                "blackbox_devices": True, "process": self.process,
                "support_sha256": self.support.manifest.sha256 if self.support else None}

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        keys(inputs, {"layout", "database", "binding"},
             {"task", "original", "derivation", "process"}, "KPEX inputs")
        process = self.process
        if "process" in inputs:
            if process is not None:
                raise ValueError("KPEX process input cannot be combined with a legacy profile")
            if inputs["process"].format != "json":
                raise ValueError("KPEX process input must be JSON")
            process = json.loads(inputs["process"].content)
        if process is None:
            raise ValueError("KPEX requires an explicit process input or a legacy profile")
        if not self.managed:
            validate_process(process)
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
            **({"process": inputs["process"]} if "process" in inputs else {})}
        try:
            validate_binding(inputs["layout"], inputs["database"], json.loads(inputs["binding"].content), top)
        except (ValueError, TypeError, KeyError) as error:
            return JobResult("error", str(error), evidence=evidence)
        config = Asset(json.dumps({**params, "top_cell": top, "process": process,
                                  "mode": self.mode, "native_resources": self.managed}).encode(), "json")
        result = self.tool.run(["python", "run.py"], {
            "candidate.lvsdb": inputs["database"], "candidate.gds": inputs["layout"],
            "run.py": self.runner, "config.json": config,
            **(self.support.mounted_files() if self.support else {}),
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
            devices = verdict["details"]["model_interfaces"] if self.managed else process['devices']
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
                    if model not in devices:
                        raise ValueError("KPEX emitted an undeclared physical model")
                    if len(values) != len(devices[model]['terminals']) + 1:
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
        return JobResult("passed", outputs={"netlist": netlist}, evidence=evidence)


class KpexRCDocker(KpexCCDocker):
    """Native 2.5D distributed wire/via resistance and coupling capacitance."""

    mode = "RC"
    wire_resistance = True

    def __init__(self, **settings):
        super().__init__(**settings)
        if not self.managed:
            raise ValueError("KPEX RC requires explicitly managed native resources")


class KpexNetgenDocker(KpexCCDocker):
    """Extract native KPEX devices and compare their model calls with Netgen."""

    def __init__(self, *, netgen_support: str, setup: str, **settings):
        super().__init__(**settings)
        if not self.managed:
            raise ValueError("KPEX/Netgen LVS requires explicitly managed native resources")
        self.netgen_support = load_bundle(Path(netgen_support))
        self.setup = relative(setup, "Netgen setup")
        if self.setup not in dict(self.netgen_support.files):
            raise ValueError("Netgen setup is missing from its support bundle")
        self.netgen = DockerTool(settings["image"], ["netgen", "-batch", "quit"],
                                 settings.get("timeout_seconds", 600))

    @property
    def identity(self):
        return {**super().identity, "adapter": "kpex-netgen-docker", "netgen": self.netgen.identity,
                "netgen_support_sha256": self.netgen_support.manifest.sha256, "setup": self.setup}

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        from benchmarking.eda.backends.magic import _tcl_word
        from benchmarking.eda.backends.magic_checks import netgen_verdict

        keys(inputs, {"layout", "netlist"}, {"task"}, "KPEX/Netgen LVS inputs")
        keys(job.parameters, {"substrate"}, {"top_cell", "subcircuit"}, "KPEX/Netgen LVS parameters")
        if (job.stage != "check" or job.gate not in {None, "lvs"}
                or dict(job.outputs) != {"database": "klayout-lvs", "binding": "json"}
                or inputs["layout"].format != "gds" or inputs["netlist"].format != "spice"):
            raise ValueError("KPEX/Netgen LVS requires GDS, source SPICE and database/binding outputs")
        params = dict(job.parameters)
        if "task" in inputs:
            task = json.loads(inputs["task"].content)
            for key, value in {"top_cell": task["output"]["top_cell"],
                               "subcircuit": task["netlist_subcircuit"]}.items():
                if key in params and params[key] != value:
                    raise ValueError(f"LVS {key} differs from task")
                params[key] = value
        top, subcircuit = text(params.get("top_cell"), "top cell"), text(params.get("subcircuit"), "subcircuit")
        config = Asset(json.dumps({**params, "process": self.process, "devices_only": True}).encode(), "json")
        extraction = self.tool.run(["python", "run.py"], {
            "candidate.gds": inputs["layout"], "run.py": self.runner, "config.json": config,
            **self.support.mounted_files(),
        }, {"extracted.spice": "spice", "geometry.lvsdb": "klayout-lvs",
            "geometry.log": "text", "result.json": "json"})
        evidence = {**self.support.evidence(), **extraction.evidence, **extraction.files,
                    "runner": self.runner, "configuration": config}
        if extraction.reason or extraction.returncode:
            return JobResult("error", extraction.reason or "Native device extraction failed", evidence=evidence)
        try:
            verdict = json.loads(extraction.files["result.json"].content)
            if verdict["status"] != "passed":
                return JobResult("error", verdict["reason"], evidence=evidence)
            script = ('if {[catch {\n'
                      f'lvs [list extracted.spice {_tcl_word(top)}] '
                      f'[list source.spice {_tcl_word(subcircuit)}] '
                      f'{_tcl_word("/workspace/support/" + self.setup)} comparison.out -json\n'
                      'set f [open complete.txt w]; puts $f complete; close $f\n'
                      '} message]} {puts stderr $message; exit 2}\nquit\n')
            comparison = self.netgen.run(["netgen", "-batch", "source", "compare.tcl"], {
                "extracted.spice": extraction.files["extracted.spice"], "source.spice": inputs["netlist"],
                "compare.tcl": Asset(script.encode(), "tcl"), **self.netgen_support.mounted_files(),
            }, {"comparison.json": "json", "comparison.out": "text", "complete.txt": "text"})
            evidence.update({f"netgen:{k}": v for k, v in (comparison.evidence | comparison.files).items()})
            if comparison.reason or comparison.returncode:
                return JobResult("error", comparison.reason or "Netgen did not complete", evidence=evidence)
            if comparison.files["complete.txt"].content.strip() != b"complete":
                raise ValueError("Incomplete Netgen comparison")
            if not netgen_verdict(json.loads(comparison.files["comparison.json"].content), top, subcircuit):
                return JobResult("failed", "Netgen LVS mismatch", evidence=evidence)
            database = extraction.files["geometry.lvsdb"]
            binding = Asset(json.dumps({"candidate_sha256": inputs["layout"].sha256,
                "database_sha256": database.sha256, "top_cell": top, "layers": {}}).encode(), "json")
            return JobResult("passed", outputs={"database": database, "binding": binding}, evidence=evidence)
        except (ValueError, TypeError, KeyError) as error:
            return JobResult("error", f"Invalid LVS result: {error}", evidence=evidence)
