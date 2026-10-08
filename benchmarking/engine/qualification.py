"""Run one reference evaluation and verify its retained input bindings."""

import argparse
import json
import tempfile
from contextlib import nullcontext
from pathlib import Path

from benchmarking.dataset import load_dataset
from benchmarking.files import atomic_write, read_file
from benchmarking.protocol import json_bytes

from .evaluate import run_evaluation
from .runtime import load_case, load_case_inputs


def retained_report(report):
    """Keep conclusions and evaluation inputs, leaving run artifacts in scratch."""
    return {
        "outcome": report["outcome"],
        "physical_valid": report["physical_valid"],
        "specs_pass": report["specs_pass"],
        "task_success": report["task_success"],
        "score": report["score"],
        "inputs": {name: value["sha256"] for name, value in report["inputs"].items()
                   if name != "task"},
        "jobs": {name: {"status": job["status"], "measurements": job["measurements"]}
                 for name, job in report["jobs"].items()},
        "metrics": report["metrics"],
    }


def audit(plan):
    """Classify the contract before spending resources on a reference run."""
    legacy = [m.id for m in plan.metrics if m.is_requirement and not m.requirement_rationale]
    if legacy:
        raise ValueError(
            "Qualification contract review required: implicit lower/upper bounds on "
            + ", ".join(legacy[:8]) + (f" (and {len(legacy) - 8} more)" if len(legacy) > 8 else "")
            + ". Remove performance cutoffs; put necessary functional bounds in "
            "requirement = {lower/upper, rationale}. Review the contract before changing the reference.")
    weights = dict(plan.scoring.weights) if plan.scoring else {}
    return {
        "requirements": {m.id: {"lower": m.lower, "upper": m.upper,
                                 "rationale": m.requirement_rationale}
                         for m in plan.metrics if m.is_requirement},
        "quality": {m.id: weights[m.id] for m in plan.metrics if weights.get(m.id, 0) > 0},
        "diagnostics": [m.id for m in plan.metrics
                        if not m.is_requirement and weights.get(m.id, 0) == 0],
        "minimum_score": None,
    }


def verify(runtime, directory):
    """Check a retained passing run against current reference and input bytes."""
    record = json.loads(read_file(directory, "qualification.json"))
    task = runtime.task
    if record.get("format") != "single-evaluation":
        raise ValueError("Unknown qualification format")
    report = record["report"]
    inputs = task.evaluation_inputs()
    expected_refs = task.evaluation.external_inputs()
    if "candidate" not in expected_refs:
        raise ValueError("Qualification plan does not evaluate a candidate")
    if set(report["inputs"]) != expected_refs - {"task"}:
        raise ValueError("Qualification evaluation inputs differ")
    witness = runtime.witness()
    for ref in expected_refs - {"task"}:
        expected = witness if ref == "candidate" else inputs[ref]
        if report["inputs"][ref] != expected.sha256:
            raise ValueError(f"Qualification input changed: {ref}")
    if (report["outcome"] != "passed" or report["task_success"] is not True
            or not report["jobs"]
            or any(job["status"] != "passed" for job in report["jobs"].values())):
        raise ValueError("Qualification did not pass its recorded plan")
    return record


def run(runtime, output, *, retain_evaluation=False):
    """Evaluate a witness, optionally retaining raw evidence even on failure."""
    output = Path(output).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    review = audit(runtime.task.evaluation)
    witness = runtime.witness()
    storage = (nullcontext(output) if retain_evaluation else
               tempfile.TemporaryDirectory(prefix="qualification-run-"))
    with storage as temporary:
        report = run_evaluation(
            runtime.task.evaluation,
            {**runtime.task.evaluation_inputs(), "candidate": witness},
            runtime.backends, Path(temporary) / "evaluation",
            task_sha256=runtime.task.digest, task_witnessed=runtime.task.witnessed,
        )
        if report["outcome"] != "passed" or report["task_success"] is not True:
            failures = {
                "requirements": [name for name, metric in report["metrics"].items()
                                 if metric["status"] == "failed"],
                "jobs": {name: {"status": job["status"], "reason": job.get("reason")}
                         for name, job in report["jobs"].items() if job["status"] in {"failed", "error"}},
                "measurement_errors": [name for name, metric in report["metrics"].items()
                                       if metric["status"] == "error"],
                "scoring_error": report.get("scoring_error"),
            }
            raise ValueError("Qualification did not pass the complete plan: " + json.dumps(failures)
                             + ". Diagnose contract, measurements and tools before changing the reference; "
                             "low performance alone is not a qualification failure.")
        record = {
            "format": "single-evaluation",
            "report": retained_report(report),
            "contract_review": review,
        }
        output.mkdir(parents=True, exist_ok=retain_evaluation)
        atomic_write(output / "qualification.json", json_bytes(record))
        verify(runtime, output)
        return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "run", "verify"))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--case")
    parser.add_argument("--image", default="iclayout-eda-open:local", help="Tool image for run")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--retain-evaluation", action="store_true",
                        help="Keep full evaluation artifacts under output/evaluation, including failed runs")
    args = parser.parse_args(argv)
    if args.retain_evaluation and args.action != "run":
        parser.error("--retain-evaluation requires run")
    dataset = load_dataset(args.dataset, revision=args.revision, include_reference=True)
    if args.action == "audit":
        if not args.case or args.output:
            parser.error("audit requires --case and no --output")
        runtime = load_case_inputs(dataset.case(args.case))
        print(json.dumps(audit(runtime.task.evaluation), indent=2))
        return
    if not args.case or not args.output:
        parser.error("run/verify require --case and --output")
    case = dataset.case(args.case)
    if args.action == "run":
        runtime = load_case(case, image=args.image)
        run(runtime, args.output, retain_evaluation=args.retain_evaluation)
    else:
        runtime = load_case_inputs(case)
        verify(runtime, args.output)
    print(f"PASS: {runtime.task.id}; qualification: {args.output}")


if __name__ == "__main__":
    main()
