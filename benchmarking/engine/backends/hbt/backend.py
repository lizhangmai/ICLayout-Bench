"""Tool orchestration for candidate-derived SG13G2 HBT extraction."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from benchmarking.evaluation.contracts import Job
from benchmarking.files import Asset, keys, text

from ...contracts import JobResult
from ...source import package_source
from ..klayout import KLayoutDocker
from ..magic import MagicRCDocker
from .merge import merge_hbt_netlists
from .netlist import _HBT_MODELS, _canonical_net


class _HBTMagicRCDocker(MagicRCDocker):
    """Defer proven HBT contact diagnostics to the composite graph validator.

    SG13G2 describes HBTs as Magic msubckt devices. ResFixUpConnections still uses
    MOS terminal names for their compact contacts, which may not have a
    separate resistance mesh node. This is not a general warning waiver:
    native device identity and the named terminal must agree, and the caller
    must subsequently validate both Magic graphs against native KLayout HBTs.
    """

    @property
    def identity(self) -> dict:
        return {**super().identity,
                "diagnostic_review_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "diagnostic_policy": "native HBT contacts require subsequent composite graph validation"}

    def _check_diagnostics(self, log: str, files: dict[str, Asset]) -> tuple[str, dict[str, Asset]]:
        pattern = re.compile(
            r"Missing (gate|source|drain|substrate) connection of device at "
            r"\((-?\d+) (-?\d+)\) on net (.+)", re.IGNORECASE)
        diagnostics = []
        for line in log.splitlines():
            if re.search(r"missing\s+\w+\s+connection", line, re.IGNORECASE):
                match = pattern.fullmatch(line)
                if match is None:
                    return "Unrecognized Magic HBT terminal diagnostic", {}
                diagnostics.append(match)
        if not diagnostics:
            return super()._check_diagnostics(log, files)
        reviewed = []
        try:
            devices: dict[tuple[int, int], list[list[str]]] = {}
            for line in files["extraction.ext"].content.decode().splitlines():
                if not line.startswith("device "):
                    continue
                fields = shlex.split(line)
                coordinate = (int(fields[3]), int(fields[4]))
                devices.setdefault(coordinate, []).append(fields)
            # Magic msubckt records: parameters, bulk, then gate/source/drain
            # triples (net, length, attributes). Keep its native terminal order.
            positions = {"substrate": 0, "gate": 1, "source": 4, "drain": 7}
            for match in diagnostics:
                terminal, x, y, net = match.groups()
                coordinate = (int(x), int(y))
                matches = devices.get(coordinate, [])
                if len(matches) != 1:
                    raise ValueError(f"Missing or ambiguous native device at {coordinate}")
                fields = matches[0]
                if fields[1] != "msubckt" or fields[2].casefold() not in _HBT_MODELS:
                    raise ValueError(f"Diagnostic does not identify a supported HBT at {coordinate}")
                terminals = fields[7:]
                while terminals and "=" in terminals[0]:
                    terminals = terminals[1:]
                if len(terminals) != 10 or terminals[positions[terminal.casefold()]] != net:
                    raise ValueError(f"Diagnostic terminal differs from the native HBT at {coordinate}")
                reviewed.append({"diagnostic": match.group(), "model": fields[2],
                                 "coordinate": list(coordinate), "terminal": terminal, "net": net})
        except (KeyError, IndexError, ValueError, UnicodeError) as error:
            return f"Unverified Magic HBT terminal diagnostic: {error}", {}
        remaining = "\n".join(line for line in log.splitlines() if not pattern.fullmatch(line))
        error, evidence = super()._check_diagnostics(remaining, files)
        evidence["terminal_diagnostic_review"] = Asset(json.dumps({
            "status": "requires_composite_mapping", "diagnostics": reviewed,
        }, indent=2).encode(), "json")
        return error, evidence


class SG13G2HBTRCDocker:
    """Extract candidate-derived HBT geometry plus Magic distributed RC."""

    wire_resistance = True

    def __init__(self, *, image: str, klayout_support: str, klayout_profile: str,
                 magic_support: str, technology: str, tech_name: str, style: str,
                 timeout_seconds: float = 180, disable_tap_extraction: bool = False):
        if type(disable_tap_extraction) is not bool:
            raise TypeError("disable_tap_extraction must be a boolean")
        self.disable_tap_extraction = disable_tap_extraction
        self.klayout = KLayoutDocker(image=image, check="lvs", support=klayout_support,
                                     profile=klayout_profile, timeout_seconds=timeout_seconds)
        self.magic = _HBTMagicRCDocker(image=image, support=magic_support, technology=technology,
                                     tech_name=tech_name, style=style,
                                     timeout_seconds=timeout_seconds)
        self.runner = Asset(package_source("engine/container_scripts/hbt_runner.py").read_bytes(), "python")
        self.timeout_seconds = timeout_seconds

    @property
    def identity(self) -> dict:
        return {
            "adapter": "sg13g2-hbt-rc-docker",
            "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
            "spice_number_sha256": Asset(package_source("engine/netlists/spice.py").read_bytes(), "python").sha256,
            "hbt_implementation_sha256": {
                name: Asset(package_source(f"engine/backends/hbt/{name}.py").read_bytes(), "python").sha256
                for name in ("netlist", "connectivity", "passives", "matching", "merge", "backend")
            },
            "runner_sha256": self.runner.sha256,
            "klayout": self.klayout.identity,
            "magic": self.magic.identity,
            "parasitics": "candidate_hbt_geometry_plus_distributed_rc",
            "disable_tap_extraction": self.disable_tap_extraction,
            "mapping_policy": (
                "unique terminal mapping; explicit primitive-wire connectivity may "
                "split one logical internal net; an isolated compact terminal may "
                "use one retained passive/HBT anchor; ambiguous or unproven mappings rejected"
            ),
            "isolated_terminal_policy": (
                "restore a candidate-proven port, or a unique retained Magic passive/HBT "
                "anchor for an internal net, only when the local contact has zero "
                "external R/C references in both Magic outputs; no synthetic ties"
            ),
        }

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        if job.stage != "extract" or set(inputs) - {"layout", "task"} or "layout" not in inputs:
            raise ValueError("SG13G2 HBT extraction requires layout and optional task inputs")
        if inputs["layout"].format != "gds" or dict(job.outputs) != {"netlist": "spice"}:
            raise ValueError("SG13G2 HBT extraction requires GDS and a SPICE netlist output")
        keys(job.parameters, {"ports"}, {"top_cell"}, "SG13G2 HBT extraction parameters")
        params = job.parameters
        ports = params["ports"]
        if not isinstance(ports, list) or not ports or any(not isinstance(port, str) for port in ports):
            raise ValueError("Extraction requires an ordered list of unique ports")
        if len({_canonical_net(port) for port in ports}) != len(ports):
            raise ValueError("Extraction ports must be unique case-insensitively")
        top = params.get("top_cell")
        if "task" in inputs:
            if inputs["task"].format != "json":
                raise ValueError("Task description must be JSON")
            task = json.loads(inputs["task"].content)
            configured = task["output"]["top_cell"]
            if top is not None and top != configured:
                raise ValueError("Extraction top cell differs from task configuration")
            top = configured
        top = text(top, "top cell")

        # This standard PDK mode affects candidate extraction only. The
        # separate physical LVS gate still checks the task's explicit taps.
        # Recording it in both identity and config makes the body boundary
        # reproducible; cases must disclose and calibrate its idealization.
        variables = {**self.klayout.settings["variables"],
                     "disable_tap_extraction": "true" if self.disable_tap_extraction else "false"}
        config = Asset(json.dumps({"deck": self.klayout.settings["deck"],
                                   "variables": variables,
                                   "top_cell": top}, sort_keys=True).encode(), "json")
        files = {"candidate.gds": inputs["layout"], "run.py": self.runner,
                 "config.json": config, **self.klayout.support.mounted_files()}
        extraction = self.klayout.tool.run(
            ["python", "run.py"], files,
            {"result.json": "json", "tool.log": "text", "complete.txt": "text",
             "extracted.spice": "spice"},
        )
        evidence = {**self.klayout.support.evidence(), **extraction.evidence,
                    **{f"klayout:{name}": asset for name, asset in extraction.files.items()},
                    "klayout_runner": self.runner, "klayout_configuration": config}
        if extraction.reason or extraction.returncode != 0:
            return JobResult("error", extraction.reason or "KLayout extraction failed", evidence=evidence)
        try:
            verdict = json.loads(extraction.files["result.json"].content)
        except (KeyError, ValueError, TypeError) as error:
            return JobResult("error", f"Invalid KLayout extraction result: {error}", evidence=evidence)
        if verdict.get("status") != "passed":
            return JobResult("error", verdict.get("reason") or "KLayout extraction did not pass", evidence=evidence)

        magic_result = self.magic.run(job, inputs)
        evidence.update({f"magic:{name}": asset for name, asset in magic_result.evidence.items()})
        if magic_result.status != "passed":
            return JobResult("error", magic_result.reason or "Magic extraction failed", evidence=evidence)
        try:
            klayout_raw = extraction.files["extracted.spice"].content
            magic_raw = magic_result.outputs["netlist"].content
            topology_asset = magic_result.evidence.get("topology.spice")
            topology_raw = topology_asset.content if topology_asset else None
            merged, details = merge_hbt_netlists(klayout_raw, magic_raw, ports, topology_raw)
        except (KeyError, ValueError, UnicodeError) as error:
            evidence["klayout_native_netlist"] = Asset(klayout_raw, "spice") if "klayout_raw" in locals() else Asset(b"", "spice")
            if "magic_raw" in locals():
                evidence["magic_rc_netlist"] = Asset(magic_raw, "spice")
            return JobResult("error", f"Unsafe HBT extractor mapping: {error}", evidence=evidence)
        merged_asset = Asset(merged.encode(), "spice")
        evidence.update({"klayout_native_netlist": Asset(klayout_raw, "spice"),
                         "magic_rc_netlist": Asset(magic_raw, "spice"),
                         "mapping": Asset(json.dumps(details, indent=2, sort_keys=True).encode(), "json"),
                         "merged_netlist": merged_asset})
        return JobResult("passed", outputs={"netlist": merged_asset}, evidence=evidence)

__all__ = ["SG13G2HBTRCDocker"]
