"""Native gds2palace mesh generation, multiport solve and checked export."""

import importlib
import importlib.util
import json
import math
import re
import subprocess
import sys
import tarfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np


def read_network(csv_path, converter, ports, config):
    """Read the upstream CSV format; reject unsolved or truncated responses."""
    import skrf
    from skrf.mathFunctions import dbdeg_2_reim

    spec = importlib.util.spec_from_file_location("native_palace_csv", converter)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    count = len(ports)
    sources = csv_path if isinstance(csv_path, list) else [(csv_path, list(range(1, count + 1)))]
    covered, frequencies, matrices = set(), None, None
    for path, columns in sources:
        if (not columns or any(type(column) is not int or not 1 <= column <= count for column in columns)
                or len(set(columns)) != len(columns) or covered.intersection(columns)):
            raise ValueError("Native FEM excitation columns are missing, invalid or duplicated")
        frequency, magnitudes, phases = [], [], []
        native_count, unit = native.parse_palace_csv(str(path), frequency, magnitudes, phases)
        expected = {f"{i} {j}" for i in range(1, count + 1) for j in columns}
        if native_count != count or not frequency:
            raise ValueError("Native FEM output has missing ports or frequencies")
        native_frequency = skrf.Frequency.from_f(np.asarray(frequency, float), unit=unit).f
        if frequencies is None:
            frequencies = native_frequency
            matrices = np.empty((len(frequency), count, count), dtype=complex)
        elif not np.array_equal(frequencies, native_frequency):
            raise ValueError("Native FEM excitation batches have different frequency grids")
        if len(magnitudes) != len(frequencies) or len(phases) != len(frequencies):
            raise ValueError("Native FEM output has incomplete frequency responses")
        for k, (magnitude, phase) in enumerate(zip(magnitudes, phases, strict=True)):
            if not expected <= magnitude.keys() or not expected <= phase.keys():
                raise ValueError("Native FEM output does not contain every requested port response")
            for i in range(count):
                for j in columns:
                    key = f"{i+1} {j}"
                    db, angle = float(magnitude[key]), float(phase[key])
                    if math.isnan(db) or db == math.inf or not math.isfinite(angle):
                        raise ValueError("Native FEM output contains an invalid response")
                    matrices[k, i, j-1] = dbdeg_2_reim(db, angle)
        covered.update(columns)
    if covered != set(range(1, count + 1)):
        raise ValueError("Native FEM did not solve every excitation column")
    network = skrf.Network(frequency=skrf.Frequency.from_f(frequencies, unit="Hz"),
                           s=matrices, z0=ports[0]["impedance"])
    order = np.argsort(network.f)
    network = skrf.Network(frequency=skrf.Frequency.from_f(network.f[order], unit="Hz"),
                           s=network.s[order], z0=network.z0[order])
    steps = (config["fstop"] - config["fstart"]) / config["fstep"]
    requested = np.linspace(config["fstart"], config["fstop"], round(steps) + 1)
    if (len(network.f) != len(requested) or not np.isfinite(network.s).all()
            or not np.allclose(network.f, requested, rtol=1e-9, atol=1e-3)):
        raise ValueError("Native FEM did not solve the complete declared frequency grid")
    filename = f"network.s{count}p"
    network.write_touchstone(filename=filename, form="ri", skrf_comment=False)
    Path("network.snp").write_bytes(Path(filename).read_bytes())
    return network


def native_linear_settings(config):
    """Translate declared options to the upstream Palace linear-solver schema."""
    settings = {}
    if "linear_solver" in config:
        solver = config["linear_solver"]
        if type(solver) is not str or solver not in {"Default", "AMS", "MUMPS", "SuperLU", "STRUMPACK", "STRUMPACK-MP"}:
            raise ValueError("Invalid native Palace linear solver")
        settings["Type"] = solver
    if "complex_coarse_solve" in config:
        if type(config["complex_coarse_solve"]) is not bool:
            raise ValueError("Invalid native complex coarse-solve setting")
        settings["ComplexCoarseSolve"] = config["complex_coarse_solve"]
    for key, native in (("solver_maxits", "MaxIts"), ("krylov_max_size", "MaxSize")):
        if key in config:
            if type(config[key]) is not int or config[key] < 1:
                raise ValueError("Invalid native Palace Krylov iteration or memory bound")
            settings[native] = config[key]
    if "solver_tol" in config:
        if type(config["solver_tol"]) not in {int, float} or not 0 < config["solver_tol"] < 1:
            raise ValueError("Invalid native Palace linear residual tolerance")
        settings["Tol"] = config["solver_tol"]
    return settings


def prepare_mesh(config, ports):
    from klayout import db

    linear = native_linear_settings(config)
    for key in ("fstart", "fstop", "fstep", "cellsize", "margin", "meshsize_max", "air_around"):
        if type(config[key]) not in {int, float} or not math.isfinite(config[key]):
            raise ValueError("Invalid native FEM numeric setting")
    if (not 0 < config["fstart"] < config["fstop"] or config["fstep"] <= 0
            or any(config[k] <= 0 for k in ("cellsize", "margin", "meshsize_max"))
            or config["air_around"] < 0):
        raise ValueError("Invalid native FEM sweep or geometry bounds")
    steps = (config["fstop"] - config["fstart"]) / config["fstep"]
    if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-6):
        raise ValueError("Native FEM sweep must have an integral number of steps")
    if (any(type(config[key]) is not int or config[key] < 1 for key in ("threads", "processes", "order"))
            or config["order"] not in {1, 2, 3}):
        raise ValueError("Invalid native FEM parallelism or basis order")
    if type(config["adaptive_sweep"]) is not bool or config["conductor_model"] not in {
            "surface", "solve_inside", "solve_inside_skin"}:
        raise ValueError("Invalid native FEM solve method")
    if (len(config["boundaries"]) != 6
            or any(value not in {"ABC", "PEC", "PMC"} for value in config["boundaries"])):
        raise ValueError("Invalid native FEM boundaries")
    if (not ports or [p["number"] for p in ports] != list(range(1, len(ports) + 1))
            or len({p["source_layer"] for p in ports}) != len(ports)):
        raise ValueError("Native FEM requires ordered, distinct physical ports")
    impedances = [p["impedance"] for p in ports]
    if (any(type(z) not in {int, float} or not math.isfinite(z) or z <= 0 for z in impedances)
            or len(set(impedances)) != 1):
        raise ValueError("This native FEM export requires a common real port reference impedance")
    layout = db.Layout()
    layout.read("candidate.gds")
    if len(layout.top_cells()) != 1:
        raise ValueError("Native FEM requires one physical top cell")
    for port in ports:
        if (type(port["source_layer"]) is not int or not 0 < port["source_layer"] < 65536
                or port["direction"].lower() not in {"x", "y", "z", "-x", "-y", "-z"}):
            raise ValueError("Invalid native FEM source layer or direction")
        iterator = layout.top_cell().begin_shapes_rec(layout.layer(port["source_layer"], 0))
        found = False
        while not iterator.at_end():
            shape = iterator.shape()
            found |= shape.is_polygon() or shape.is_box() or shape.is_path()
            iterator.next()
        if not found:
            raise ValueError("EM port geometry is missing")
    sys.path.insert(0, str(Path("support", config["workflow"]).resolve().parent))
    workflow = importlib.import_module(Path(config["workflow"]).name)
    setup = workflow.simulation_setup
    material, dielectric, metal = workflow.stackup_reader.read_substrate(
        str(Path("support", config["stackup"]).resolve()))
    simulation_ports = setup.all_simulation_ports()
    for port in ports:
        if metal.getbylayernumber(port["source_layer"]) is not None:
            raise ValueError("EM source layer collides with a native material layer")
        args = {"portnumber": port["number"], "voltage": 1, "port_Z0": port["impedance"],
                "source_layernum": port["source_layer"], "direction": port["direction"]}
        if "target_layer" in port:
            args["target_layername"] = port["target_layer"]
        else:
            args.update(from_layername=port["from_layer"], to_layername=port["to_layer"])
        simulation_ports.add_port(setup.simulation_port(**args))
    layernumbers = metal.getlayernumbers() + simulation_ports.portlayers
    polygons = workflow.gds_reader.read_gds("candidate.gds", layernumbers, purposelist=[0],
        metals_list=metal, preprocess=config.get("preprocess_gds", True),
        merge_polygon_size=config.get("merge_polygon_size", 0))
    simulation = Path("fields").resolve()
    simulation.mkdir()
    settings = {
        "unit": 1e-6, "margin": config["margin"], "fstart": config["fstart"],
        "fstop": config["fstop"], "fstep": config["fstep"],
        "refined_cellsize": config["cellsize"], "meshsize_max": config["meshsize_max"],
        "air_around": config["air_around"], "boundary": config["boundaries"],
        "adaptive_sweep": config["adaptive_sweep"], "conductor_model": config["conductor_model"],
        "order": config["order"], "adaptive_mesh_iterations": config.get("adaptive_mesh_iterations", 0),
        "preview_only": False, "no_gui": True, "no_preview": True,
        "simulation_ports": simulation_ports, "materials_list": material,
        "dielectrics_list": dielectric, "metals_list": metal, "layernumbers": layernumbers,
        "allpolygons": polygons, "sim_path": str(simulation), "model_basename": "candidate",
    }
    settings.update({key: config[key] for key in ("complex_coarse_solve", "solver_maxits", "solver_tol")
                     if key in config})
    if "fill_factor_correction" in config:
        if type(config["fill_factor_correction"]) is not bool:
            raise ValueError("Invalid native via fill-factor correction setting")
        settings["fill_factor_correction"] = config["fill_factor_correction"]
    import gmsh

    cad_threads = config.get("cad_threads", config["threads"])
    if type(cad_threads) is not int or cad_threads < 1:
        raise ValueError("Invalid declared Gmsh thread count")
    gmsh.initialize(readConfigFiles=False)
    gmsh.option.setNumber("General.NumThreads", cad_threads)
    gmsh.option.setNumber("Geometry.OCCParallel", 1 if cad_threads > 1 else 0)
    if "cad_boolean_simplify" in config:
        simplify = config["cad_boolean_simplify"]
        if type(simplify) is not int or simplify not in {0, 1, 2}:
            raise ValueError("Invalid declared Gmsh boolean simplification mode")
        gmsh.option.setNumber("Geometry.OCCBooleanSimplify", simplify)
    if "mesh_algorithm_3d" in config:
        algorithm = config["mesh_algorithm_3d"]
        if type(algorithm) is not int or algorithm not in {1, 4, 7, 10}:
            raise ValueError("Invalid declared native Gmsh 3D meshing algorithm")
        gmsh.option.setNumber("Mesh.Algorithm3D", algorithm)
    config_name, _ = setup.create_palace(simulation_ports.all_active_excitations(), settings)
    config_path = Path(config_name)
    if not config_path.is_absolute():
        config_path = (config_path if config_path.exists() else simulation / config_path).resolve()
    native_config = json.loads(config_path.read_text())
    native_config["Solver"]["Linear"].update(linear)
    if "adaptive_tolerance" in config:
        tolerance = config["adaptive_tolerance"]
        if type(tolerance) not in {int, float} or not 0 < tolerance < 1 or not config["adaptive_sweep"]:
            raise ValueError("Invalid declared native Palace adaptive-sweep tolerance")
        native_config["Solver"]["Driven"]["AdaptiveTol"] = tolerance
    config_path.write_text(json.dumps(native_config, indent=2))
    return config_path, simulation


def excitation_groups(config, ports):
    """Validate native source groups before the expensive geometry operation."""
    batch_size = config.get("excitation_batch_size", len(ports))
    parallel = config.get("parallel_batches", 1)
    if any(type(value) is not int or value < 1 for value in (batch_size, parallel)):
        raise ValueError("Invalid declared native FEM excitation batching")
    if batch_size < len(ports) and config.get("adaptive_mesh_iterations", 0):
        raise ValueError("Excitation batches require the same fixed mesh")
    groups = [list(range(start, min(start + batch_size, len(ports) + 1)))
              for start in range(1, len(ports) + 1, batch_size)]
    return groups, parallel


def solve_prepared(config, ports, config_path, simulation):
    """Run native sources on one existing native mesh and material configuration."""
    groups, parallel = excitation_groups(config, ports)
    base = json.loads(config_path.read_text())

    def run_batch(item):
        index, columns = item
        if len(groups) == 1:
            path, log_path = config_path, simulation / "solver.log"
            result_directory = simulation / base["Problem"]["Output"]
        else:
            native = json.loads(json.dumps(base))
            if {port["Index"] for port in native["Boundaries"]["LumpedPort"]} != set(range(1, len(ports) + 1)):
                raise ValueError("Native FEM ports do not match the complete excitation plan")
            for port in native["Boundaries"]["LumpedPort"]:
                port["Excitation"] = port["Index"] if port["Index"] in columns else 0
            native["Problem"]["Output"] = f"output/batch-{index}"
            path = simulation / f"config-batch-{index}.json"
            path.write_text(json.dumps(native, indent=2))
            log_path = simulation / f"solver-batch-{index}.log"
            result_directory = simulation / native["Problem"]["Output"]
        with log_path.open("w") as log:
            subprocess.run(["palace", "-np", str(config["processes"]), str(path)],
                           cwd=simulation, stdout=log, stderr=subprocess.STDOUT, check=True)
        with log_path.open() as log:
            if any(any(marker in line.lower() for marker in (
                    "adaptive sampling reached maximum", "did not converge", "failed to converge"))
                   for line in log):
                raise ValueError("Native FEM did not reach its declared solver tolerance")
        candidates = list(result_directory.rglob("port-S.csv"))
        if len(candidates) > 1:
            ranked = [(max((int(v) for v in re.findall(r"iteration(\d+)", str(p))), default=-1), p)
                      for p in candidates]
            latest = max(rank for rank, _ in ranked)
            candidates = [p for rank, p in ranked if rank == latest]
        if len(candidates) != 1:
            raise ValueError("Native FEM did not produce one unambiguous final excitation result")
        return candidates[0], columns

    responses = []
    # Keep only active groups submitted. A failed native call must not leave
    # every remaining source group queued behind it during executor shutdown.
    with ThreadPoolExecutor(max_workers=min(parallel, len(groups))) as pool:
        remaining = iter(enumerate(groups))
        pending = {pool.submit(run_batch, item) for item in
                   [next(remaining) for _ in range(min(parallel, len(groups)))]}
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            responses.extend(future.result() for future in completed)
            for _ in completed:
                item = next(remaining, None)
                if item is not None:
                    pending.add(pool.submit(run_batch, item))
    network = read_network(responses, Path("support", config["converter"]).resolve(), ports, config)
    details = {"ports": network.nports, "frequencies": len(network.f),
        "excitation_batches": len(groups), "parallel_batches": min(parallel, len(groups)),
        "maximum_singular_value": float(np.linalg.svd(network.s, compute_uv=False).max()),
        "maximum_reciprocity_error": float(np.abs(network.s - network.s.transpose(0, 2, 1)).max()),
        "scope": "Native FEM of explicit input geometry; no DC extrapolation or port de-embedding."}
    if "model" in config:
        from native_fit import fit_model
        details["model"] = fit_model(network.f, network.s, ports[0]["impedance"], config["model"])
    return details


def solve(config, ports):
    excitation_groups(config, ports)
    config_path, simulation = prepare_mesh(config, ports)
    return solve_prepared(config, ports, config_path, simulation)


if __name__ == "__main__":
    for filename in ("network.snp", "model.spice", "model.native.spice"):
        Path(filename).touch()
    try:
        result = {"status": "passed", "details": solve(
            json.loads(Path("config.json").read_text()), json.loads(Path("ports.json").read_text()))}
    except (Exception, SystemExit) as error:  # noqa: BLE001 -- retain native failures.
        result = {"status": "error", "reason": f"{type(error).__name__}: {error}"}
    with tarfile.open("fields.tar.gz", "w:gz") as archive:
        if Path("fields").exists():
            archive.add("fields")
    Path("result.json").write_text(json.dumps(result, indent=2, allow_nan=False))
