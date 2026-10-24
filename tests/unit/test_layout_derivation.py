import json

import pytest

from benchmarking.eda.layout_derivation import (
    validate_derived_model,
    validate_layout_derivation,
)
from benchmarking.files import Asset

pytestmark = pytest.mark.unit


def test_fixed_macro_binding_rejects_changed_candidate_cut_and_top():
    original, cut = Asset(b"original layout", "gds"), Asset(b"verified cut layout", "gds")
    binding = {"kind": "fixed-macro-abstraction-v1", "top_cell": "DUT",
        "candidate_sha256": original.sha256, "cut_sha256": cut.sha256,
        "library_sha256": "a" * 64, "specification_sha256": "b" * 64, "macros": []}
    inputs = {"layout": cut, "original": original,
        "binding": Asset(json.dumps(binding).encode(), "json"),
        "task": Asset(json.dumps({"output": {"top_cell": "DUT"}}).encode(), "json")}
    assert validate_layout_derivation(inputs) == {"layout_derivation": inputs["binding"]}
    for name, replacement in (("original", Asset(b"different original", "gds")),
                              ("layout", Asset(b"different cut", "gds")),
                              ("task", Asset(b'{"output":{"top_cell":"OTHER"}}', "json"))):
        with pytest.raises(ValueError, match="differs"):
            validate_layout_derivation({**inputs, name: replacement})
    with pytest.raises(ValueError, match="both original candidate and binding"):
        validate_layout_derivation({k: v for k, v in inputs.items() if k != "binding"})
    assert validate_layout_derivation({"layout": original}) == {}


def test_uniform_line_binding_preserves_candidate_and_parent_lineage():
    original, cut = Asset(b"original line layout", "gds"), Asset(b"cut line layout", "gds")
    binding = {"kind": "uniform-line-abstraction-v1", "top_cell": "DUT",
        "candidate_sha256": original.sha256, "cut_sha256": cut.sha256,
        "process_sha256": "a" * 64, "specification_sha256": "b" * 64,
        "netlist_sha256": "d" * 64,
        "parent_binding_sha256": "c" * 64, "line": {"length_um": 40}}
    inputs = {"layout": cut, "original": original,
        "binding": Asset(json.dumps(binding).encode(), "json")}
    assert validate_layout_derivation(inputs) == {"layout_derivation": inputs["binding"]}
    with pytest.raises(ValueError, match="differs"):
        validate_layout_derivation({**inputs, "original": Asset(b"edited line", "gds")})
    del binding["parent_binding_sha256"]
    with pytest.raises(ValueError):
        validate_layout_derivation({**inputs, "binding": Asset(json.dumps(binding).encode(), "json")})


def test_only_the_verified_geometry_model_can_supplement_extraction():
    model = Asset(b".subckt LINE A B REF\nR1 A B 1\n.ends\n", "spice")
    proof = Asset(json.dumps({"kind": "uniform-line-abstraction-v1",
        "netlist_sha256": model.sha256}).encode(), "json")
    assert validate_derived_model(proof, model) == {"modeled_circuit": model}
    assert validate_derived_model(None, None) == {}
    for replacement in (None, Asset(b"changed model", "spice"), Asset(model.content, "text")):
        with pytest.raises(ValueError, match="differs"):
            validate_derived_model(proof, replacement)
    with pytest.raises(ValueError, match="requires a verified"):
        validate_derived_model(None, model)
