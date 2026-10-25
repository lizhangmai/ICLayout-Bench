"""ngspice batch adapter; simulator syntax stays outside the evaluation core."""

import math
import re
from pathlib import Path

from benchmarking.evaluation.contracts import (
    Job,
    JobResult,
    Measurement,
    identifier,
    number,
)
from benchmarking.evidence.bundles import load_bundle
from benchmarking.execution.tools.diagnostics import native_failure
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys, relative


def branch_resistors(asset: Asset) -> Asset:
    """Use V=R*I instead of a 1/R nodal stamp for constant linear resistors.

    A series zero-volt sensor and CCVS are exactly the same deterministic
    two-terminal element. This does not provide the resistor's thermal noise.
    Reject unsupported cards rather than silently dropping model/TC parameters.
    """
    text = asset.content.decode("utf-8")
    lines = text.splitlines()
    names = set(re.findall(r"\S+", text.lower()))
    result = []
    changed = False
    for index, line in enumerate(lines):
        fields = line.split()
        if not fields or not fields[0].lower().startswith("r"):
            result.append(line)
            continue
        value = re.fullmatch(
            r"((?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:[tTgGkKmMuUnNpPfF]|[mM][eE][gG])?",
            fields[3]) if len(fields) == 4 else None
        if (value is None or not math.isfinite(float(value[1])) or float(value[1]) <= 0
                or (index + 1 < len(lines) and lines[index + 1].lstrip().startswith("+"))):
            raise ValueError("Branch formulation requires positive constant four-field resistor cards")
        name, positive, negative, resistance = fields
        stem = f"lb_branch_{name}"
        voltage, source, node = f"V{stem}", f"H{stem}", f"{stem}_node"
        if any(value.lower() in names for value in (voltage, source, node)):
            raise ValueError("Branch resistor generated-name collision")
        result.extend([f"{source} {positive} {node} {voltage} {resistance}",
                       f"{voltage} {node} {negative} 0"])
        changed = True
    return Asset(("\n".join(result) + "\n").encode(), "spice") if changed else asset


class NgspiceDocker:
    """Each input role becomes <role>.spice; deck owns analyses and measurements.

    Optional support is a verified snapshot of models, compiled libraries and
    startup settings. It is supplied by tool configuration, independent of tasks.
    """

    def __init__(self, *, image: str, timeout_seconds: float = 60, support: str | None = None,
                 compatibility: str | None = None, resistor_formulation: str = "conductance",
                 max_parallel_jobs: int = 4, threads: int = 1, cpu_budget: int = 8):
        for name, value in (("max_parallel_jobs", max_parallel_jobs),
                            ("threads", threads), ("cpu_budget", cpu_budget)):
            if type(value) is not int or value < 1:
                raise ValueError(f"ngspice {name} must be a positive integer")
        if max_parallel_jobs * threads > cpu_budget:
            raise ValueError("ngspice concurrent jobs and threads exceed the CPU budget")
        self.max_parallel_jobs, self.threads, self.cpu_budget = max_parallel_jobs, threads, cpu_budget
        self.thread_environment = {"OMP_NUM_THREADS": str(threads), "OMP_THREAD_LIMIT": str(threads)}
        if compatibility not in {None, "hsa"}:
            raise ValueError("Unsupported ngspice compatibility mode")
        self.compatibility = compatibility
        if resistor_formulation not in {"conductance", "branch"}:
            raise ValueError("Unsupported resistor formulation")
        self.resistor_formulation = resistor_formulation
        self.support = load_bundle(Path(support)) if support else None
        self.tool = DockerTool(image, ["ngspice", "--version"], timeout_seconds)

    @property
    def identity(self) -> dict:
        return {"adapter": "ngspice-docker",
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "compatibility": self.compatibility,
                "resistor_formulation": self.resistor_formulation,
                "max_parallel_jobs": self.max_parallel_jobs,
                "threads": self.threads, "cpu_budget": self.cpu_budget,
                "thread_environment": dict(self.thread_environment),
                **self.tool.identity,
                "support_sha256": self.support.manifest.sha256 if self.support else None}

    def run(self, job: Job, inputs: dict[str, Asset]) -> JobResult:
        if job.stage != "simulate" or "deck" not in inputs:
            raise ValueError("ngspice requires a simulate job with a deck input")
        params = job.parameters
        keys(params, {"measurements"}, {"values", "exports"}, "ngspice parameters")
        units, values, exports = params["measurements"], params.get("values", {}), params.get("exports", {})
        if not isinstance(units, dict) or not units:
            raise ValueError("ngspice needs named measurements with units")
        if not isinstance(values, dict) or not isinstance(exports, dict):
            raise TypeError("values and exports must be tables")
        for name, unit in units.items():
            identifier(name)
            if not isinstance(unit, str) or not unit:
                raise ValueError("Measurement unit must be a nonempty string")
        if set(exports) != set(dict(job.outputs)) or len(set(exports.values())) != len(exports):
            raise ValueError("ngspice exports must match unique declared job outputs")
        for path in exports.values():
            relative(path, "ngspice export")
            if path == "ngspice.log":
                raise ValueError("ngspice.log is reserved for evidence")
        files = {}
        for name, asset in inputs.items():
            identifier(name)
            if name == "parameters" or asset.format != "spice":
                raise ValueError("ngspice inputs must be SPICE; parameters is a reserved role")
            files[f"{name}.spice"] = asset
        assignments = "".join(f".param {identifier(k)}={number(v):.17g}\n" for k, v in values.items())
        files["parameters.spice"] = Asset(assignments.encode(), "spice")
        evidence = {"parameters": files["parameters.spice"]}
        if self.resistor_formulation == "branch":
            if re.search(r"(?im)^\s*\.?noise\b", inputs["deck"].content.decode("utf-8")):
                raise ValueError("Branch resistor formulation does not support noise analysis")
            for name, asset in inputs.items():
                if name == "deck":
                    continue
                effective = branch_resistors(asset)
                if effective != asset:
                    files[f"{name}.spice"] = effective
                    evidence[f"effective_{name}"] = effective
        environment = dict(self.thread_environment)
        if self.support:
            files.update(self.support.mounted_files())
            evidence.update(self.support.evidence())
            environment["SPICE_USERINIT_DIR"] = "/workspace/support"
        startup_path = "support/.spiceinit" if self.support else ".spiceinit"
        startup = files.get(startup_path, Asset(b"", "text"))
        settings = f"\nset num_threads={self.threads}\n"
        if self.compatibility:
            settings += f"set ngbehavior={self.compatibility}\n"
        startup = Asset(startup.content + settings.encode(), "text")
        files[startup_path] = startup
        environment["SPICE_USERINIT_DIR"] = "/workspace/support" if self.support else "/workspace"
        evidence["effective_startup"] = startup
        requested = {"ngspice.log": "text", **{path: dict(job.outputs)[name] for name, path in exports.items()}}
        result = self.tool.run(["ngspice", "-b", "-o", "ngspice.log", "deck.spice"],
                               files, requested, environment=environment)
        evidence.update(result.evidence)
        if "ngspice.log" in result.files:
            evidence["log"] = result.files["ngspice.log"]
        if result.reason or result.returncode != 0:
            return JobResult("error", result.reason or "ngspice did not complete", evidence=evidence)
        log = result.files["ngspice.log"].content.decode("utf-8", errors="replace")
        console = result.evidence.get("console", Asset(b"", "text")).content
        failure = native_failure([log.encode(), console])
        if failure:
            return JobResult("error", "ngspice reported a native execution failure",
                             evidence=evidence, failure=failure)
        # ngspice reports an absent WHEN/TRIG/TARG event as an Error even when
        # the analysis completes. Only this explicit native verdict rejects a
        # required response; missing/ambiguous scalars alone prove no rejection.
        event_pattern = re.compile(
            r"^\s*Error:\s+measure\s+(\w+)\s+(?:when\(WHEN\)|trig\((?:TRIG|TARG)\)|targ\(TARG\))"
            r"\s*:\s*out of interval\s*$", re.MULTILINE | re.IGNORECASE)
        failed_events = {m[1].casefold() for m in event_pattern.finditer(log)
                         if m[1].casefold() in {name.casefold() for name in units}
                         and re.search(rf"^\s*meas(?:ure)?\s+(?:tran|ac|dc)\s+{re.escape(m[1])}\b"
                                       r"[^\n]*\bfailed!\s*$", log,
                                       re.MULTILINE | re.IGNORECASE)}
        remaining = event_pattern.sub(lambda m: "" if m[1].casefold() in failed_events else m[0], log)
        combined = remaining + "\n" + console.decode("utf-8", errors="replace")
        if re.search(r"^\s*(?:fatal|error)\b|simulation interrupted|timestep too small|unknown model type",
                     combined, flags=re.MULTILINE | re.IGNORECASE):
            return JobResult("error", "ngspice reported an execution or model error", evidence=evidence)
        measurements, rejected = {}, []
        for name, unit in units.items():
            matches = re.findall(rf"^\s*{re.escape(name)}\s*=\s*(\S+)", log,
                                 flags=re.MULTILINE | re.IGNORECASE)
            if (not matches and name.casefold() in failed_events
                    and re.search(r"No\. of Data Rows\s*:\s*[1-9]\d*", log)):
                rejected.append(name)
                continue
            if name.casefold() in failed_events:
                return JobResult("error", f"Contradictory ngspice measurement: {name}", evidence=evidence)
            if len(matches) != 1:
                return JobResult("error", f"Missing/ambiguous ngspice measurement: {name}", evidence=evidence)
            try:
                value = number(float(matches[0]))
            except ValueError:
                return JobResult("error", f"Invalid ngspice measurement: {name}", evidence=evidence)
            measurements[name] = Measurement(value, unit)
        if rejected:
            return JobResult("failed", "Required ngspice measurement event did not occur: " + ", ".join(rejected),
                             evidence=evidence)
        return JobResult("passed", measurements=measurements,
                         outputs={name: result.files[path] for name, path in exports.items()}, evidence=evidence)
