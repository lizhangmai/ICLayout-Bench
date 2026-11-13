"""Native KPEX resources, RC networks and rejection of inconsistent candidates."""

import json
import os

import pytest

from benchmarking.eda.backends.klayout import KLayoutDocker
from benchmarking.eda.backends.kpex import KpexCCDocker, KpexNetgenDocker, KpexRCDocker
from benchmarking.eda.backends.magic import MagicRCDocker
from benchmarking.eda.backends.magic_checks import MagicPhysicalDocker
from benchmarking.eda.images import DEFAULT_IMAGE
from benchmarking.eda.netlists.spice import number
from benchmarking.eda.resources.support import prepare_support
from benchmarking.evaluation import Job
from benchmarking.files import Asset

pytestmark = [pytest.mark.integration, pytest.mark.acceptance_eda]


@pytest.fixture(scope="module")
def resources(tmp_path_factory):
    root = tmp_path_factory.mktemp("kpex-resources")
    manifest = root / "pdk.toml"
    manifest.write_text('''
[source]
kind = "checkout"
[profiles.kpex.source]
kind = "python-package"
distribution = "klayout-pex"
version = "0.9.0"
[profiles.kpex.files."kpex/sky130.lvs"]
path = "klayout_pex/pdk/sky130A/libs.tech/kpex/sky130.lvs"
format = "text"
[profiles.kpex.files."kpex/rule_decks/auto_name_layers.rb"]
path = "klayout_pex/pdk/sky130A/libs.tech/kpex/rule_decks/auto_name_layers.rb"
format = "text"
[profiles.kpex.files."sky130A_tech.pb.json"]
path = "klayout_pex_protobuf/sky130A_tech.pb.json"
format = "json"
''')
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)
    prepare_support(None, f"{manifest}#kpex", root / "support", compiler_image=image)
    return image, str(root / "support")


def wires(tmp_path, *, length=10, wrong_database=False, far_pin=False):
    db = pytest.importorskip("klayout.db")
    layout = db.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("DUT")
    for y, name in ((0, "A"), (2000, "B"), (10000, "SUB")):
        cell.shapes(layout.layer(68, 20)).insert(db.Box(0, y, int(length * 1000), y + 1000))
        cell.shapes(layout.layer(68, 16)).insert(db.Box(0, y, 1000, y + 1000))
        cell.shapes(layout.layer(68, 5)).insert(db.Text(name, db.Trans(500, y + 500)))
    if far_pin:
        end = int(length * 1000)
        cell.shapes(layout.layer(68, 16)).insert(db.Box(end - 1000, 0, end, 1000))
        cell.shapes(layout.layer(68, 5)).insert(db.Text("END", db.Trans(end - 500, 500)))
    path = tmp_path / "candidate.gds"
    layout.write(str(path))
    candidate = Asset(path.read_bytes(), "gds")
    database = db.LayoutVsSchematic("DUT", 0.001)
    database.extract_netlist()
    circuit = db.Circuit()
    circuit.name = "DUT"
    database.netlist().add(circuit)
    for name in ("A", "WRONG" if wrong_database else "B", "SUB"):
        circuit.connect_pin(circuit.create_pin(name), circuit.create_net(name))
    if far_pin:
        circuit.connect_pin(circuit.create_pin("END"), circuit.net_by_name("A"))
    reference = database.netlist().dup()
    database.reference = reference
    assert database.compare(db.NetlistComparer())
    path = tmp_path / "candidate.lvsdb"
    database.write(str(path))
    native = Asset(path.read_bytes(), "klayout-lvs")
    return {"layout": candidate, "database": native, "binding": Asset(json.dumps({
        "candidate_sha256": candidate.sha256, "database_sha256": native.sha256,
        "top_cell": "DUT", "layers": {}}).encode(), "json")}


def extract(resources, inputs, mode, *, ports=None):
    image, support = resources
    backend = (KpexRCDocker if mode == "RC" else KpexCCDocker)(
        image=image, support=support, pdk="sky130A", deck="kpex/sky130.lvs",
        technology="sky130A_tech.pb.json", top_cell_variable="top_cell",
        substrate_node="sky130_gnd",
        variables={"thr": "1", "run_mode": "flat", "scale": "false", "top_lvl_pins": "true",
                   "schematic_simplify": "false", "combine": "false", "purge": "false",
                   "purge_nets": "false"})
    job = Job("pex", "extract", "layout.extract_rc", (), (("netlist", "spice"),), (), None,
              json.dumps({"top_cell": "DUT", "ports": ports or ["A", "B", "SUB"], "substrate": "SUB"}))
    return backend.run(job, inputs)


@pytest.mark.parametrize("mode,length", [("CC", 10), ("RC", 10), ("RC", 20)])
def test_native_wires_preserve_ports_and_extract_declared_parasitics(tmp_path, resources, mode, length):
    ports = ["A", "B", "SUB", "END"] if mode == "RC" else ["A", "B", "SUB"]
    result = extract(resources, wires(tmp_path, length=length, far_pin=mode == "RC"), mode, ports=ports)
    for name in ("console", "geometry.log", "result.json", "extracted.spice"):
        if name in result.evidence:
            (tmp_path / name).write_bytes(result.evidence[name].content)
    assert result.status == "passed", (result.reason, str(tmp_path))
    netlist = result.outputs["netlist"].content.decode()
    assert f'.SUBCKT DUT {" ".join(ports)}' in netlist
    assert any(line.startswith("C") for line in netlist.splitlines())
    assert any(line.startswith("R") for line in netlist.splitlines()) == (mode == "RC")
    if mode == "RC":
        # Independent rectangular-wire calculation: the pin centers are 0.5 um
        # inside each end of a 1 um wide M1 strip; sheet resistance is 0.125 ohm.
        resistors = [line.split() for line in netlist.splitlines() if line.startswith("R")]
        path = [number(row[3]) for row in resistors if set(row[1:3]) == {"A", "END"}]
        assert sum(path) == pytest.approx(0.125 * (length - 1), rel=1e-6)


def test_candidate_database_cannot_hide_a_missing_port(tmp_path, resources):
    result = extract(resources, wires(tmp_path, wrong_database=True), "RC")
    assert result.status == "error"
    assert "ports differ" in json.loads(result.evidence["result.json"].content)["reason"]
    assert not result.outputs


def mos_candidate(tmp_path):
    """One drawn 1 um / 0.15 um NMOS with four contacted terminals."""
    db = pytest.importorskip("klayout.db")
    layout = db.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("DUT")
    def box(layer, values):
        cell.shapes(layout.layer(*layer)).insert(db.Box(*(round(v * 1000) for v in values)))
    box((65, 20), (0, 0, 1.15, 1))
    box((93, 44), (-0.125, -0.125, 1.275, 1.125))
    box((66, 20), (0.5, -0.13, 0.65, 1.8))
    box((66, 20), (0.4, 1.2, 0.75, 1.8))
    box((95, 20), (0.4, 1.3, 0.75, 1.7))
    box((65, 44), (-1, 0, -0.5, 1))
    box((94, 20), (-1.125, -0.125, -0.375, 1.125))
    for name, x, y in (("S", 0.1, 0.4), ("D", 0.85, 0.4),
                       ("G", 0.49, 1.4), ("B", -0.85, 0.4)):
        for layer in ((66, 44), (67, 44)):
            box(layer, (x, y, x + 0.17, y + 0.17))
        for layer in ((67, 20), (68, 20), (68, 16)):
            box(layer, (x - 0.05, y - 0.05, x + 0.22, y + 0.22))
        cell.shapes(layout.layer(68, 5)).insert(db.Text(name, db.Trans(round((x + 0.085) * 1000),
                                                                    round((y + 0.085) * 1000))))
    path = tmp_path / "mos.gds"
    layout.write(str(path))
    return Asset(path.read_bytes(), "gds")


@pytest.fixture(scope="module")
def netgen_resources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sky130-netgen")
    manifest = root / "pdk.toml"
    manifest.write_text('''
[source]
kind = "ciel"
family = "sky130"
version = "e7a6777d157a9d94c7ac757457b9e4309e9e9000"
libraries = ["sky130_fd_pr", "sky130_fd_sc_hvl"]
[profiles.netgen.files."sky130A_setup.tcl"]
path = "sky130A/libs.tech/netgen/sky130A_setup.tcl"
format = "text"
''' + ''.join(f'''
[profiles.netgen.files."{filename}"]
path = "sky130A/libs.tech/magic/{filename}"
format = "text"
''' for filename in ('sky130A.tech', 'sky130A-cifin.tech', 'sky130A-cifout.tech',
                     'sky130A-drc.tech', 'sky130A-extract.tech')))
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", DEFAULT_IMAGE)
    prepare_support(None, f"{manifest}#netgen", root / "support", compiler_image=image)
    return str(root / "support")


@pytest.mark.parametrize("change", [None, "width", "body", "multiplicity"])
def test_native_model_calls_are_compared_by_netgen(tmp_path, resources, netgen_resources, change):
    image, support = resources
    source = '.subckt DUT D G S B\nXA D G S B sky130_fd_pr__nfet_01v8 L=0.15 W=1 m=1\n.ends DUT\n'
    source = {"width": source.replace("W=1", "W=1.2"),
              "body": source.replace("XA D G S B", "XA D G S S"),
              "multiplicity": source.replace("m=1", "m=2")}.get(change, source)
    backend = KpexNetgenDocker(image=image, support=support, netgen_support=netgen_resources,
        setup="sky130A_setup.tcl", pdk="sky130A", deck="kpex/sky130.lvs",
        technology="sky130A_tech.pb.json", top_cell_variable="top_cell", substrate_variable="lvs_sub",
        variables={"thr": "1", "run_mode": "flat", "scale": "false", "top_lvl_pins": "true",
                   "schematic_simplify": "false", "combine": "false", "purge": "false", "purge_nets": "false"})
    job = Job("lvs", "check", "layout.lvs", (), (("database", "klayout-lvs"), ("binding", "json")),
              (), "lvs", json.dumps({"top_cell": "DUT", "subcircuit": "DUT", "substrate": "B"}))
    result = backend.run(job, {"layout": mos_candidate(tmp_path), "netlist": Asset(source.encode(), "spice")})
    assert result.status == ("failed" if change else "passed"), result.reason
    assert set(result.outputs) == (set() if change else {"database", "binding"})


def test_native_mos_model_and_terminals_survive_rc_extraction(tmp_path, resources):
    image, support = resources
    layout = mos_candidate(tmp_path)
    source = Asset(b'.subckt DUT D G S B\nM1 D G S B sky130_fd_pr__nfet_01v8 L=0.15u W=1u\n.ends DUT\n', 'spice')
    lvs = KLayoutDocker(image=image, support=support, check="lvs", deck="kpex/sky130.lvs",
        variables={"top_cell": "DUT", "lvs_sub": "B", "thr": "1", "run_mode": "flat", "scale": "false",
                   "top_lvl_pins": "true", "schematic_simplify": "false", "combine": "false",
                   "purge": "false", "purge_nets": "false"})
    job = Job("lvs", "check", "layout.lvs", (), (("database", "klayout-lvs"), ("binding", "json")),
              (), "lvs", json.dumps({"top_cell": "DUT", "subcircuit": "DUT", "max_bytes": 1000000}))
    checked = lvs.run(job, {"layout": layout, "netlist": source})
    for name in ("tool.log", "extracted.spice"):
        if name in checked.evidence:
            (tmp_path / name).write_bytes(checked.evidence[name].content)
    assert checked.status == "passed", (checked.reason, str(tmp_path))
    inputs = {"layout": layout, **checked.outputs}
    backend = KpexRCDocker(image=image, support=support, pdk="sky130A", deck="kpex/sky130.lvs",
        technology="sky130A_tech.pb.json", top_cell_variable="top_cell", substrate_node="sky130_gnd",
        substrate_variable="lvs_sub",
        variables={"thr": "1", "run_mode": "flat", "scale": "false", "top_lvl_pins": "true",
                   "schematic_simplify": "false", "combine": "false", "purge": "false", "purge_nets": "false"})
    pex_job = Job("pex", "extract", "layout.extract_rc", (), (("netlist", "spice"),), (), None,
                  json.dumps({"top_cell": "DUT", "ports": ["D", "G", "S", "B"], "substrate": "B"}))
    result = backend.run(pex_job, inputs)
    for name in ("console", "geometry.log", "result.json", "extracted.spice", "candidate-reference.spice"):
        if name in result.evidence:
            (tmp_path / f"pex-{name}").write_bytes(result.evidence[name].content)
    assert result.status == "passed", (result.reason, str(tmp_path))
    netlist = result.outputs["netlist"].content.decode()
    assert 'sky130_fd_pr__nfet_01v8' in netlist
    assert json.loads(result.evidence["result.json"].content)["details"]["physical_devices"] == {
        "sky130_fd_pr__nfet_01v8": 1}
    # A prior database with the right ports but a different channel length must
    # not override the independently re-extracted geometry of the submitted GDS.
    db = pytest.importorskip("klayout.db")
    path = tmp_path / "changed.lvsdb"
    path.write_bytes(inputs["database"].content)
    changed = db.LayoutVsSchematic()
    changed.read(str(path))
    device = next(changed.netlist().circuit_by_name("DUT").each_device())
    device.set_parameter("L", 0.2)
    changed.write(str(path))
    database = Asset(path.read_bytes(), "klayout-lvs")
    binding = json.loads(inputs["binding"].content)
    binding["database_sha256"] = database.sha256
    rejected = backend.run(pex_job, inputs | {"database": database,
        "binding": Asset(json.dumps(binding).encode(), "json")})
    assert rejected.status == "error" and not rejected.outputs
    assert "geometry extraction differs" in rejected.reason


def magic_model_settings(resources, netgen_resources):
    image, models = resources
    return {'image': image, 'support': netgen_resources, 'technology': 'sky130A.tech',
            'tech_name': 'sky130A', 'style': 'ngspice(si)', 'grid_subdivision': 2,
            'model_support': models, 'model_technology': 'sky130A_tech.pb.json'}


@pytest.mark.parametrize('change', [None, 'width', 'body', 'multiplicity'])
def test_magic_si_models_preserve_mos_geometry_and_body(tmp_path, resources, netgen_resources, change):
    source = '.subckt DUT D G S B\nXA D G S B sky130_fd_pr__nfet_01v8 L=0.15 W=1 m=1\n.ends DUT\n'
    source = {'width': source.replace('W=1', 'W=1.2'),
              'body': source.replace('XA D G S B', 'XA D G S S'),
              'multiplicity': source.replace('m=1', 'm=2')}.get(change, source)
    backend = MagicPhysicalDocker(check='lvs', setup='sky130A_setup.tcl',
                                  **magic_model_settings(resources, netgen_resources))
    job = Job('lvs', 'check', 'layout.lvs', (), (), (), 'lvs',
              json.dumps({'top_cell': 'DUT', 'subcircuit': 'DUT'}))
    result = backend.run(job, {'layout': mos_candidate(tmp_path), 'netlist': Asset(source.encode(), 'spice')})
    assert result.status == ('failed' if change else 'passed'), result.reason


def test_magic_model_interface_reads_hierarchical_device_metadata(tmp_path, resources, netgen_resources):
    db = pytest.importorskip('klayout.db')
    original = tmp_path / 'hierarchical.gds'
    original.write_bytes(mos_candidate(tmp_path).content)
    layout = db.Layout()
    layout.read(str(original))
    leaf = layout.top_cell()
    leaf.name = 'TRANSISTOR'
    top = layout.create_cell('DUT')
    top.insert(db.CellInstArray(leaf.cell_index(), db.Trans()))
    # Parent routing owns its drawing, pin and label shapes; the transistor
    # remains in the child. The flattened physical geometry is unchanged.
    for pair in ((68, 20), (68, 16), (68, 5)):
        layer = layout.layer(*pair)
        for shape in list(leaf.shapes(layer).each()):
            top.shapes(layer).insert(shape)
            shape.delete()
    layout.write(str(original))
    source = Asset(b'.subckt DUT D G S B\nXA D G S B sky130_fd_pr__nfet_01v8 L=0.15 W=1\n.ends DUT\n', 'spice')
    backend = MagicPhysicalDocker(check='lvs', setup='sky130A_setup.tcl',
                                  **magic_model_settings(resources, netgen_resources))
    job = Job('lvs', 'check', 'layout.lvs', (), (), (), 'lvs',
              json.dumps({'top_cell': 'DUT', 'subcircuit': 'DUT'}))
    result = backend.run(job, {'layout': Asset(original.read_bytes(), 'gds'), 'netlist': source})
    assert result.status == 'passed', result.reason


@pytest.mark.parametrize('change', ['open_gate', 'short_sd'])
def test_magic_model_interface_does_not_repair_candidate_connections(
        tmp_path, resources, netgen_resources, change):
    db = pytest.importorskip('klayout.db')
    path = tmp_path / 'invalid.gds'
    path.write_bytes(mos_candidate(tmp_path).content)
    layout = db.Layout()
    layout.read(str(path))
    top = layout.top_cell()
    if change == 'short_sd':
        top.shapes(layout.layer(68, 20)).insert(db.Box(50, 350, 1070, 620))
    else:
        gate_contact = db.Box(490, 1400, 660, 1570)
        for shape in list(top.shapes(layout.layer(66, 44)).each()):
            if shape.bbox() == gate_contact:
                shape.delete()
    layout.write(str(path))
    source = Asset(b'.subckt DUT D G S B\nXA D G S B sky130_fd_pr__nfet_01v8 L=0.15 W=1\n.ends DUT\n', 'spice')
    backend = MagicPhysicalDocker(check='lvs', setup='sky130A_setup.tcl',
                                  **magic_model_settings(resources, netgen_resources))
    job = Job('lvs', 'check', 'layout.lvs', (), (), (), 'lvs',
              json.dumps({'top_cell': 'DUT', 'subcircuit': 'DUT'}))
    result = backend.run(job, {'layout': Asset(path.read_bytes(), 'gds'), 'netlist': source})
    assert result.status == 'failed', result.reason
    assert not result.outputs


def diode_candidate(tmp_path):
    """A drawn 0.6 um square n+ diode with a separate contacted p-substrate ring."""
    db = pytest.importorskip('klayout.db')
    layout = db.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell('DUT')
    def box(layer, bounds):
        cell.shapes(layout.layer(*layer)).insert(db.DBox(*bounds).to_itype(layout.dbu))
    box((65, 20), (0, 0, .6, .6))
    box((93, 44), (-.125, -.125, .725, .725))
    box((81, 23), (0, 0, .6, .6))
    ring = db.Region(db.Box(-1000, -1000, 1600, 1600)) - db.Region(db.Box(-500, -500, 1100, 1100))
    cell.shapes(layout.layer(65, 44)).insert(ring)
    cell.shapes(layout.layer(94, 20)).insert(ring.sized(125))
    for name, x, y in (('C', .215, .215), ('A', -.85, .215)):
        for layer in ((66, 44), (67, 44)):
            box(layer, (x, y, x + .17, y + .17))
        for layer in ((67, 20), (68, 20), (68, 16)):
            box(layer, (x - .05, y - .05, x + .22, y + .22))
        cell.shapes(layout.layer(68, 5)).insert(db.Text(name, db.Trans(round((x+.085)*1000),
                                                                    round((y+.085)*1000))))
    path = tmp_path / 'diode.gds'
    layout.write(str(path))
    return Asset(path.read_bytes(), 'gds')


@pytest.mark.parametrize('change', [None, 'area', 'perimeter', 'polarity'])
def test_magic_native_diode_units_and_polarity(tmp_path, resources, netgen_resources, change):
    # Area and perimeter are calculated from the drawn square, independently
    # of the extraction metadata and of the model interface implementation.
    source = '.subckt DUT A C\nXD A C sky130_fd_pr__diode_pw2nd_05v5 area=0.36 perim=2.4\n.ends DUT\n'
    source = {'area': source.replace('area=0.36', 'area=0.30'),
              'perimeter': source.replace('perim=2.4', 'perim=2.0'),
              'polarity': source.replace('XD A C', 'XD C A')}.get(change, source)
    backend = MagicPhysicalDocker(check='lvs', setup='sky130A_setup.tcl',
                                  **magic_model_settings(resources, netgen_resources))
    job = Job('lvs', 'check', 'layout.lvs', (), (), (), 'lvs',
              json.dumps({'top_cell': 'DUT', 'subcircuit': 'DUT'}))
    result = backend.run(job, {'layout': diode_candidate(tmp_path), 'netlist': Asset(source.encode(), 'spice')})
    assert result.status == ('failed' if change else 'passed'), result.reason


def test_magic_rc_model_interface_retains_native_interconnect(tmp_path, resources, netgen_resources):
    backend = MagicRCDocker(**magic_model_settings(resources, netgen_resources))
    job = Job('pex', 'extract', 'layout.extract_rc', (), (('netlist', 'spice'),), (), None,
              json.dumps({'top_cell': 'DUT', 'ports': ['D', 'G', 'S', 'B']}))
    result = backend.run(job, {'layout': mos_candidate(tmp_path)})
    assert result.status == 'passed', result.reason
    raw = result.evidence['native_model_parameters'].content.decode()
    bound = result.outputs['netlist'].content.decode()
    def interconnect(text):
        return [(f[0], *f[1:3], number(f[3])) for line in text.splitlines()
                if (f := line.split()) and f[0][0].upper() in {'R', 'C'}]
    assert interconnect(raw)
    assert interconnect(raw) == interconnect(bound)
