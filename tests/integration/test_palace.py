"""Native Palace multiport format and the reviewed upstream EM example."""

import json
import os

import pytest

from benchmarking.eda._scripts.palace_runner import prepare_mesh
from benchmarking.eda.backends.openems import PalaceDocker
from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.eda.resources.installation import prepare_installation
from benchmarking.eda.resources.support import load_profile, prepare_support_cache
from benchmarking.evaluation import Job
from benchmarking.evidence.bundles import load_bundle
from benchmarking.evidence.identity import package_source
from benchmarking.execution.tools.docker import DockerTool
from benchmarking.files import Asset

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]


@pytest.fixture(scope="module")
def fem_resources(tmp_path_factory):
    profile = os.environ.get("ICLAYOUT_BENCH_PALACE_PROFILE")
    if not profile:
        pytest.skip("Set ICLAYOUT_BENCH_PALACE_PROFILE to a reviewed native FEM profile")
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)
    source = json.loads(load_profile(profile).content)["source"]
    prepared = prepare_support_cache(prepare_installation(source), profile, compiler_image=image,
        diagnostics=tmp_path_factory.mktemp("fem-resources") / "resources")
    return image, prepared, dict(load_bundle(prepared).files)


def test_native_csv_preserves_twelve_ports_and_rejects_incomplete_results(fem_resources, tmp_path):
    image, prepared, _ = fem_resources
    script = Asset(rb'''
import json
from pathlib import Path
import numpy as np
from native_runner import read_network
n = 12
header = "Frequency (GHz), " + ", ".join(
    f"|S[{i}][{j}]| (dB), arg(S[{i}][{j}]) (deg.)"
    for i in range(1,n+1) for j in range(1,n+1))
rows = []
expected = np.empty((3,n,n), complex)
for k,f in enumerate((1,2,3)):
    row = [str(f)]
    for i in range(n):
        for j in range(n):
            magnitude = .001*(i+1) + .0001*(j+1)
            angle = 3*i-j
            expected[k,i,j] = magnitude*np.exp(1j*np.deg2rad(angle))
            row.extend((str(20*np.log10(magnitude)),str(angle)))
    rows.append(row)
Path("complete.csv").write_text(header+"\n"+"\n".join(", ".join(r) for r in rows)+"\n")
ports = [{"impedance":50} for _ in range(n)]
config = {"fstart":1e9,"fstop":3e9,"fstep":1e9}
network = read_network(Path("complete.csv"),Path("support/convert.py"),ports,config)
np.testing.assert_allclose(network.s,expected,rtol=1e-12,atol=1e-15)
rejected = []
for kind in ("unsolved","truncated"):
    damaged = [list(row) for row in rows]
    if kind == "unsolved":
        damaged[-1][17] = "NULL"
    else:
        damaged[-1] = damaged[-1][:-1]
    path=Path(kind+".csv")
    path.write_text(header+"\n"+"\n".join(", ".join(row) for row in damaged)+"\n")
    try:
        read_network(path,Path("support/convert.py"),ports,config)
    except ValueError:
        rejected.append(kind)
    else:
        raise AssertionError("Incomplete native FEM result was accepted")
Path("comparison.json").write_text(json.dumps({"ports":network.nports,"rejected":rejected}))
''', "python")
    bundle = load_bundle(prepared)
    result = DockerTool(image, ["python", "--version"], 60).run(
        ["python", "control.py"], {"control.py": script,
            "native_runner.py": Asset(package_source("eda/_scripts/palace_runner.py").read_bytes(), "python"),
            **bundle.mounted_files()}, {"comparison.json": "json", "network.snp": "touchstone"})
    for name, asset in {**result.evidence, **result.files}.items():
        (tmp_path / name.replace(":", "_")).write_bytes(asset.content)
    assert not result.returncode and not result.reason, result.evidence["console"].content.decode()


def test_native_fem_example_mesh(fem_resources, tmp_path, monkeypatch):
    """Exercise the native geometry workflow in the shared author environment."""
    _, _, files = fem_resources
    monkeypatch.chdir(tmp_path)
    (tmp_path / "candidate.gds").write_bytes(files["examples/core.gds"].content)
    ports = [{"number": number, "source_layer": 200 + number, "impedance": 50,
              "from_layer": "Metal3" if number < 3 else "Metal2",
              "to_layer": "TopMetal2" if number < 3 else "REF_FOR_TRANSISTOR", "direction": "z"}
             for number in range(1, 6)]
    settings = {"workflow": str(files["workflow/gds2palace"].path),
        "stackup": str(files["examples/core-stackup.xml"].path),
        "fstart": 1e9, "fstop": 196e9, "fstep": 5e9, "cellsize": 1.,
        "margin": 30, "meshsize_max": 30, "air_around": 10, "boundaries": ["ABC"] * 6,
        "adaptive_sweep": True, "adaptive_tolerance": .001,
        "conductor_model": "solve_inside_skin", "order": 2, "threads": 2, "processes": 4,
        "cad_threads": 8,
        "merge_polygon_size": 1.2, "preprocess_gds": True}
    configuration, directory = prepare_mesh(settings, ports)
    native = json.loads(configuration.read_text())
    assert native["Solver"]["Driven"]["AdaptiveTol"] == .001
    mesh = directory / native["Model"]["Mesh"]
    assert mesh.is_file() and mesh.stat().st_size > 0
    assert len(native["Boundaries"]["LumpedPort"]) == len(ports)


@pytest.mark.parametrize("conductor_model", ["surface", "solve_inside_skin"])
def test_native_fem_example_and_mesh_convergence(fem_resources, tmp_path, conductor_model):
    image, prepared, files = fem_resources
    ports = [{"number": number, "source_layer": 200 + number, "impedance": 50,
              "from_layer": "Metal3" if number < 3 else "Metal2",
              "to_layer": "TopMetal2" if number < 3 else "REF_FOR_TRANSISTOR", "direction": "z"}
             for number in range(1, 6)]
    networks = {}
    for mesh in (1.0, .7):
        backend = PalaceDocker(image=image, support=str(prepared), workflow="workflow/gds2palace",
            stackup="examples/core-stackup.xml", converter="convert.py", timeout_seconds=10800)
        settings = {"fstart": 1e9, "fstop": 196e9, "fstep": 5e9, "cellsize": mesh,
            "margin": 30, "meshsize_max": 30, "air_around": 10, "boundaries": ["ABC"] * 6,
            "adaptive_sweep": True, "adaptive_tolerance": .001,
            "conductor_model": conductor_model, "order": 2, "threads": 2, "processes": 4,
            "cad_threads": 8,
            "merge_polygon_size": 1.2, "preprocess_gds": True}
        job = Job("fem", "extract", "layout.electromagnetic", (), (("network", "touchstone"),), (),
                  None, json.dumps(settings))
        result = backend.run(job, {"layout": Asset(files["examples/core.gds"].content, "gds"),
                                  "ports": Asset(json.dumps(ports).encode(), "json")})
        directory = tmp_path / str(mesh)
        directory.mkdir()
        for name, asset in {**result.evidence, **result.outputs}.items():
            (directory / name.replace(":", "_")).write_bytes(asset.content)
        assert result.status == "passed", result.reason
        networks[f"mesh-{mesh}.s5p"] = result.outputs["network"]
    control = Asset(b'''
import json
import numpy as np
import skrf
a,b=(skrf.Network(path) for path in ("mesh-1.0.s5p","mesh-0.7.s5p"))
assert a.nports==b.nports==5
assert np.array_equal(a.f,b.f)
change=float(np.abs(a.s-b.s).max())
reciprocity=float(max(np.abs(n.s-n.s.transpose(0,2,1)).max() for n in (a,b)))
passivity=float(max(np.linalg.svd(n.s,compute_uv=False).max() for n in (a,b)))
json.dump(dict(mesh_change=change,reciprocity_error=reciprocity,
    maximum_singular_value=passivity),open("comparison.json","w"))
assert change < .02
assert reciprocity < .01
assert passivity < 1.01
''', "python")
    result = DockerTool(image, ["python", "--version"], 60).run(
        ["python", "check.py"], {"check.py": control, **networks}, {"comparison.json": "json"})
    for name, asset in {**result.evidence, **result.files}.items():
        (tmp_path / name.replace(":", "_")).write_bytes(asset.content)
    assert not result.returncode and not result.reason, result.evidence["console"].content.decode()
