"""Check the maintained input-pair netlists with the PDK reader."""

import json
import os
import re
from pathlib import Path

import pytest

from benchmarking.bundles import load_bundle
from benchmarking.engine.docker import DockerTool
from benchmarking.engine.prepare_support import prepare_support
from benchmarking.files import Asset

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT
CASE = PUBLIC_ROOT / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/input_pair"


def test_maintained_netlists_agree_on_mos_and_tap_dimensions(tmp_path):
    from benchmarking.tasks import load_task
    inputs = load_task(CASE / "case.toml").input_assets()
    raw = inputs["netlist"].content.decode()
    simulation = inputs["simulation"]
    tap_lines = [line for line in raw.splitlines() if line.startswith("R")]
    assert tap_lines
    params = dict(re.findall(r"([AP])\s*=\s*(\S+)", tap_lines[0]))
    tap = next(line.split() for line in simulation.content.decode().splitlines() if line.startswith("XR1 "))
    tap_params = dict(token.split("=") for token in tap[4:])
    # Independently evaluate the PDK symbol's area/perimeter conductance model.
    assert float(tap_params["R"]) == pytest.approx(1 / (float(params["A"]) / 9.8e-10 + float(params["P"]) / 9.8e-4), rel=1e-6)

    # Interpret the maintained CDL and simulator netlists with the pinned PDK's
    # reader. SPICE model names are case-insensitive; normalize that spelling
    # and instance-name prefixes without altering connectivity or parameters.
    script = """require 'json'
require 'logger'
def logger; Logger.new($stdout); end
def dbu; 0.001; end
base = '/workspace/support/ihp-sg13g2/libs.tech/klayout/tech/lvs/rule_decks/'
%w[globals.lvs custom_combiner.lvs custom_devices.lvs custom_mim_extractor.lvs custom_reader.lvs].each { |f| load(base + f) }
load('/workspace/support/sg13g2-model-calls.lvs')
result = {}
%w[fresh simulation].each do |kind|
  netlist = RBA::Netlist.new
  netlist.read((kind == 'simulation' ? 'circuit.spice' : kind + '.cdl'), RBA::NetlistSpiceReader.new(CustomReader.new))
  circuit = netlist.circuit_by_name('INPUT_COMMON_CENTROID')
  result[kind] = circuit.each_device.to_h do |d|
    cls = d.device_class
    [cls.name.downcase + ':' + d.name.sub(/^[MR]/, ''), {
      model: cls.name.downcase,
      params: cls.parameter_definitions.to_h { |p| [p.name, d.parameter(p.id)] },
      nets: cls.terminal_definitions.to_h { |t| [t.name, d.net_for_terminal(t.id).name] }
    }]
  end
end
File.write('comparison.json', JSON.pretty_generate(result))
"""
    prepare_support(None, f"{PUBLIC_ROOT}/tasks/ihp-sg13g2/pdk.toml#klayout",
                    tmp_path / "support")
    bundle = load_bundle(tmp_path / "support")
    result = DockerTool(os.environ.get("ICLAYOUT_BENCH_TEST_IMAGE", "iclayout-bench-tools:local"),
                        ["klayout", "-v"], 120).run(
        ["klayout", "-b", "-r", "compare.rb"],
        {"compare.rb": Asset(script.encode(), "ruby"),
         "fresh.cdl": Asset(raw.encode(), "cdl"),
         "circuit.spice": simulation,
         **bundle.mounted_files()},
        {"comparison.json": "json"},
    )
    assert result.returncode == 0 and not result.reason, result.evidence["console"].content.decode()
    comparison = json.loads(result.files["comparison.json"].content)
    assert comparison["fresh"] == comparison["simulation"]
