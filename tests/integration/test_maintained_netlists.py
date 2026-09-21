"""Maintained CDL and SPICE agree on devices, connectivity and tap geometry."""

import json
import os
from pathlib import Path

import pytest

from benchmarking.bundles import load_bundle
from benchmarking.engine.docker import DockerTool
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.files import Asset

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
from helpers.catalog import ROOT as PUBLIC_ROOT


@pytest.mark.parametrize("case_name", ["full_OTA", "comparator"])
def test_maintained_netlists_agree_on_devices_and_tap_geometry(tmp_path, case_name):
    case = PUBLIC_ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases" / case_name
    from benchmarking.tasks import load_task
    task = load_task(case / "case.toml")
    top = task.netlist_subcircuit
    image = os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local")
    cdl = task.input_assets()["netlist"]
    spice = task.input_assets()["simulation"]
    expected_ports = next(line.split()[1:] for line in task.input_assets()["netlist"].content.decode().splitlines()
                          if line.lower().startswith(".subckt "))
    for netlist in (cdl, spice):
        line = next(line for line in netlist.content.decode().splitlines() if line.startswith(".subckt"))
        assert line.split()[1:] == expected_ports

    prepare_support(None, f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#klayout", tmp_path / "support")
    bundle = load_bundle(tmp_path / "support")
    prepare_support(None, f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#model-calls", tmp_path / "model-calls")
    model_calls = load_bundle(tmp_path / "model-calls")
    # Cross-check model interfaces with the PDK reader without simplification:
    # this catches missing devices, altered terminals and geometry parameters.
    script = """require 'json'
require 'logger'
def logger; Logger.new($stdout); end
def dbu; 0.001; end
base = '/workspace/support/ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/'
%w[globals.lvs custom_combiner.lvs custom_devices.lvs custom_mim_extractor.lvs custom_reader.lvs].each { |f| load(base + f) }
load('/workspace/support/sg13g2-model-calls.lvs')
result = {}
%w[cdl spice].each do |kind|
  n = RBA::Netlist.new
  n.read('circuit.' + kind, RBA::NetlistSpiceReader.new(CustomReader.new))
  c = n.circuit_by_name('TWO_STAGE_OTA_LAYOUT')
  result[kind] = c.each_device.to_h do |d|
    cls = d.device_class
    [d.name, {model: cls.name.downcase,
      params: cls.parameter_definitions.to_h { |p| [p.name, d.parameter(p.id)] },
      nets: cls.terminal_definitions.to_h { |t| [t.name, d.net_for_terminal(t.id).name] }}]
  end
end
File.write('comparison.json', JSON.pretty_generate(result))
"""
    result = DockerTool(image, ["klayout", "-v"], 120).run(
        ["klayout", "-b", "-r", "compare.rb"],
        {"compare.rb": Asset(script.replace("TWO_STAGE_OTA_LAYOUT", top.upper()).encode(), "ruby"), "circuit.cdl": cdl,
         "circuit.spice": spice, **bundle.mounted_files(), **model_calls.mounted_files()}, {"comparison.json": "json"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence["console"].content.decode()
    comparison = json.loads(result.files["comparison.json"].content)
    (tmp_path / "comparison.json").write_bytes(result.files["comparison.json"].content)
    assert comparison["cdl"] == comparison["spice"]
    devices = comparison["cdl"]
    # SPICE prefixes each instance identifier with its card type; the native
    # reader exposes the identifier without that leading type character.
    expected_devices = {line.split()[0][1:] for line in cdl.content.decode().splitlines()
                        if line and line[0].upper() in {'M', 'R', 'C', 'Q'}}
    assert set(devices) == expected_devices
    taps = {name: (device['params']['A'], device['params']['P'])
            for name, device in devices.items() if device['model'] in {'ntap1', 'ptap1'}}
    cards = [line.split() for line in spice.content.decode().splitlines() if line.startswith("XR")]
    for name, (area, perimeter) in taps.items():
        card = next(card for card in cards if card[0] == "X" + name)
        parameters = dict(token.split("=") for token in card[4:])
        expected_r = 1 / (area * 1e-12 / 9.8e-10 + perimeter * 1e-6 / 9.8e-4)
        # Native ev7 emits seven significant digits.
        assert float(parameters["r"]) == pytest.approx(expected_r, rel=1e-6)
