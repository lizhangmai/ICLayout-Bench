import json

import pytest

from benchmarking.eda.layout_derivation import validate_layout_derivation
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


def test_unknown_layout_derivation_is_rejected():
    original, cut = Asset(b"original layout", "gds"), Asset(b"derived layout", "gds")
    binding = {"kind": "unsupported-abstraction", "top_cell": "DUT",
        "candidate_sha256": original.sha256, "cut_sha256": cut.sha256,
        "specification_sha256": "b" * 64}
    inputs = {"layout": cut, "original": original,
        "binding": Asset(json.dumps(binding).encode(), "json")}
    with pytest.raises(ValueError, match="Unknown derived-layout binding"):
        validate_layout_derivation(inputs)
