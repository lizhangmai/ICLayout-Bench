"""Support manifest refresh records the clean checkout's identity and nothing else."""

import hashlib
import subprocess
import tomllib

import pytest
import tomli_w

from benchmarking.refresh_support import refresh

pytestmark = pytest.mark.unit


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _make_checkout(root, files):
    root.mkdir()
    _git(root, "init", "-q")
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        _git(root, "add", name)
    _git(root, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-qm", "pin")
    return _git(root, "rev-parse", "HEAD")


def _manifest(path, profiles, stale):
    data = {"schema_version": 1,
            "source": {"repository": "https://example.invalid/pdk", "commit": "0" * 40},
            "profiles": {name: {"files": {file: {"path": file, "sha256": stale, "format": "text"}
                                          for file in files}}
                         for name, files in profiles.items()}}
    path.write_text(tomli_w.dumps(data))


def _sha256(content):
    # Independent calculation from the fixture bytes, not a copy of the manifest.
    return hashlib.sha256(content).hexdigest()


def test_refresh_records_head_and_recomputed_digests(tmp_path):
    files = {"decks/rules.drc": b"rules v2", "models/mos.lib": b"model v2"}
    commit = _make_checkout(tmp_path / "pdk", files)
    manifest = tmp_path / "ihp-sg13g2.toml"
    _manifest(manifest, {"klayout": list(files), "magic": []}, stale="f" * 64)
    changes = refresh(tmp_path / "pdk", manifest)
    assert changes["commit"] == ("0" * 40, commit)
    assert set(changes["digests"]) == {f"klayout:{name}" for name in files}
    data = tomllib.loads(manifest.read_text())
    assert data["source"]["repository"] == "https://example.invalid/pdk"
    assert data["source"]["commit"] == commit
    for name, content in files.items():
        assert data["profiles"]["klayout"]["files"][name]["sha256"] == _sha256(content)


def test_refresh_scopes_to_the_named_profile(tmp_path):
    files = {"decks/rules.drc": b"rules"}
    _make_checkout(tmp_path / "pdk", files)
    manifest = tmp_path / "ihp-sg13g2.toml"
    _manifest(manifest, {"klayout": list(files), "magic": list(files)}, stale="f" * 64)
    changes = refresh(tmp_path / "pdk", manifest, profile="klayout")
    assert changes["digests"] == ["klayout:decks/rules.drc"]
    data = tomllib.loads(manifest.read_text())
    assert data["profiles"]["klayout"]["files"]["decks/rules.drc"]["sha256"] == _sha256(b"rules")
    assert data["profiles"]["magic"]["files"]["decks/rules.drc"]["sha256"] == "f" * 64


def test_refresh_is_idempotent_on_a_matching_manifest(tmp_path):
    _make_checkout(tmp_path / "pdk", {"decks/rules.drc": b"rules"})
    manifest = tmp_path / "ihp-sg13g2.toml"
    _manifest(manifest, {"klayout": ["decks/rules.drc"]}, stale="f" * 64)
    refresh(tmp_path / "pdk", manifest)
    frozen = manifest.read_bytes()
    assert refresh(tmp_path / "pdk", manifest)["digests"] == []
    assert manifest.read_bytes() == frozen


def test_refresh_refuses_a_dirty_checkout(tmp_path):
    files = {"decks/rules.drc": b"rules"}
    _make_checkout(tmp_path / "pdk", files)
    (tmp_path / "pdk/decks/rules.drc").write_bytes(b"local experiment")
    manifest = tmp_path / "ihp-sg13g2.toml"
    _manifest(manifest, {"klayout": list(files)}, stale="f" * 64)
    with pytest.raises(ValueError, match="uncommitted changes"):
        refresh(tmp_path / "pdk", manifest)
    files_after = tomllib.loads(manifest.read_text())["profiles"]["klayout"]["files"]
    assert files_after["decks/rules.drc"]["sha256"] == "f" * 64


def test_refresh_refuses_a_missing_source_file(tmp_path):
    _make_checkout(tmp_path / "pdk", {"decks/rules.drc": b"rules"})
    manifest = tmp_path / "ihp-sg13g2.toml"
    _manifest(manifest, {"klayout": ["decks/gone.drc"]}, stale="f" * 64)
    with pytest.raises(OSError):
        refresh(tmp_path / "pdk", manifest)
    files_after = tomllib.loads(manifest.read_text())["profiles"]["klayout"]["files"]
    assert files_after["decks/gone.drc"]["sha256"] == "f" * 64



def test_case_attribution_cannot_be_refreshed_from_a_checkout(circuit_case, tmp_path):
    frozen = circuit_case.read_bytes()
    with pytest.raises(ValueError):
        refresh(tmp_path / "unavailable-upstream", circuit_case)
    assert circuit_case.read_bytes() == frozen
