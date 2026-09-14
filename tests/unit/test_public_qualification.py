"""Executable contracts for qualified public cases and executable candidates.

The inventory is intentionally discovered from the public catalogs.  This
keeps the checks useful when cases are added or split, while ensuring that a
qualified label cannot silently describe an inventory-only or physical-only
record.  Real EDA and simulator evidence remains integration work; these
checks protect the frozen data flow that makes that evidence meaningful.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from benchmarking.tasks import load_task

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def _executable_cases():
    """Yield qualified records and executable candidates without skipping either."""
    for catalog_path in sorted((ROOT / "tasks").glob("*/*/catalog.toml")):
        catalog = tomllib.loads(catalog_path.read_text())
        for entry in catalog["cases"]:
            case_path = catalog_path.parent / entry["config_path"]
            case = tomllib.loads(case_path.read_text())
            if case["status"] == "qualified" or case.get("task"):
                yield case_path, case


def _ancestors(jobs, job_id):
    """Return jobs required by ``job_id`` through the frozen dependency graph."""
    seen = set()

    def visit(current):
        for dependency in jobs[current].requires:
            if dependency not in seen:
                seen.add(dependency)
                visit(dependency)

    visit(job_id)
    return seen


def _logical_lines(raw):
    """Join SPICE continuation lines for the small top-level checks below."""
    logical = []
    for raw_line in raw.splitlines():
        line = raw_line.decode("utf-8", "replace").strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+") and logical:
            logical[-1] += " " + line[1:].strip()
        else:
            logical.append(line)
    return logical


def _subckt_ports(raw, name):
    for line in _logical_lines(raw):
        fields = line.split()
        if len(fields) >= 2 and fields[0].lower() == ".subckt" and fields[1].lower() == name.lower():
            return fields[2:]
    return None


def _dut_argument_lists(raw, name):
    """Find top-level X instances of the authoritative DUT subcircuit."""
    calls = []
    for line in _logical_lines(raw):
        fields = line.split()
        if not fields or not re.fullmatch(r"x[^\s]*", fields[0], flags=re.IGNORECASE):
            continue
        matches = [index for index, field in enumerate(fields[1:], start=1)
                   if field.lower() == name.lower()]
        if matches:
            calls.append(fields[1:matches[0]])
    return calls


def test_executable_public_cases_have_complete_post_layout_plans():
    """Published executable cases must have performance-bounded plans."""
    cases = list(_executable_cases())
    assert cases, "Public catalogs must expose at least one executable case"

    for case_path, case in cases:
        task = load_task(case_path)
        plan = task.evaluation
        assert plan is not None, f"{case_path} has no executable task"
        assert plan.mode == "post_layout", f"{case_path} is not a post-layout task"
        assert "coefficient" in case["task"], f"{case_path} has no reviewed task coefficient"
        assert plan.description().get("scoring", {}).get("method") == "layout-v1", (
            f"{case_path} has no unified scoring calibration")

        performance = [metric for metric in plan.metrics if metric.category == "performance"]
        assert performance, f"{case_path} has no functional performance metric"
        assert any(metric.is_requirement for metric in performance), (
            f"{case_path} has no bounded performance requirement")

        jobs = {job.id: job for job in plan.jobs}
        netlist = next(item for item in task.inputs if item.role == "netlist")
        netlist_ports = _subckt_ports(netlist.content, task.netlist_subcircuit)
        assert netlist_ports, f"{case_path} netlist lacks its declared subcircuit header"
        gate_jobs = {job.gate: job for job in plan.jobs
                     if job.gate in {"artifact", "drc", "lvs"}}
        assert set(gate_jobs) == {"artifact", "drc", "lvs"}, (
            f"{case_path} must expose one candidate artifact, DRC, and LVS gate")
        gate_ids = set()
        for gate, job in gate_jobs.items():
            gate_ids.add(job.id)
            assert dict(job.inputs).get("layout") == "candidate", (
                f"{case_path} gate {gate} does not check the submitted GDS")

        extractors = [job for job in plan.jobs if job.stage == "extract"]
        assert extractors, f"{case_path} has no post-layout extraction job"
        for extractor in extractors:
            assert "candidate" in dict(extractor.inputs).values(), (
                f"{case_path} extraction is not bound to the submitted GDS")
            assert gate_ids <= set(extractor.requires), (
                f"{case_path} extraction can bypass a physical validity gate")
            assert extractor.outputs, f"{case_path} extraction publishes no circuit artifact"
            extraction_ports = extractor.parameters.get("ports")
            assert isinstance(extraction_ports, list) and extraction_ports, (
                f"{case_path} extraction has no ordered port contract")
            assert [port.lower() for port in extraction_ports] == [port.lower() for port in netlist_ports], (
                f"{case_path} extraction port order differs from the LVS netlist")

        # Every measured requirement must have a simulation in its dependency
        # lineage, and that simulation must receive a candidate-derived output.
        for metric in performance:
            for observation in metric.observations:
                job_id = observation.split(":", 1)[0]
                lineage = _ancestors(jobs, job_id) | {job_id}
                simulations = [jobs[item] for item in lineage if jobs[item].stage == "simulate"]
                assert simulations, f"{case_path} metric {metric.id} has no simulation"
                for simulation in simulations:
                    assert any(ref.startswith("job:") for _, ref in simulation.inputs), (
                        f"{case_path} simulation {simulation.id} has no extracted DUT input")
                    assert "input:netlist" not in dict(simulation.inputs).values(), (
                        f"{case_path} simulation {simulation.id} uses schematic netlist directly")
                    assert any(ref.startswith("input:") and ref != "input:netlist"
                               for _, ref in simulation.inputs), (
                        f"{case_path} simulation {simulation.id} has no declared testbench input")
                    simulation_extractors = [jobs[item] for item in _ancestors(jobs, simulation.id)
                                             if jobs[item].stage == "extract"]
                    extracted_roles = [role for role, ref in simulation.inputs
                                       if any(ref.startswith(f"job:{extractor.id}:")
                                              for extractor in simulation_extractors)]
                    assert extracted_roles, (
                        f"{case_path} simulation {simulation.id} does not consume PEX output")
                    deck_ref = dict(simulation.inputs).get("deck", "")
                    deck = next(item for item in task.inputs if f"input:{item.role}" == deck_ref)
                    included = {line.split()[1].strip("\"'")
                                for line in _logical_lines(deck.content)
                                if line.lower().startswith(".include ")}
                    assert any(f"{role}.spice" in included for role in extracted_roles), (
                        f"{case_path} simulation {simulation.id} deck does not include its PEX circuit")


def test_public_simulation_decks_match_authoritative_subcircuits():
    """Each performance deck must instantiate the netlist's declared DUT ports."""
    cases = list(_executable_cases())
    assert cases, "Public catalogs must expose at least one executable case"

    for case_path, _ in cases:
        task = load_task(case_path)
        netlist = next(item for item in task.inputs if item.role == "netlist")
        ports = _subckt_ports(netlist.content, task.netlist_subcircuit)
        assert ports, f"{case_path} netlist lacks its declared subcircuit header"

        # A case may reuse its authoritative SPICE netlist for simulation.
        # Any separately supplied simulator representation must expose the
        # same DUT interface as the LVS authority.
        simulation_sources = [item for item in task.inputs
                              if item.role == "simulation" or (
                                  item.role != "netlist"
                                  and _subckt_ports(item.content, task.netlist_subcircuit) is not None)]
        assert all(_subckt_ports(item.content, task.netlist_subcircuit) == ports
                   for item in simulation_sources), (
            f"{case_path} simulator and LVS DUT port declarations differ")

        input_assets = {f"input:{item.role}": item for item in task.inputs}
        simulation_jobs = [job for job in task.evaluation.jobs if job.stage == "simulate"]
        for job in simulation_jobs:
            decks = [input_assets[ref] for _, ref in job.inputs
                     if ref.startswith("input:") and ref in input_assets]
            calls = [call for asset in decks for call in
                     _dut_argument_lists(asset.content, task.netlist_subcircuit)]
            assert calls, f"{case_path} simulation {job.id} has no DUT testbench instance"
            assert all(len(call) == len(ports) for call in calls), (
                f"{case_path} simulation {job.id} DUT port count differs from the netlist")


def test_public_resource_bindings_resolve_declared_profiles():
    """Directory aliases cannot masquerade as PDK profile identifiers."""
    from benchmarking.prepare_support import load_profile

    for case_path, case in _executable_cases():
        for backend in case['toolchain']['backends'].values():
            for setting, profile in backend.get('support_profiles', {}).items():
                assert setting in backend['settings'], (case_path, setting)
                load_profile(f'{case_path.parents[3]}/pdk.toml#{profile}')


def test_published_references_are_excluded_from_materialized_solver_inputs(tmp_path):
    """Reference exclusion applies to every witnessed public task."""
    import hashlib

    for index, (case_path, case) in enumerate(_executable_cases()):
        reference = case.get('qualification', {}).get('reference')
        if reference is None:
            continue
        task = load_task(case_path)
        digest = hashlib.sha256((case_path.parent / reference).read_bytes()).hexdigest()
        assert task.witnessed
        assert digest not in {item.sha256 for item in task.inputs}, case_path
        destination = tmp_path / str(index)
        task.materialize(destination)
        assert not (destination / reference).exists(), case_path
