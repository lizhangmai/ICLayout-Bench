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
    if binding.get("kind") != "fixed-macro-abstraction-v1":
        raise ValueError("Unknown derived-layout binding")
    keys(binding, common | {"library_sha256", "macros"}, set(), "layout abstraction binding")
    if (binding["candidate_sha256"] != inputs["original"].sha256
            or binding["cut_sha256"] != inputs["layout"].sha256):
        raise ValueError("Derived layout binding differs from the frozen candidate or cut GDS")
    if "task" in inputs and binding["top_cell"] != json.loads(inputs["task"].content)["output"]["top_cell"]:
        raise ValueError("Derived layout top cell differs from the task")
    return {"layout_derivation": inputs["binding"]}
