"""Preview configuration stays usable with just one arbitrarily named image."""

import hashlib
import importlib.util
import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest
import tomli_w
from helpers.catalog import CATALOGS, read_catalog
from helpers.protocol import write_protocol_task

from benchmarking.engine import prepare_support
from benchmarking.engine.preparation import support_bindings
from benchmarking.tasks import load_task

pytestmark = [pytest.mark.unit, pytest.mark.acceptance, pytest.mark.acceptance_fast]
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_ROOT = ROOT


@pytest.fixture
def preview():
    spec = importlib.util.spec_from_file_location("public_preview", ROOT / "benchmarking/engine/preview.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_covers_every_public_executable_witness(preview):
    expected = {path for catalog in CATALOGS for path, data in read_catalog(catalog)[1]
                if data.get("status") in {"candidate", "qualified"}
                and data.get("task") and data.get("qualification", {}).get("reference")}
    discovered = {record["config"] for record in preview.discover_cases().values()}
    assert discovered == expected
    for key, record in preview.discover_cases().items():
        assert preview._resolve_case(key)["config"] == record["config"]


@pytest.fixture
def preview_case(preview, tmp_path, monkeypatch, circuit_case):
    root = tmp_path / "checkout with spaces"
    source = root / "tasks/ihp-sg13g2/IHP-AnalogAcademy/cases/synthetic"
    task_path = write_protocol_task(source)
    body = task_path.read_text().split("[inputs.netlist]", 1)[1]
    body = re.sub(r"^(\[\[?)", r"\1task.", "[inputs.netlist]" + body, flags=re.MULTILINE)
    config = circuit_case.read_text().replace('status = "candidate"', 'status = "qualified"')
    config += '\n[task]\nkind = "netlist_to_gds"\nfamily = "protocol"\nenvironment = "no-eda"\n' + body
    config += '''
[qualification]
reference = "reference.gds"
evidence = "README.md"
[toolchain]
schema_version = 1
[toolchain.backends.rules]
type = "klayout-docker"
settings = {image = "synthetic-image", support = "source-rules", check = "drc", profile = "reviewed.json"}
support_profiles = {support = "klayout"}
[toolchain.backends.simulation]
type = "ngspice-docker"
settings = {image = "synthetic-image", support = "source-models"}
support_profiles = {support = "analog-models"}
[toolchain.bindings]
check = "rules"
simulate = "simulation"
'''
    (source / "case.toml").write_text(config)
    (source / "reference.gds").write_bytes(b"Maintainer-only witness")
    (source / "README.md").write_text("Maintainer-only provenance")
    (root / "tasks/ihp-sg13g2/IHP-AnalogAcademy/catalog.toml").write_text(
        'schema_version = 3\n\n[[cases]]\n'
        'id = "synthetic-circuit"\nconfig_path = "cases/synthetic/case.toml"\n')
    (root / "third_party/synthetic-pdk/ihp-sg13g2").mkdir(parents=True)
    (root / ".gitmodules").write_text(
        '[submodule "pdk"]\npath = third_party/synthetic-pdk\nurl = https://example.test/pdk.git\n')
    (root / "tasks/ihp-sg13g2/pdk.toml").write_text(tomli_w.dumps({
        "schema_version": 1, "source": {"repository": "https://example.test/pdk"},
        "profiles": {name: {"files": {}} for name in ("klayout", "analog-models", "hbt-models", "magic")},
    }))
    monkeypatch.setattr(preview, "ROOT", root)
    return root, source


def test_preparation_binds_image_and_support_without_delivering_reference(preview, preview_case, monkeypatch):
    root, source = preview_case
    terms = b"Synthetic collection license\n"
    (source.parent.parent / "LICENSE").write_bytes(terms)
    config = source / "case.toml"
    config.write_text(config.read_text() + '\n[task.inputs.license]\n'
                      'path = "materials/LICENSE"\ncollection_source = "LICENSE"\n'
                      f'sha256 = "{hashlib.sha256(terms).hexdigest()}"\n')
    inspected, compilers = [], []
    identity = "sha256:" + "a" * 64

    def inspect(command, **kwargs):
        inspected.append(command[-1])
        return identity + "\n"

    def support(source, profile, output, *, compiler_image):
        compilers.append(compiler_image)
        output.mkdir()

    monkeypatch.setattr(preview.subprocess, "check_output", inspect)
    monkeypatch.setattr(prepare_support, "prepare_support", support)
    destination = root / "prepared"
    preview.prepare(destination, "my-unified-image:reviewed", "synthetic")
    assert inspected == ["my-unified-image:reviewed"]
    assert set(compilers) == {identity}
    bound_case = destination / "case/case.toml"
    toolchain = tomllib.loads(bound_case.read_text())["toolchain"]
    for backend in toolchain["backends"].values():
        assert backend["settings"]["image"] == identity
        path = Path(backend["settings"]["support"])
        assert path.is_dir() and path.parent == destination
    assert toolchain["backends"]["rules"]["settings"]["profile"] == "reviewed.json"
    task = load_task(bound_case)
    assert task.evaluation.description() == load_task(source / "case.toml").evaluation.description()
    task.materialize(root / "solver")
    assert (root / "solver/input.spice").read_bytes() == (source / "input.spice").read_bytes()
    assert not (root / "solver/reference.gds").exists()
    assert not (root / "solver/README.md").exists()
    assert not (root / "solver/case.toml").exists()
    (source.parent.parent / "LICENSE").unlink()
    assert load_task(bound_case).input_assets()["license"].content == terms
    assert (root / "solver/materials/LICENSE").read_bytes() == terms
    assert (bound_case.parent / "reference.gds").read_bytes() == b"Maintainer-only witness"


def test_discovery_spans_collections_and_selects_hbt_support(preview, preview_case, monkeypatch):
    root, source = preview_case
    hbt = root / "tasks/ihp-sg13g2/TO_Apr2025/cases/hbt_synthetic"
    hbt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, hbt)
    config = (hbt / "case.toml").read_text().replace(
        'id = "synthetic-circuit"', 'id = "hbt-synthetic"')
    config = config.replace('support_profiles = {support = "analog-models"}',
                            'support_profiles = {support = "hbt-models"}')
    config += '''
[toolchain.backends.extraction]
type = "sg13g2-hbt-rc-docker"
support_profiles = {klayout_support = "klayout", magic_support = "magic"}
[toolchain.backends.extraction.settings]
image = "synthetic-image"
klayout_support = "source-klayout"
klayout_profile = "reviewed.json"
magic_support = "source-magic"
technology = "magic/ihp-sg13g2.tech"
tech_name = "ihp-sg13g2"
style = "ngspice()"
'''
    (hbt / "case.toml").write_text(config)

    candidate = root / "tasks/ihp-sg13g2/TO_Apr2025/cases/candidate_synthetic"
    shutil.copytree(source, candidate)
    config = (candidate / "case.toml").read_text().replace(
        'id = "synthetic-circuit"', 'id = "candidate-synthetic"')
    (candidate / "case.toml").write_text(config.replace(
        'status = "qualified"', 'status = "candidate"'))

    for collection, entries in {
        "IHP-AnalogAcademy": [("synthetic-circuit", "cases/synthetic/case.toml")],
        "TO_Apr2025": [("hbt-synthetic", "cases/hbt_synthetic/case.toml"),
                       ("candidate-synthetic", "cases/candidate_synthetic/case.toml")],
    }.items():
        catalog = root / "tasks/ihp-sg13g2" / collection / "catalog.toml"
        catalog.parent.mkdir(parents=True, exist_ok=True)
        body = "schema_version = 3\n\n" + "\n".join(
            f'[[cases]]\nid = "{case_id}"\nconfig_path = "{config_path}"\n'
            for case_id, config_path in entries)
        catalog.write_text(body)

    cases = preview.discover_cases()
    assert set(cases) == {"synthetic", "hbt_synthetic", "candidate_synthetic"}
    hbt_backend = cases["hbt_synthetic"]["data"]["toolchain"]["backends"]["simulation"]
    assert support_bindings("simulation", hbt_backend) == [("support", "hbt-models")]
    unbound_hbt = {**hbt_backend}
    unbound_hbt.pop("support_profiles")
    with pytest.raises(ValueError, match="support_profiles metadata"):
        support_bindings("simulation", unbound_hbt)
    assert preview._case_choices() == ("candidate_synthetic", "hbt_synthetic", "synthetic")

    identity = "sha256:" + "b" * 64
    monkeypatch.setattr(preview.subprocess, "check_output", lambda *args, **kwargs: identity + "\n")
    profiles = []

    def support(source, profile, output, *, compiler_image):
        profiles.append(profile)
        output.mkdir()

    monkeypatch.setattr(prepare_support, "prepare_support", support)
    preview.prepare(root / "candidate-prepared", "synthetic-tools:local", "candidate_synthetic")
    assert load_task(root / "candidate-prepared/case/case.toml").status == "candidate"
    profiles.clear()
    preview.prepare(root / "hbt-prepared", "synthetic-tools:local", "hbt_synthetic")
    assert {profile.rsplit("#", 1)[-1] for profile in profiles} == {"klayout", "magic", "hbt-models"}


def test_quickstart_rejects_unexecutable_selection_before_external_work(preview, preview_case, monkeypatch):
    root, source = preview_case
    config = source / "case.toml"
    config.write_text(config.read_text().replace('reference = "reference.gds"\n', ""))
    monkeypatch.setattr(preview, "call", lambda *args, **kwargs: pytest.fail("Must validate the case first"))
    with pytest.raises(ValueError, match="published witness"):
        preview.quickstart(root / "output", "tools", "host", False, "synthetic")
    assert not (root / "output").exists()


def test_other_process_prepares_declared_sources_without_local_support(preview, preview_case, monkeypatch):
    root, source = preview_case
    collection = root / "tasks/other-process/public"
    target = collection / "cases/synthetic"
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    (collection / "catalog.toml").write_text(
        '[[cases]]\nid = "other-synthetic"\nconfig_path = "cases/synthetic/case.toml"\n')
    upstream = root / "third_party/other-models"
    upstream.mkdir()
    content = b"Synthetic model source\n"
    (upstream / "model.lib").write_bytes(content)
    with (root / ".gitmodules").open("a") as stream:
        stream.write('[submodule "models"]\npath = third_party/other-models\nurl = https://example.test/models.git\n')
    metadata = tomllib.loads((root / "tasks/ihp-sg13g2/pdk.toml").read_text())
    for profile in metadata["profiles"].values():
        profile["source"] = {"checkout": "third_party/other-models"}
        profile["files"] = {"model.lib": {"path": "model.lib", "format": "spice",
                                            "sha256": hashlib.sha256(content).hexdigest(),
                                            "replace": [{"old": "Synthetic", "new": "Adapted"}]}}
    (collection.parent / "pdk.toml").write_text(tomli_w.dumps(metadata))
    monkeypatch.setattr(preview.subprocess, "check_output", lambda *args, **kwargs: "sha256:" + "a" * 64)
    commands = []
    monkeypatch.setattr(preview, "call", lambda *args: commands.append(args))
    # Update the selected process's declared checkout, never the unrelated IHP checkout.
    (upstream / ".git").write_text("gitdir: synthetic\n")
    key = "other-process/public/synthetic"
    preview.ensure_case_pdks(key)
    assert commands == [("git", "submodule", "update", "--init", "--depth", "1",
                         Path("third_party/other-models"))]
    assert not (root / "build/support").exists()
    destination = root / "prepared-other"
    preview.prepare(destination, "tools", key)
    bound = tomllib.loads((destination / "case/case.toml").read_text())
    for backend in bound["toolchain"]["backends"].values():
        support = Path(backend["settings"]["support"])
        assert support.is_relative_to(destination)
        assert (support / "model.lib").read_bytes() == b"Adapted model source\n"
    assert not (destination / "agent-resources").exists()
    # A declared adapter must match exactly once; changed upstream bytes cannot
    # silently turn a required unit/model correction into a no-op.
    for profile in metadata["profiles"].values():
        profile["files"]["model.lib"]["replace"][0]["old"] = "missing marker"
    (collection.parent / "pdk.toml").write_text(tomli_w.dumps(metadata))
    with pytest.raises(ValueError, match="exactly once"):
        preview.prepare(root / "bad-adapter", "tools", key)


@pytest.mark.parametrize("success", [True, False])
def test_reference_run_requires_actual_task_success(preview, preview_case, monkeypatch, success):
    root, source = preview_case
    prepared = root / "prepared"
    prepared.mkdir()
    source.rename(prepared / "case")

    def evaluate(*args, **kwargs):
        report_dir = Path(args[args.index("--output") + 1])
        report_dir.mkdir()
        (report_dir / "report.json").write_text(json.dumps({
            "outcome": "passed" if success else "failed", "task_success": success,
        }))

    monkeypatch.setattr(preview, "python", evaluate)
    output = root / "run"
    if not success:
        with pytest.raises(ValueError, match="complete evaluation"):
            preview.run(prepared, output)
        assert not (output / "preview.json").exists()
    else:
        preview.run(prepared, output)
        summary = json.loads((output / "preview.json").read_text())
        assert summary["reference"] == "passed" and summary["model_called"] is False


def test_existing_evidence_rejected_before_build_or_pdk_update(preview, tmp_path, monkeypatch):
    evidence = tmp_path / "run.json"
    evidence.write_text("retained evidence")
    monkeypatch.setattr(preview, "doctor", lambda: None)
    monkeypatch.setattr(preview, "_check_build_network", lambda network: None)
    monkeypatch.setattr(preview, "call", lambda *args, **kwargs: pytest.fail("Must not run preparation commands"))
    with pytest.raises(ValueError, match="Output already exists"):
        preview.quickstart(tmp_path, preview.IMAGE, "default", False)
    assert evidence.read_text() == "retained evidence"
