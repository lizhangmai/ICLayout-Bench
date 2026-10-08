"""Evaluation dependency ordering and source/candidate graph correspondence."""

import re

from .contracts import Job, identifier


def _order_jobs(jobs):
    # Data dependencies also impose ordering; explicit requires is useful for
    # checks that produce evidence but no downstream circuit artifact.
    ordered = []
    pending = dict(jobs)
    ancestors: dict[str, set[str]] = {}
    data_ancestors: dict[str, set[str]] = {}
    dependencies = {}
    data_dependencies = {}
    for job in jobs.values():
        deps = set(job.requires)
        producers = set()
        for _, ref in job.inputs:
            parts = ref.split(":")
            if ref in {"candidate", "task"}:
                continue
            if len(parts) == 2 and parts[0] == "input":
                identifier(parts[1])
                continue
            if len(parts) != 3 or parts[0] != "job" or parts[1] not in jobs:
                raise ValueError(f"Unknown input reference: {ref}")
            if parts[2] not in dict(jobs[parts[1]].outputs):
                raise ValueError(f"Unknown job output: {ref}")
            producers.add(parts[1])
        deps |= producers
        if not deps <= jobs.keys():
            raise ValueError(f"Unknown job dependency in {job.id}")
        dependencies[job.id], data_dependencies[job.id] = deps, producers
    while pending:
        ready = [job for job in pending.values() if dependencies[job.id] <= ancestors.keys()]
        if not ready:
            raise ValueError("Evaluation dependency cycle")
        for job in ready:
            deps, producers = dependencies[job.id], data_dependencies[job.id]
            ancestors[job.id] = deps | set().union(*(ancestors[x] for x in deps))
            data_ancestors[job.id] = producers | set().union(*(data_ancestors[x] for x in producers))
            ordered.append(Job(job.id, job.stage, job.operation, job.inputs, job.outputs,
                               tuple(sorted(deps)), job.gate, job.parameters_json))
            del pending[job.id]

    return ordered, ancestors, data_ancestors


def _validate_source_graph(sources):
    """Bind source-only intermediate artifacts without exposing them as inputs."""
    visited, active = set(), set()

    def visit(name):
        if name in active:
            raise ValueError("Pre-layout dependency cycle")
        if name in visited:
            return
        active.add(name)
        source = sources[name]
        digests = source.get("output_sha256", {})
        if not isinstance(digests, dict) or not digests.keys() <= source["outputs"].keys():
            raise ValueError("Invalid pre-layout output identities")
        for role, digest in digests.items():
            identifier(role)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Invalid pre-layout output digest")
        has_circuit = bool({"input:netlist", "input:simulation"} & set(source["inputs"].values()))
        for role, ref in source["inputs"].items():
            if ref.startswith("input:"):
                continue
            _, producer, output = ref.split(":")
            if producer not in sources or output not in sources[producer]["outputs"]:
                raise ValueError("Pre-layout must be independent of the candidate")
            visit(producer)
            if sources[producer].get("output_sha256", {}).get(output) != source["input_sha256"][role]:
                raise ValueError("Pre-layout intermediate input digest mismatch")
            has_circuit = True
        if not has_circuit:
            raise ValueError("Pre-layout must consume the declared source circuit")
        active.remove(name)
        visited.add(name)

    for name in sources:
        visit(name)



def _source_pair_matches(source_name, candidate_name, sources, jobs):
    source, candidate = sources[source_name], jobs[candidate_name]
    if source["operation"] != candidate.operation or source["parameters"] != candidate.parameters:
        return False
    candidate_inputs = dict(candidate.inputs)
    if source["inputs"].keys() != candidate_inputs.keys():
        return False
    for role, ref in source["inputs"].items():
        paired = candidate_inputs[role]
        if ref in {"input:netlist", "input:simulation"} and paired.startswith("job:"):
            _, producer, output = paired.split(":")
            if (jobs[producer].stage != "extract"
                    or dict(jobs[producer].outputs)[output] != "spice"):
                return False
            continue
        if ref.startswith("job:") and paired.startswith("job:"):
            _, producer, output = ref.split(":")
            _, paired_producer, paired_output = paired.split(":")
            if output != paired_output:
                return False
            if not _source_pair_matches(producer, paired_producer, sources, jobs):
                return False
            if sources[producer]["outputs"][output] != dict(jobs[paired_producer].outputs)[paired_output]:
                return False
        elif ref != paired:
            return False
    return True
