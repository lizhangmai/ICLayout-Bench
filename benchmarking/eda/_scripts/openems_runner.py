"""GDS and explicit port planes to a native PDK openEMS network."""

import importlib
import json
import math
import os
import sys
import tarfile
from pathlib import Path

import numpy as np


def fit_model(frequencies, scattering, impedances, settings):
    """Use the native fit and exporter; verify DC and the complete frequency grid."""
    import skrf
    from skrf.vectorFitting import VectorFitting

    if set(settings) != {"real_poles", "complex_poles", "maximum_error", "fit_constant"}:
        raise ValueError("Invalid native EM fitting settings")
    if (any(type(settings[k]) is not int or settings[k] < 0 for k in ("real_poles", "complex_poles"))
            or settings["real_poles"] + settings["complex_poles"] == 0
            or type(settings["maximum_error"]) not in {int, float}
            or not 0 < settings["maximum_error"] < 1
            or type(settings["fit_constant"]) is not bool):
        raise ValueError("Invalid native EM fitting bounds")
    network = skrf.Network(frequency=skrf.Frequency.from_f(frequencies, unit="Hz"),
                           s=scattering, z0=impedances)
    fit = VectorFitting(network)
    # Fit every sample, including DC. Verify the actual response instead of
    # treating a fitting option as proof of electrical equivalence.
    fit.vector_fit(n_poles_real=settings["real_poles"], n_poles_cmplx=settings["complex_poles"],
                   enforce_dc=False, fit_constant=settings["fit_constant"])
    if not fit.is_passive():
        fit.passivity_enforce(n_samples=max(200, len(frequencies) * 2),
                              f_max=float(frequencies[-1]), preserve_dc=True)
    if not fit.is_passive():
        raise ValueError("Native EM equivalent did not pass the scikit-rf passivity test")
    fitted = np.asarray([[fit.get_model_response(i, j, frequencies)
                          for j in range(network.nports)] for i in range(network.nports)])
    error = float(np.abs(fitted.transpose(2, 0, 1) - scattering).max())
    if error > settings["maximum_error"]:
        raise ValueError(f"Native EM fit error {error:g} exceeds {settings['maximum_error']:g}")
    if np.any(fit.poles.real >= 0):
        raise ValueError("Native EM fit is not asymptotically stable")
    fit.write_spice_subcircuit_s("model.native.spice", fitted_model_name="EM_NETWORK", create_reference_pins=True)
    # ngspice clamps a literal |R| < 1e-12 ohm during parameter parsing.
    # Its native instance `scale` parameter expresses the same resistance
    # without that clamp: 1 ohm * scale. Preserve all other exported cards.
    lines, scaled = [], 0
    for line in Path("model.native.spice").read_text().splitlines(keepends=True):
        words = line.split()
        if len(words) == 4 and words[0].startswith("R") and 0 < abs(float(words[3])) < 1e-12:
            line = " ".join(words[:3]) + f" 1 scale={words[3]}\n"
            scaled += 1
        lines.append(line)
    Path("model.spice").write_text("".join(lines))
    return {"maximum_complex_s_error": error, "stable": True, "passive": True,
            "dc_error": float(np.abs(fitted[:, :, 0] - scattering[0]).max())
                if frequencies[0] == 0 else None, "poles": len(fit.poles),
            "native_resistor_scale_parameters": scaled}


def extract(config, ports):
    from klayout import db
    from openEMS import openEMS

    for name in ("fstart", "fstop", "cellsize", "margin", "energy_limit"):
        value = config[name]
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError(f"Invalid openEMS {name}")
    if (not 0 <= config["fstart"] < config["fstop"] or config["cellsize"] <= 0
            or config["margin"] <= 0 or config["energy_limit"] >= 0
            or type(config["numfreq"]) is not int or config["numfreq"] < 2
            or type(config["threads"]) is not int or config["threads"] < 1):
        raise ValueError("Invalid openEMS simulation bounds")
    if (len(config["boundaries"]) != 6
            or any(b not in {"PEC", "PMC", "MUR", "PML_8"} for b in config["boundaries"])):
        raise ValueError("Invalid openEMS boundaries")
    merge_size = config.get("merge_polygon_size", 0)
    if type(merge_size) not in {int, float} or not math.isfinite(merge_size) or merge_size < 0:
        raise ValueError("Invalid native via merge distance")
    preprocess = config.get("preprocess_gds", True)
    if type(preprocess) is not bool:
        raise ValueError("Invalid native GDS preprocessing option")
    if not ports or [p["number"] for p in ports] != list(range(1, len(ports) + 1)):
        raise ValueError("EM ports must be ordered and numbered consecutively")
    layers = [p["source_layer"] for p in ports]
    if (len(set(layers)) != len(layers)
            or any(type(n) is not int or not 0 < n < 65536 for n in layers)):
        raise ValueError("Each EM port requires its own GDS layer")
    layout = db.Layout()
    layout.read("candidate.gds")
    if len(layout.top_cells()) != 1:
        raise ValueError("EM geometry must contain one top cell")
    for number in layers:
        iterator = layout.top_cell().begin_shapes_rec(layout.layer(number, 0))
        found = False
        while not iterator.at_end():
            shape = iterator.shape()
            # Native examples also use zero-xy-area vertical sheets. Region
            # booleans discard those valid port polygons as empty areas.
            found |= shape.is_polygon() or shape.is_box() or shape.is_path()
            iterator.next()
        if not found:
            raise ValueError("EM port geometry is missing")
    sys.path.insert(0, str(Path("support", config["workflow"]).resolve().parent))
    workflow = importlib.import_module(Path(config["workflow"]).name)
    setup, utilities = workflow.simulation_setup, workflow.utilities
    sim_ports = setup.all_simulation_ports()
    for port in ports:
        if (port["direction"] not in {"x", "y", "z", "-x", "-y", "-z"}
                or type(port["impedance"]) not in {int, float}
                or not math.isfinite(port["impedance"]) or port["impedance"] <= 0):
            raise ValueError("Invalid EM port direction or impedance")
        args = {"portnumber": port["number"], "voltage": 1,
                "port_Z0": port["impedance"], "source_layernum": port["source_layer"],
                "direction": port["direction"]}
        if "from_layer" in port:
            args.update(from_layername=port["from_layer"], to_layername=port["to_layer"])
        else:
            args["target_layername"] = port["target_layer"]
        sim_ports.add_port(setup.simulation_port(**args))
    materials, dielectrics, metals = workflow.stackup_reader.read_substrate(
        str(Path("support", config["stackup"]).resolve()))
    if any(metals.getbylayernumber(n) is not None for n in layers):
        raise ValueError("EM port layer collides with a native material layer")
    layernumbers = metals.getlayernumbers() + sim_ports.portlayers
    polygons = workflow.gds_reader.read_gds("candidate.gds", layernumbers,
        purposelist=[0], metals_list=metals, preprocess=preprocess, merge_polygon_size=merge_size)
    root = Path.cwd()
    path = (root / "fields").resolve()
    path.mkdir()
    settings = {"unit": 1e-6, "margin": config["margin"],
        "fstart": config["fstart"], "fstop": config["fstop"], "numfreq": config["numfreq"],
        "refined_cellsize": config["cellsize"], "cells_per_wavelength": 20,
        "energy_limit": config["energy_limit"], "Boundaries": config["boundaries"],
        "numThreads": config["threads"], "preview_only": False, "no_gui": True,
        "simulation_ports": sim_ports, "materials_list": materials,
        "dielectrics_list": dielectrics, "metals_list": metals,
        "layernumbers": layernumbers, "allpolygons": polygons,
        "sim_path": str(path), "model_basename": "candidate"}
    for number in range(1, len(ports) + 1):
        fdtd = openEMS(EndCriteria=10 ** (config["energy_limit"] / 10))
        fdtd.SetGaussExcite((config["fstart"] + config["fstop"]) / 2,
                           (config["fstop"] - config["fstart"]) / 2)
        fdtd.SetBoundaryCond(config["boundaries"])
        settings["excite_portnumbers"] = [number]
        setup.setupSimulation(FDTD=fdtd, settings=settings)
        try:
            setup.runSimulation(FDTD=fdtd, settings=settings)
        finally:
            os.chdir(root)
    f = np.linspace(config["fstart"], config["fstop"], config["numfreq"])
    s = np.asarray([[utilities.calculate_Sij(i, j, f, str(path), sim_ports)
                     for j in range(1, len(ports) + 1)] for i in range(1, len(ports) + 1)],
                   dtype=complex)
    if not np.isfinite(s).all():
        raise ValueError("Native openEMS produced a nonfinite network")
    utilities.write_snp(s[0] if len(ports) == 1 else s, f, "network.snp",
                        z0=sim_ports.get_reference_impedance())
    matrices = s.transpose(2, 0, 1)
    details = {"ports": len(ports), "frequencies": len(f),
        "maximum_singular_value": float(np.linalg.svd(matrices, compute_uv=False).max()),
        "maximum_reciprocity_error": float(np.abs(s - s.transpose(1, 0, 2)).max()),
        "scope": "Native FDTD of the explicit input geometry and port reference planes; no circuit assembly or model fitting."}
    if "model" in config:
        details["model"] = fit_model(f, matrices, sim_ports.get_reference_impedance(), config["model"])
        details["scope"] = "Native FDTD and a scikit-rf passive SPICE equivalent; no circuit assembly."
    return details


if __name__ == "__main__":
    Path("network.snp").touch()
    Path("model.spice").touch()
    Path("model.native.spice").touch()
    try:
        result = {"status": "passed", "details": extract(
            json.loads(Path("config.json").read_text()), json.loads(Path("ports.json").read_text()))}
    except (Exception, SystemExit) as error:  # noqa: BLE001 -- keep native failures as tool evidence.
        result = {"status": "error", "reason": f"{type(error).__name__}: {error}"}
    with tarfile.open("fields.tar.gz", "w:gz") as archive:
        if Path("fields").exists():
            archive.add("fields")
    Path("result.json").write_text(json.dumps(result, indent=2, allow_nan=False))
