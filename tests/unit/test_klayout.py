import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarking.eda.backends.klayout import KLayoutDocker, validate_drc_waivers
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


@pytest.fixture
def native_support(monkeypatch):
    from benchmarking.eda.backends import klayout

    support = SimpleNamespace(files=(('rules.drc', Asset(b'# native rules\n', 'text')),
                                     ('rules.lvs', Asset(b'# native rules\n', 'text'))))
    monkeypatch.setattr(klayout, 'load_bundle', lambda path: support)
    monkeypatch.setattr(klayout, 'DockerTool', lambda *args: SimpleNamespace(identity={}))
    return support


def test_native_rule_settings_need_no_json_resource(native_support):
    backend = KLayoutDocker(image='tools', check='drc', support='prepared', deck='rules.drc',
                            variables={'variant': 'D'}, required_categories=['width'])
    assert backend.settings['deck'] == 'rules.drc'
    assert backend.settings['variables'] == {'variant': 'D'}
    assert backend.settings['required_categories'] == ['width']


@pytest.mark.parametrize('settings,match', [
    ({'deck': '../rules.drc', 'required_categories': ['width']}, 'relative'),
    ({'deck': 'missing.drc', 'required_categories': ['width']}, 'Missing'),
    ({'deck': 'rules.drc', 'required_categories': []}, 'unique report category'),
    ({'deck': 'rules.drc', 'required_categories': ['width'],
      'variables': {'input': 'candidate.gds'}}, 'reserved'),
    ({'deck': 'rules.drc', 'profile': 'drc.json'}, 'cannot mix'),
])
def test_direct_rule_settings_preserve_validation(native_support, settings, match):
    with pytest.raises(ValueError, match=match):
        KLayoutDocker(image='tools', check='drc', support='prepared', **settings)


def test_drc_waiver_schema_keeps_case_local_marker_scope():
    waivers = validate_drc_waivers([{
        "category": "'NBL.b'",
        "cell": "DIFF_COMPARATOR",
        "markers": ["edge-pair: marker-a", "edge-pair: marker-b"],
        "reason": "Known upstream ring construction",
    }])
    assert waivers == [{
        "category": "'NBL.b'",
        "cell": "DIFF_COMPARATOR",
        "markers": ["edge-pair: marker-a", "edge-pair: marker-b"],
        "reason": "Known upstream ring construction",
    }]


def test_drc_waiver_schema_rejects_duplicate_marker_across_entries():
    entry = {
        "category": "'NBL.b'",
        "cell": "DIFF_COMPARATOR",
        "markers": ["edge-pair: marker"],
        "reason": "Known upstream ring construction",
    }
    with pytest.raises(ValueError, match="Duplicate"):
        validate_drc_waivers([entry, dict(entry)])


@pytest.mark.parametrize("primary,extra,expected", [
    ("passed", "failed", "failed"),
    ("failed", "error", "error"),
    ("passed", "passed", "passed"),
])
def test_all_drc_decks_contribute_to_one_gate(monkeypatch, primary, extra, expected):
    # Exercise orchestration without substituting a real rule-check result.
    monkeypatch.setitem(sys.modules, "klayout", SimpleNamespace(db=None, rdb=None))
    module = runpy.run_path(str(Path(__file__).resolve().parents[2] / "benchmarking/eda/_scripts/klayout_runner.py"))
    main = module["main"]
    monkeypatch.setitem(main.__globals__, "artifact", lambda config: "")
    calls = []

    def run_deck(config, suffix, used):
        calls.append((config["deck"], suffix))
        status = {"main.drc": primary, "extra.drc": extra}[config["deck"]]
        count = int(status == "failed")
        return status, "test failure" if status != "passed" else "", {
            "violations": count, "unwaived_violations": count,
            "waived_violations": 0, "by_category": {"rule": count},
            "unwaived_by_category": {"rule": count},
        }

    monkeypatch.setitem(main.__globals__, "run_deck", run_deck)
    status, _, details = main({"check": "drc", "deck": "main.drc", "required_categories": ["rule"],
                              "additional_decks": [{"deck": "extra.drc", "required_categories": ["rule"]}]})
    assert {deck for deck, _ in calls} == {"main.drc", "extra.drc"}
    assert status == expected
    assert details["violations"] == int(primary == "failed") + int(extra == "failed")
    assert len({entry["report"] for entry in details["decks"]}) == len(calls)
