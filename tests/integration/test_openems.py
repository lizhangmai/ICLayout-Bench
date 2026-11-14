"""Native IHP port example and convergence of the frozen multiport network.

Select an explicit reviewed profile with ICLAYOUT_BENCH_EM_PROFILE. This
checks native invocation, port completeness, reciprocity and mesh sensitivity;
it does not independently calibrate the material stack against silicon.
"""

import json
import os

import pytest

from benchmarking.eda.backends.openems import OpenEMSDocker
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
def em_resources(tmp_path_factory):
    profile = os.environ.get("ICLAYOUT_BENCH_EM_PROFILE")
    if not profile:
        pytest.skip("Set ICLAYOUT_BENCH_EM_PROFILE to a reviewed IHP EM profile")
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)
    source = json.loads(load_profile(profile).content)["source"]
    prepared = prepare_support_cache(prepare_installation(source), profile, compiler_image=image,
        diagnostics=tmp_path_factory.mktemp("em-resources") / "failed")
    return image, prepared, dict(load_bundle(prepared).files)


def example(em_resources, cellsize, *, missing_port=False):
    image, prepared, files = em_resources
    backend = OpenEMSDocker(image=image, support=str(prepared), workflow="workflow/modules",
        stackup="examples/core-stackup.xml", timeout_seconds=3600)
    ports = [{"number": number, "source_layer": 200 + number, "impedance": 50,
              "from_layer": "Metal3" if number < 3 else "Metal2",
              "to_layer": "TopMetal2" if number < 3 else "REF_FOR_TRANSISTOR", "direction": "z"}
             for number in range(1, 6)]
    if missing_port:
        ports[0]["source_layer"] = 10000
    job = Job("em", "extract", "layout.electromagnetic", (), (("network", "touchstone"),), (),
        None, json.dumps({"fstart": 0, "fstop": 200e9, "numfreq": 401, "cellsize": cellsize,
            "margin": 20, "energy_limit": -60, "merge_polygon_size": 0.5,
            "preprocess_gds": False,
            "boundaries": ["PEC"] * 5 + ["MUR"], "threads": 8}))
    return backend.run(job, {"layout": Asset(files["examples/core.gds"].content, "gds"),
                            "ports": Asset(json.dumps(ports).encode(), "json")})


def test_native_em_rejects_a_missing_port_without_returning_a_network(em_resources):
    result = example(em_resources, 0.5, missing_port=True)
    assert result.status == "error"
    assert "port geometry is missing" in result.reason
    assert not result.outputs


@pytest.mark.parametrize("component", ["resistor", "capacitor"])
def test_native_passive_examples_and_passive_equivalents(em_resources, component, tmp_path):
    image, prepared, files = em_resources
    capacitor = component == "capacitor"
    ports = [{"number": i, "source_layer": 200 + i, "impedance": 50,
              "from_layer": "Metal1", "to_layer": (
                  "TopMetal1" if i == 1 else "Metal5") if capacitor else "Metal2", "direction": "z"}
             for i in (1, 2)]
    settings = {"fstart": 0, "fstop": 100e9 if capacitor else 200e9, "numfreq": 401,
        "cellsize": .5 if capacitor else .2, "margin": 10,
        "energy_limit": -100 if capacitor else -60,
        "boundaries": ["PEC"] * 6 if capacitor else ["PEC"] * 5 + ["MUR"],
        "threads": 8, "merge_polygon_size": 1.0 if capacitor else .5,
        "preprocess_gds": capacitor,
        "model": {"real_poles": 4, "complex_poles": 4 if capacitor else 0,
                  "maximum_error": .003, "fit_constant": not capacitor}}
    backend = OpenEMSDocker(image=image, support=str(prepared), workflow="workflow/modules",
        stackup="stackup.xml", timeout_seconds=3600)
    job = Job("native_passive", "extract", "layout.electromagnetic", (),
        (("network", "touchstone"), ("model", "spice"), ("netlist", "spice")), (), None, json.dumps(settings))
    circuit = Asset(b"* Declared circuit\n.subckt control p n\nXmodel p n external_model\n.ends control\n", "spice")
    models = Asset(b".subckt external_model p n\nRcontrol p n 50\n.ends external_model\n", "spice")
    result = backend.run(job, {"layout": Asset(files[f"examples/{component}.gds"].content, "gds"),
                              "ports": Asset(json.dumps(ports).encode(), "json"),
                              "circuit": circuit, "models": models})
    for name, asset in {**result.evidence, **result.outputs}.items():
        (tmp_path / name.replace(":", "_")).write_bytes(asset.content)
    assert result.status == "passed", result.reason
    details = json.loads(result.evidence["result.json"].content)["details"]
    assert details["ports"] == 2
    assert details["maximum_singular_value"] < 1.005
    assert details["maximum_reciprocity_error"] < .001
    assert details["model"]["passive"] and details["model"]["stable"]
    assert details["model"]["maximum_complex_s_error"] <= .003
    assert result.outputs["netlist"].content == (
        circuit.content + b"\n" + models.content + b"\n" + result.outputs["model"].content)


def test_native_hbt_port_example_and_mesh_convergence(em_resources, tmp_path):
    networks = {}
    for mesh in (0.5, 0.35):
        result = example(em_resources, mesh)
        directory = tmp_path / str(mesh)
        directory.mkdir()
        for name, asset in result.evidence.items():
            if name in {"console", "result.json", "fields.tar.gz", "network.snp"}:
                (directory / name).write_bytes(asset.content)
        assert result.status == "passed", result.reason
        networks[f"mesh-{mesh}.s5p"] = result.outputs["network"]
    tool = DockerTool(em_resources[0], ["python", "--version"], 120)
    checked = tool.run(["python", "check.py"], {**networks, "check.py": Asset(b'''
import json
import numpy as np
import skrf
a,b=(skrf.Network(n) for n in ('mesh-0.5.s5p','mesh-0.35.s5p'))
# Native five-port example, the same complete excitation grid on both meshes.
assert a.nports==b.nports==5
assert np.array_equal(a.f,b.f)
assert np.isfinite(a.s).all() and np.isfinite(b.s).all()
reciprocity=float(max(np.abs(a.s-a.s.transpose(0,2,1)).max(),np.abs(b.s-b.s.transpose(0,2,1)).max()))
passivity=float(max(np.linalg.svd(a.s,compute_uv=False).max(),np.linalg.svd(b.s,compute_uv=False).max()))
change=float(np.abs(a.s-b.s).max())
json.dump(dict(reciprocity_error=reciprocity,maximum_singular_value=passivity,mesh_change=change),open('comparison.json','w'))
assert reciprocity < .01
assert passivity < 1.01
assert change < .02
''', "python")}, {"comparison.json": "json"})
    (tmp_path / "comparison.log").write_bytes(checked.evidence["console"].content)
    if "comparison.json" in checked.files:
        (tmp_path / "comparison.json").write_bytes(checked.files["comparison.json"].content)
    assert not checked.returncode and not checked.reason, checked.evidence["console"].content.decode()
    check_field_spice(em_resources[0], networks["mesh-0.35.s5p"], tmp_path / "spice")


def check_field_spice(image, network, directory):
    """Check all 25 responses of the actual field model in native ngspice."""
    directory.mkdir()
    script = Asset(rb'''
import json
import subprocess
from pathlib import Path
import numpy as np
import skrf
from native_fit import fit_model
n = skrf.Network('network.s5p')
details = fit_model(n.f, n.s, 50, {'real_poles': 4, 'complex_poles': 2,
    'maximum_error': .001, 'fit_constant': False})
assert details['native_resistor_scale_parameters'] > 0
ports = ' '.join(f'p{i} 0' for i in range(1, 6))
variables = ' '.join(f's_{i}_{j}' for i in range(1, 6) for j in range(1, 6))
deck = ('Native five-port field equivalent control\n.include model.spice\n'
    + ''.join(f'V{i} p{i} 0 dc 0 ac 1 portnum {i} z0 50\n' for i in range(1, 6))
    + f'XEM {ports} EM_NETWORK\n'
    + '.options reltol=1e-7 abstol=1e-15 vntol=1e-15\n'
    + f'.control\nset numdgt=15\nsp lin 400 500Meg 200G\nwrite response.raw {variables}\n'
    + 'quit\n.endc\n.end\n')
Path('control.spice').write_text(deck)
subprocess.run(['ngspice', '-b', 'control.spice'], check=True)
header, binary = Path('response.raw').read_bytes().split(b'Binary:\n', 1)
names = [line.split()[1] for line in header.decode().split('Variables:\n')[1].splitlines()
         if line.strip()]
table = dict(zip(names, np.frombuffer(binary, dtype='<c16').reshape(-1, len(names)).T))
np.testing.assert_allclose(table['frequency'].real, n.f[1:], rtol=1e-12)
error = max(float(np.abs(table[f's_{i+1}_{j+1}'] - n.s[1:, i, j]).max())
            for i in range(5) for j in range(5))
details['ngspice_maximum_complex_s_error'] = error
Path('comparison.json').write_text(json.dumps(details))
assert error < details['maximum_complex_s_error'] + 1e-6
''', "python")
    result = DockerTool(image, ["ngspice", "--version"], 120).run(
        ["python", "control.py"], {"control.py": script, "network.s5p": network,
            "native_fit.py": Asset(package_source("eda/_scripts/openems_runner.py").read_bytes(), "python")},
        {"comparison.json": "json", "model.spice": "spice", "model.native.spice": "spice",
         "response.raw": "ngspice-raw", "control.spice": "spice"},
        environment={"OPENBLAS_NUM_THREADS": "1"})
    for name, asset in {**result.files, **result.evidence}.items():
        (directory / name.replace(":", "_")).write_bytes(asset.content)
    assert not result.returncode and not result.reason, result.evidence["console"].content.decode()


@pytest.mark.parametrize("copies,capacitance", [(1, 1e-12), (6, 1e-12), (1, 1e-15)])
def test_native_spice_equivalent_preserves_an_analytical_rc_network(tmp_path, monkeypatch, copies, capacitance):
    """10-ohm series arms, 1-kohm/1-pF shunt and 50-ohm ports; exact ABCD.

    The independent DC divider and AC expression check the native exporter,
    terminal order and state scaling. This does not validate a field model.
    """
    np = pytest.importorskip("numpy")
    pytest.importorskip("skrf")
    from benchmarking.eda._scripts.openems_runner import fit_model

    stop = 0.2 / capacitance
    frequency = np.concatenate(([0.0], np.geomspace(1e6, stop, 501)))
    # Both series arms and the shunt dissipate energy. The exact network is
    # strictly passive at DC and infinity, avoiding a degenerate lossless mode
    # in the independent test of numerical accuracy.
    admittance = 1 / 1000 + 2j * np.pi * frequency * capacitance
    denominator = 2.4 + admittance * 72
    scattering = np.zeros((len(frequency), 2 * copies, 2 * copies), dtype=complex)
    for copy in range(copies):
        i = 2 * copy
        scattering[:, i, i] = (0.4 - admittance * 48) / denominator
        scattering[:, i + 1, i + 1] = (0.4 - admittance * 48) / denominator
        scattering[:, i, i + 1] = scattering[:, i + 1, i] = 2 / denominator
    monkeypatch.chdir(tmp_path)
    fitted = fit_model(frequency, scattering, 50,
        {"real_poles": 1, "complex_poles": 0, "maximum_error": 1e-6, "fit_constant": True})
    assert fitted["passive"] and fitted["stable"]
    assert fitted["dc_error"] < 1e-6
    # Probe the last pair; earlier independent ports are terminated at zero.
    connections = "0 0 " * (2 * copies - 2) + "p1 0 out 0"
    circuit = Asset(('''Native EM exporter RC control
.include model.spice
Vin input 0 DC 1 AC 1
Rs input p1 50
Xnetwork PORTS EM_NETWORK
Rl out 0 50
.options reltol=1e-7 vntol=1e-15 abstol=1e-15
.control
set numdgt=15
op
print v(out)
ac dec 10 1e6 STOP
wrdata response.txt v(out)
quit
.endc
.end
'''.replace("PORTS", connections).replace("STOP", str(stop))).encode(), "spice")
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)
    tool = DockerTool(image, ["ngspice", "--version"], 120)
    result = tool.run(["ngspice", "-b", "control.spice"], {
        "model.spice": Asset((tmp_path / "model.spice").read_bytes(), "spice"),
        "control.spice": circuit}, {"response.txt": "text"})
    console = result.evidence["console"].content.decode()
    (tmp_path / "simulation.log").write_text(console)
    assert not result.returncode and not result.reason, console
    import io
    import re

    dc = float(re.search(r"v\(out\)\s*=\s*(\S+)", console)[1])
    assert dc == pytest.approx(50 / (120 + 60 * 60 / 1000), rel=1e-7)
    observed = np.loadtxt(io.BytesIO(result.files["response.txt"].content))
    expected = 1 / (2.4 + 72 * (1 / 1000 + 2j * np.pi * observed[:, 0] * capacitance))
    assert np.max(np.abs(observed[:, 1] + 1j * observed[:, 2] - expected)) < 1e-6
