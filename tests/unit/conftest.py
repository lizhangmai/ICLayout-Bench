"""Synthetic case metadata shared by loader and CLI tests."""

import hashlib

import pytest


@pytest.fixture
def circuit_case(tmp_path):
    checkout = tmp_path / "synthetic-source"
    checkout.mkdir()
    netlist = b".subckt CIRCUIT_REF A B\nR1 A B 1000\n.ends\n"
    (checkout / "circuit.spice").write_bytes(netlist)
    path = tmp_path / "case.toml"
    path.write_text('''schema_version = 2
kind = "layout_case"
id = "synthetic-circuit"
title = "Synthetic circuit"
status = "candidate"
[origin]
url = "https://example.invalid/synthetic-circuit"
''')
    return path


@pytest.fixture
def executable_case(circuit_case):
    root = circuit_case.parent
    plan = 'schema_version = 1\nmode = "physical"\nmetrics = []\n'
    for gate in ("artifact", "drc", "lvs"):
        plan += f'''[[jobs]]
id = "{gate}"
stage = "check"
operation = "layout.{gate}"
gate = "{gate}"
inputs = {{ layout = "candidate" }}
'''
    (root / "checks.toml").write_text(plan)
    circuit_case.write_text(circuit_case.read_text() + f'''
[task]
kind = "netlist_to_gds"
family = "synthetic"
environment = "synthetic-tools"
[task.inputs.netlist]
path = "synthetic-source/circuit.spice"
sha256 = "{hashlib.sha256((root / 'synthetic-source/circuit.spice').read_bytes()).hexdigest()}"
subcircuit = "CIRCUIT_REF"
[task.inputs.evaluation]
path = "checks.toml"
sha256 = "{hashlib.sha256(plan.encode()).hexdigest()}"
[task.constraints]
schema_version = 1
hard = []
[task.output]
path = "answer.gds"
format = "gds"
top_cell = "LAYOUT_TOP"
max_bytes = 1024
[toolchain]
schema_version = 1
[toolchain.backends.fixture]
type = "synthetic"
[toolchain.bindings]
"layout.artifact" = "fixture"
''')
    return circuit_case
