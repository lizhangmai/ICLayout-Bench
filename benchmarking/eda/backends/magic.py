"""Magic parasitic extraction with caller-selected technology and pin order."""

import json
import re
from pathlib import Path

from benchmarking.evaluation.contracts import Job, JobResult
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.diagnostics import native_failure
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys, number, relative, text


def _tcl_word(value: str) -> str:
    value = text(value, "Tcl argument")
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("[", "\\["), ("]", "\\]"),
                     ("\n", "\\n"), ("\r", "\\r")):
        value = value.replace(old, new)
    return '"' + value + '"'


def _model_binding(support, technology):
    """Select a native model interface for Magic's SI extraction output."""
    if support is None and technology is None:
        return {}, {}
    if support is None or technology is None:
        raise ValueError('Magic model support and technology must be supplied together')
    bundle = load_bundle(Path(support))
    technology = relative(technology, 'model technology')
    if technology not in dict(bundle.files):
        raise ValueError('Model technology is missing from its support bundle')
    runner = Asset(package_source('eda/_scripts/magic_models.py').read_bytes(), 'python')
    files = {f'model_support/{name}': asset for name, asset in bundle.files}
    files.update({'magic_models.py': runner, 'model-interface.json': Asset(json.dumps({
        'technology': 'model_support/' + technology}).encode(), 'json')})
    identity = {'model_support_sha256': bundle.manifest.sha256, 'model_technology': technology,
                'model_interface_sha256': runner.sha256}
    return files, identity


def _ignore_gds_layers(technology: bytes, layers: list[list[int]]) -> Asset:
    """Apply explicit input-layer exclusions with native CIF/GDS ignore rules."""
    source = technology.decode()
    section = re.search(r'(?ms)^[ \t]*cifinput[ \t]*\r?\n(.*?)^[ \t]*end[ \t]*\r?$', source)
    if section is None:
        raise ValueError("GDS ignore layers require an inline cifinput section")
    body = section[1]
    if re.search(r'(?m)^[ \t]*include\s', body):
        raise ValueError("GDS ignore layers require inline cifinput styles")
    name = "ICLAYOUT_IGNORED"
    if re.search(r'\b' + name + r'\b', source):
        raise ValueError("Reserved Magic input layer: " + name)
    by_type = {}
    for layer, datatype in layers:
        by_type.setdefault(datatype, []).append(layer)
    rules = f'\n  ignore {name}\n' + ''.join(
        f'  calma {name} {",".join(map(str, sorted(numbers)))} {datatype}\n'
        for datatype, numbers in sorted(by_type.items()))
    # Append to every style so the declarations also apply after cif istyle.
    styles = list(re.finditer(r'(?m)^[ \t]*style\s+[^\n]*', body))
    positions = [style.start() for style in styles[1:]] + [len(body)]
    if styles and any(line.split('#', 1)[0].strip() for line in body[:styles[0].start()].splitlines()):
        positions.insert(0, styles[0].start())
    for position in reversed(positions):
        body = body[:position] + rules + body[position:]
    return Asset((source[:section.start(1)] + body + source[section.end(1):]).encode(), "text")


class MagicCapacitanceDocker:
    """Extract devices and coupled capacitances; wire resistance is not included.

    This adapter does not certify DRC or LVS. The evaluated plan must require
    independent validity gates before extraction can count toward task success.
    """

    wire_resistance = False

    def __init__(self, *, image: str, support: str, technology: str, tech_name: str,
                 style: str, capacitance_threshold_ff: float = 0, timeout_seconds: float = 60,
                 gds_readonly: bool = True, label_layers: list[list[int]] | None = None,
                 case_insensitive_ports: bool = False, grid_subdivision: int = 1,
                 resistance_net_selection: str = "all", gds_ignore_layers: list[list[int]] | None = None,
                 model_support: str | None = None, model_technology: str | None = None):
        if resistance_net_selection not in {"all", "canonical"} or (
                not self.wire_resistance and resistance_net_selection != "all"):
            raise ValueError("Invalid Magic resistance net selection")
        self.resistance_net_selection = resistance_net_selection
        if type(grid_subdivision) is not int or grid_subdivision < 1:
            raise ValueError("Magic grid subdivision must be a positive integer")
        self.grid_subdivision = grid_subdivision
        if type(gds_readonly) is not bool:
            raise TypeError("gds_readonly must be a boolean")
        self.gds_readonly = gds_readonly
        if type(case_insensitive_ports) is not bool:
            raise TypeError("case_insensitive_ports must be a boolean")
        self.case_insensitive_ports = case_insensitive_ports
        if label_layers is not None and (not isinstance(label_layers, list) or not label_layers
                or any(not isinstance(pair, list) or len(pair) != 2
                       or any(type(n) is not int or not 0 <= n <= 65535 for n in pair)
                       for pair in label_layers)):
            raise ValueError("label_layers must contain GDS layer/datatype pairs")
        self.label_layers = label_layers
        if gds_ignore_layers is not None and (not isinstance(gds_ignore_layers, list)
                or any(not isinstance(pair, list) or len(pair) != 2
                       or any(type(n) is not int or not 0 <= n <= 65535 for n in pair)
                       for pair in gds_ignore_layers)
                or len({tuple(pair) for pair in gds_ignore_layers}) != len(gds_ignore_layers)):
            raise ValueError("gds_ignore_layers must contain unique GDS layer/datatype pairs")
        self.gds_ignore_layers = sorted(gds_ignore_layers or [])
        self.support = load_bundle(Path(support))
        self.technology = relative(technology, "Magic technology")
        if self.technology not in dict(self.support.files):
            raise ValueError("Magic technology is missing from the support bundle")
        self.import_technology = (_ignore_gds_layers(dict(self.support.files)[self.technology].content,
                                                   self.gds_ignore_layers)
                                  if self.gds_ignore_layers else None)
        self.tech_name, self.style = text(tech_name, "technology name"), text(style, "extract style")
        self.model_files, self.model_identity = _model_binding(model_support, model_technology)
        self.threshold = number(capacitance_threshold_ff)
        if self.threshold < 0:
            raise ValueError("Capacitance threshold cannot be negative")
        self.tool = DockerTool(image, ["magic", "--version"], timeout_seconds)

    @property
    def identity(self) -> dict:
        return {"adapter": "magic-rc-docker" if self.wire_resistance else "magic-capacitance-docker", **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "port_alias_sha256": Asset(package_source("eda/_scripts/magic_ports.py").read_bytes(), "python").sha256,
                "interface_check_sha256": Asset(package_source("eda/_scripts/magic_netlist.py").read_bytes(), "python").sha256,
                "support_sha256": self.support.manifest.sha256, "technology": self.technology,
                "tech_name": self.tech_name, "extract_style": self.style,
                "parasitics": "distributed_rc" if self.wire_resistance else "coupled_capacitance",
                "wire_resistance": self.wire_resistance,
                "capacitance_threshold_ff": self.threshold,
                "gds_readonly": self.gds_readonly,
                "gds_ignore_layers": self.gds_ignore_layers,
                "label_layers": self.label_layers,
                "case_insensitive_ports": self.case_insensitive_ports,
                "grid_subdivision": self.grid_subdivision,
                **self.model_identity,
                **({"flatten": True, "resistance_threshold_mohm": 0, "minimum_resistance_mohm": 0,
                    "minimum_delay_ps": 0, "simplify_resistance": False, "merge_devices": "none",
                    "same_conductor_ports": "native_canonical" if self.resistance_net_selection == "canonical" else "rejected",
                    "resistance_net_selection": self.resistance_net_selection}
                   if self.wire_resistance else {})}

    def _check_diagnostics(self, log: str, files: dict[str, Asset]) -> tuple[str, str, dict[str, Asset]]:
        """Reject unreliable extraction; composite adapters may review native evidence."""
        # CIFrdcl.c reports an overwritten FIXED_BBOX through CalmaReadError.
        # Flat standard-cell ID regions can set this non-electrical abutment
        # property more than once. Keep the warning in evidence; it does not
        # indicate missing geometry or a failed electrical extraction.
        log = re.sub(
            r'^Error while reading cell "[^"\n]+" \(byte position \d+\): '
            r'Warning:  Cell [^\n]+ boundary was redefined\.\s*$',
            '', log, flags=re.MULTILINE,
        )
        rejected = [line for line in log.splitlines()
                    if re.search(r"missing (?:gate|substrate|source|drain) connection|orphaned node", line, re.IGNORECASE)]
        remaining = "\n".join(line for line in log.splitlines() if line not in rejected)
        if re.search(r"\berrors?\b|unrecognized|unknown layer|unmapped|not found|couldn't|cannot|"
                     r"extraction style .* ambiguous", remaining, re.IGNORECASE):
            return "error", "Magic reported an extraction or input error", {}
        if rejected:
            return "failed", "Magic reported an unusable candidate extraction", {}
        return "passed", "", {}

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        if job.stage != "extract" or set(inputs) - {"layout", "task"} or "layout" not in inputs:
            raise ValueError("Magic extraction requires layout and optional task inputs")
        if inputs["layout"].format != "gds" or dict(job.outputs) != {"netlist": "spice"}:
            raise ValueError("Magic extraction requires GDS and a declared SPICE netlist output")
        params = job.parameters
        keys(params, {"ports"}, {"top_cell"}, "Magic extraction parameters")
        top = params.get("top_cell")
        if "task" in inputs:
            if inputs["task"].format != "json":
                raise ValueError("Task description must be JSON")
            configured = json.loads(inputs["task"].content)["output"]["top_cell"]
            if top is not None and top != configured:
                raise ValueError("Extraction top cell differs from task configuration")
            top = configured
        top = text(top, "top cell")
        ports = params["ports"]
        if not isinstance(ports, list) or not ports or len(set(ports)) != len(ports):
            raise ValueError("Extraction requires an ordered list of unique ports")
        # Magic trims ! (even in prefixes) and rewrites several other SPICE characters.
        # Alias only unsafe interface labels in an isolated GDS copy, never source text.
        aliases = {p: f"LBPORT_{inputs['layout'].sha256[:16]}_{i}" for i, p in enumerate(ports)
                   if self.case_insensitive_ports or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p)}
        if self.case_insensitive_ports and len({p.casefold() for p in ports}) != len(ports):
            raise ValueError("Case-insensitive ports must be unique")
        port_commands = []
        for index, port in enumerate(ports, 1):
            arg = _tcl_word(aliases.get(port, port))
            port_commands.extend([f'if {{[port {arg} index] eq ""}} {{port {arg} make {index}}} else {{port {arg} index {index}}}',
                                  f'if {{[port {arg} index] ne "{index}"}} {{reject_candidate "Missing or ambiguous port"}}'])
        prepare_layout = bool(aliases) or self.wire_resistance or self.label_layers is not None
        script = "\n".join([
            ('proc reject_candidate {message} {set f [open extraction-rejection.txt w]; '
             'puts $f $message; close $f; error $message}'),
            "if {[catch {", "drc off", f"tech load {_tcl_word('/workspace/support/' + self.technology)}",
            f'if {{[tech name] ne {_tcl_word(self.tech_name)}}} {{error "Wrong technology"}}',
            *([f"scalegrid 1 {self.grid_subdivision}"] if self.grid_subdivision != 1 else []),
            f"gds readonly {'true' if self.gds_readonly else 'false'}",
            "gds read extraction.gds" if prepare_layout else "gds read candidate.gds",
            f'if {{[cellname list exists {_tcl_word(top)}] eq "0"}} {{reject_candidate "Missing top cell"}}',
            f"load {_tcl_word(top)}", "select top cell", "expand",
            *port_commands, f"extract style {_tcl_word(self.style)}", "extract warn all", "extract all",
            *(["ext2spice default", "ext2spice format ngspice", "ext2spice scale off",
               "ext2spice hierarchy off", "ext2spice subcircuit top on", "ext2spice global off",
               "ext2spice short resistor", "ext2spice extresist off", "ext2spice cthresh infinite",
               "ext2spice -o topology.spice"] if self.wire_resistance else []),
            *(["extresist threshold 0", "extresist minres 0", "extresist mindelay 0",
               "extresist simplify off",
               *([f"set f [open {_tcl_word(top + '.ext')} r]", "set data [read $f]", "close $f",
                  "extresist include all",
                  'foreach line [split $data "\\n"] {if {[regexp {^(node|substrate) "([^"]+)"} $line match kind name]} {extresist include $name}}']
                 if self.resistance_net_selection == "canonical" else []),
               "extresist all"] if self.wire_resistance else []),
            "ext2spice default", "ext2spice format ngspice", "ext2spice scale off",
            "ext2spice hierarchy off", "ext2spice subcircuit top on", "ext2spice global off",
            *(["ext2spice merge none", "ext2spice short none", "ext2spice extresist on"]
              if self.wire_resistance else ["ext2spice extresist off"]),
            "ext2spice rthresh infinite",
            f"ext2spice cthresh {self.threshold:.17g}", "ext2spice -o extracted.spice",
            *([f"file copy -- {_tcl_word(top + '.ext')} extraction.ext",
               f"file copy -- {_tcl_word(top + '.res.ext')} resistance.ext",
               "feedback save feedback.tcl"] if self.wire_resistance else []),
            'set done [open complete.txt w]', 'puts $done "extraction complete"', "close $done",
            '} detail]} {puts stderr "EXTRACTION_ERROR: $detail"; exit 1}', "quit -noprompt", "",
        ])
        files = {"candidate.gds": inputs["layout"], "extract.tcl": Asset(script.encode(), "tcl"),
                 "empty.magicrc": Asset(b"# No user startup or device generators.\n", "tcl"),
                 **self.support.mounted_files(), **self.model_files}
        if self.import_technology is not None:
            files[f"support/{self.technology}"] = self.import_technology
        preprocessing = {}
        if prepare_layout:
            helper = Asset(package_source("eda/_scripts/magic_ports.py").read_bytes(), "python")
            mapping = Asset(json.dumps({"aliases": aliases, "ports": [aliases.get(p, p) for p in ports],
                                        "case_insensitive": self.case_insensitive_ports,
                                        **({"label_layers": self.label_layers} if self.label_layers is not None else {}),
                                        **({"flatten_top": top} if self.wire_resistance else {})}).encode(), "json")
            prepared = self.tool.run(["python", "magic_ports.py"], {
                "candidate.gds": inputs["layout"], "magic_ports.py": helper, "ports.json": mapping},
                {"extraction.gds": "gds", "preparation-check.json": "json"})
            preprocessing = {"port_aliases": mapping, "alias_helper": helper,
                             **{f"alias_{k}": a for k, a in prepared.evidence.items()}, **prepared.files}
            if prepared.reason or prepared.returncode:
                return JobResult("error", prepared.reason, evidence=preprocessing)
            files["extraction.gds"] = prepared.files["extraction.gds"]
        files["magic_netlist.py"] = Asset(package_source("eda/_scripts/magic_netlist.py").read_bytes(), "python")
        files["interface.json"] = Asset(json.dumps({"top_cell": top, "ports": [aliases.get(p, p) for p in ports],
                                                   "reject_aliased_ports": self.wire_resistance,
                                                   "allow_aliased_ports": self.resistance_net_selection == "canonical",
                                                   "model_interface": bool(self.model_files)}).encode(), "json")
        result = self.tool.run(["python", "magic_netlist.py"], files,
                               {"extracted.spice": "spice", "complete.txt": "text", "interface-check.json": "json",
                                **({"native.spice": "spice"} if self.model_files else {}),
                                **({"extraction.ext": "magic-ext", "resistance.ext": "magic-ext",
                                    "feedback.tcl": "tcl", "topology.spice": "spice"}
                                   if self.wire_resistance else {})})
        evidence = {**self.support.evidence(), **preprocessing, **result.evidence, "script": files["extract.tcl"],
                    "interface": files["interface.json"], "interface_checker": files["magic_netlist.py"]}
        if self.import_technology is not None:
            evidence["import_technology"] = self.import_technology
        if "interface-check.json" in result.files:
            evidence["interface_check"] = result.files["interface-check.json"]
        if "extracted.spice" in result.files:
            evidence["extracted_netlist"] = result.files["extracted.spice"]
        if "native.spice" in result.files:
            evidence['native_model_parameters'] = result.files['native.spice']
        for name in ("extraction.ext", "resistance.ext", "feedback.tcl", "topology.spice"):
            if name in result.files:
                evidence[name] = result.files[name]
        log = result.evidence.get("console", Asset(b"", "text")).content.decode(errors="replace")
        failure = native_failure([log.encode()])
        if (result.returncode != 0 or failure
                or any(name.endswith(("execution_error", "cleanup_error")) for name in result.evidence)):
            return JobResult("error", result.reason or "Magic did not complete", evidence=evidence, failure=failure)
        status, diagnostic_reason, diagnostic_evidence = self._check_diagnostics(log, result.files)
        evidence.update(diagnostic_evidence)
        # A completed native rejection identifies a candidate problem. Generic
        # console errors must not hide that verdict or its participant feedback.
        try:
            verdict = json.loads(result.files["interface-check.json"].content)
            if verdict["status"] == "failed" and isinstance(verdict["reason"], str) and verdict["reason"]:
                return JobResult("failed", verdict["reason"], evidence=evidence)
            if verdict["status"] != "passed":
                raise ValueError("Unknown interface verdict")
        except (KeyError, ValueError, TypeError) as error:
            return JobResult("error", f"Invalid Magic interface report: {error}", evidence=evidence)
        if status == "error":
            return JobResult(status, diagnostic_reason, evidence=evidence)
        if result.reason:
            return JobResult("error", result.reason or "Magic did not complete", evidence=evidence)
        if status == "failed":
            return JobResult(status, diagnostic_reason, evidence=evidence)
        return JobResult("passed", outputs={"netlist": result.files["extracted.spice"]}, evidence=evidence)


class MagicRCDocker(MagicCapacitanceDocker):
    """Extract distributed resistance and capacitance without resistor pruning.

    The isolated extraction copy is flattened with a geometry equivalence check.
    Requires the explicit threshold controls introduced in Magic 8.3.653.
    """

    wire_resistance = True

    def __init__(self, **settings):
        super().__init__(**settings)
        version = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", self.tool.identity["tool_version"].strip())
        if version is None or tuple(map(int, version.groups())) < (8, 3, 653):
            raise ValueError("Magic RC extraction requires Magic 8.3.653 or newer")
