"""Bind verified fixed-macro abstractions to the frozen candidate layout."""

import json

from benchmarking.files import keys


def validate_layout_derivation(inputs):
    """Require the original and cut digests together; retain the trusted proof.

    Callers still perform their ordinary native checks on ``layout``. The
    original candidate remains an explicit input for the physical gate and
    extraction lineage. A task must produce this binding through the installed
    immutable-macro verifier before either downstream operation can run.
    """
    if not {"original", "binding"} & inputs.keys():
        return {}
    if not {"original", "binding"} <= inputs.keys():
        raise ValueError("Derived layout requires both original candidate and binding")
    if inputs["original"].format != "gds" or inputs["binding"].format != "json":
        raise ValueError("Derived layout requires original GDS and JSON binding")
    binding = json.loads(inputs["binding"].content)
    common = {"kind", "top_cell", "candidate_sha256", "cut_sha256", "specification_sha256"}
    variants = {"fixed-macro-abstraction-v1": {"library_sha256", "macros"},
                "uniform-line-abstraction-v1": {"process_sha256", "parent_binding_sha256", "netlist_sha256", "line"}}
    if binding.get("kind") not in variants:
        raise ValueError("Unknown derived-layout binding")
    keys(binding, common | variants[binding["kind"]], set(), "layout abstraction binding")
    if (binding["candidate_sha256"] != inputs["original"].sha256
            or binding["cut_sha256"] != inputs["layout"].sha256):
        raise ValueError("Derived layout binding differs from the frozen candidate or cut GDS")
    if "task" in inputs and binding["top_cell"] != json.loads(inputs["task"].content)["output"]["top_cell"]:
        raise ValueError("Derived layout top cell differs from the task")
    return {"layout_derivation": inputs["binding"]}


def validate_derived_model(derivation, model):
    """Bind geometry-derived circuit elements to their verified extraction."""
    binding = json.loads(derivation.content) if derivation is not None else {}
    needs_model = binding.get("kind") == "uniform-line-abstraction-v1"
    if needs_model:
        if model is None or model.format != "spice" or model.sha256 != binding["netlist_sha256"]:
            raise ValueError("Geometry-derived model differs from the verified line extraction")
        return {"modeled_circuit": model}
    if model is not None:
        raise ValueError("Additional circuit model requires a verified geometry derivation")
    return {}
