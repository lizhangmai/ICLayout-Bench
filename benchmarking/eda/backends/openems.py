"""Run declared native GDS-to-EM workflows on frozen geometry."""

import json
from pathlib import Path

from benchmarking.evaluation.contracts import JobResult
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset, keys, relative


class _NativeEMNetworkDocker:
    """Extract every column of an EM network using reviewed PDK resources.

    Port geometry and reference conductors are explicit in the input GDS.
    An optional SPICE equivalent uses scikit-rf's native fit and exporter.
    An optional declared circuit is concatenated unchanged; the adapter never
    partitions layouts or rewires device connections.
    """

    def __init__(self, *, image, support, workflow, stackup,
                 timeout_seconds=3600, memory_mb=32768):
        self.support = load_bundle(Path(support))
        self.workflow = relative(workflow, "native EM workflow")
        self.stackup = relative(stackup, "native EM stackup")
        self.tool = DockerTool(image, list(self.version_command), timeout_seconds, memory_mb=memory_mb)
        self.runner = Asset(package_source(self.runner_path).read_bytes(), "python")

    @property
    def extra_configuration(self):
        return {}

    @property
    def extra_scripts(self):
        return {}

    @property
    def identity(self):
        return {"adapter": self.adapter, **self.tool.identity,
                "adapter_sha256": Asset(Path(__file__).read_bytes(), "python").sha256,
                "runner_sha256": self.runner.sha256,
                "support_sha256": self.support.manifest.sha256,
                "workflow": self.workflow, "stackup": self.stackup}

    def run(self, job, inputs):
        keys(inputs, {"layout", "ports"}, {"circuit", "models"}, "native EM inputs")
        outputs = dict(job.outputs)
        if (job.stage != "extract" or inputs["layout"].format != "gds"
                or inputs["ports"].format != "json"
                or outputs not in ({"network": "touchstone"},
                                   {"network": "touchstone", "model": "spice"},
                                   {"network": "touchstone", "model": "spice", "netlist": "spice"})):
            raise ValueError("EM extraction requires GDS, JSON ports and a Touchstone output")
        keys(job.parameters, self.required_settings, self.optional_settings, "EM settings")
        if ("model" in outputs) != ("model" in job.parameters):
            raise ValueError("An EM SPICE model requires explicit native fitting settings")
        if ("circuit" in inputs) != ("netlist" in outputs):
            raise ValueError("An assembled EM netlist requires a prepared circuit input")
        if "circuit" in inputs and inputs["circuit"].format != "spice":
            raise ValueError("An EM circuit input must be SPICE")
        if "models" in inputs and ("circuit" not in inputs or inputs["models"].format != "spice"):
            raise ValueError("EM circuit model definitions require a prepared SPICE circuit")
        config = Asset(json.dumps({**job.parameters, **self.extra_configuration, "workflow": self.workflow,
                                   "stackup": self.stackup}).encode(), "json")
        result = self.tool.run(["python", "run.py"], {
            "run.py": self.runner, "candidate.gds": inputs["layout"],
            "ports.json": inputs["ports"], "config.json": config,
            **self.support.mounted_files(), **self.extra_scripts,
        }, {"result.json": "json", "network.snp": "touchstone", "model.spice": "spice",
            "model.native.spice": "spice", "fields.tar.gz": "tar+gzip"},
            environment={"OMP_NUM_THREADS": str(job.parameters["threads"]),
                "OPENBLAS_NUM_THREADS": "1"})
        evidence = {**result.evidence, **result.files, "runner": self.runner, "configuration": config}
        if result.returncode or result.reason:
            return JobResult("error", result.reason or "Native EM execution failed", evidence=evidence)
        try:
            verdict = json.loads(result.files["result.json"].content)
            if verdict["status"] != "passed":
                return JobResult("error", verdict["reason"], evidence=evidence)
            network = result.files["network.snp"]
            if not network.content:
                raise ValueError("Missing native EM network")
        except (ValueError, KeyError, TypeError) as error:
            return JobResult("error", f"Invalid native EM result: {error}", evidence=evidence)
        produced = {"network": network}
        if "model" in outputs:
            model = result.files.get("model.spice")
            if model is None or not model.content:
                return JobResult("error", "Missing native EM SPICE model", evidence=evidence)
            produced["model"] = model
            if "netlist" in outputs:
                circuit = inputs["circuit"].content
                if "models" in inputs:
                    circuit += b"\n" + inputs["models"].content
                produced["netlist"] = Asset(circuit + b"\n" + model.content, "spice")
        return JobResult("passed", outputs=produced, evidence=evidence)


class OpenEMSDocker(_NativeEMNetworkDocker):
    """Native PDK FDTD with every port excited and checked."""

    adapter = "openems-docker"
    runner_path = "eda/_scripts/openems_runner.py"
    version_command = ("python", "-c",
        "import CSXCAD,openEMS; print('CSXCAD',CSXCAD.__version__,'openEMS',openEMS.__version__)")
    required_settings = frozenset({"fstart", "fstop", "numfreq", "cellsize", "margin",
                                  "energy_limit", "boundaries", "threads"})
    optional_settings = frozenset({"model", "merge_polygon_size", "preprocess_gds"})


class PalaceDocker(_NativeEMNetworkDocker):
    """Native PDK FEM with complete multiport CSV and native SPICE fitting."""

    adapter = "palace-docker"
    runner_path = "eda/_scripts/palace_runner.py"
    version_command = ("palace", "--help")
    required_settings = frozenset({"fstart", "fstop", "fstep", "cellsize", "margin", "meshsize_max",
        "air_around", "boundaries", "adaptive_sweep", "conductor_model", "order", "threads", "processes"})
    optional_settings = frozenset({"model", "merge_polygon_size", "preprocess_gds", "adaptive_mesh_iterations", "adaptive_tolerance", "cad_threads", "cad_boolean_simplify", "mesh_algorithm_3d", "fill_factor_correction", "excitation_batch_size", "parallel_batches", "linear_solver", "complex_coarse_solve", "solver_maxits", "solver_tol", "krylov_max_size"})

    def __init__(self, *, converter, timeout_seconds=10800, memory_mb=49152, **kwargs):
        self.converter = relative(converter, "native Palace CSV converter")
        super().__init__(timeout_seconds=timeout_seconds, memory_mb=memory_mb, **kwargs)
        self.fit_runner = Asset(package_source("eda/_scripts/openems_runner.py").read_bytes(), "python")

    @property
    def extra_configuration(self):
        return {"converter": self.converter}

    @property
    def extra_scripts(self):
        return {"native_fit.py": self.fit_runner}

    @property
    def identity(self):
        return {**super().identity, "converter": self.converter, "fit_runner_sha256": self.fit_runner.sha256}
