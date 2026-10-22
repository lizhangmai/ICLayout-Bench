"""Task inspection and configurable independent evaluation."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from benchmarking.eda.runtime import load_case, load_case_inputs
from benchmarking.eda.toolchain import load_toolchain, load_toolchain_spec
from benchmarking.evaluation.contracts import identifier
from benchmarking.evaluation.plans import parse_evaluation
from benchmarking.evaluation.runner import run_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.tasks.contract import load_task
from benchmarking.tasks.dataset import load_dataset


def main(argv=None) -> None:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments[:1] == ["qualify"]:
        return qualification_main(arguments[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    task_parser = subcommands.add_parser("task", help="Validate a task and show its I/O")
    task_parser.add_argument("config", type=Path, help="Path to a task or unified case TOML")
    task_parser.add_argument("--materialize", type=Path, help="New directory for verified inputs")
    evaluate_parser = subcommands.add_parser("evaluate", help="Evaluate a GDS with a task's declared plan")
    evaluate_parser.add_argument("config", type=Path)
    evaluate_parser.add_argument("candidate", type=Path)
    characterize_parser = subcommands.add_parser("characterize", help="Run a standalone measurement plan; no layout score")
    characterize_parser.add_argument("plan", type=Path)
    characterize_parser.add_argument("--input", action="append", default=[], metavar="ROLE:FORMAT=PATH")
    for command in (evaluate_parser, characterize_parser):
        command.add_argument("--toolchain", type=Path, required=command is characterize_parser,
                             help="Toolchain or case TOML; evaluate defaults to the case's [toolchain]")
        command.add_argument("--output", type=Path, required=True, help="New directory for report and evidence")
        command.add_argument("--image", default=os.environ.get("ICLAYOUT_BENCH_IMAGE"),
                             help="Tool image override; also accepts ICLAYOUT_BENCH_IMAGE")
    subcommands.add_parser("qualify", help="Audit, run or verify author reference qualification")
    args = parser.parse_args(arguments)
    try:
        if args.command == "task":
            task = load_task(args.config)
            if args.materialize:
                task.materialize(args.materialize)
            print(json.dumps(task.description(), ensure_ascii=False, indent=2))
            return
        toolchain_path = args.toolchain if args.toolchain is not None else args.config
        task_digest = None
        if args.command == "evaluate":
            task = load_task(args.config)
            plan = task.evaluation
            if plan is None or plan.mode == "characterization":
                raise ValueError("Task needs a physical or post_layout evaluation plan")
            candidate = args.candidate.absolute()
            if candidate.stat().st_size > task.output.max_bytes:
                raise ValueError("Candidate exceeds the configured GDS size limit")
            inputs = task.evaluation_inputs()
            inputs["candidate"] = Asset(read_file(candidate.parent, candidate.name), "gds")
            task_digest = task.digest
        else:
            path = args.plan.absolute()
            plan = parse_evaluation(read_file(path.parent, path.name))
            if plan.mode != "characterization":
                raise ValueError("characterize requires mode = 'characterization'")
            inputs = {}
            for argument in args.input:
                name, separator, path = argument.partition("=")
                role, colon, file_format = name.partition(":")
                if not separator or not colon or not path or not file_format:
                    raise ValueError("--input requires ROLE:FORMAT=PATH")
                ref = f"input:{identifier(role)}"
                if ref in inputs:
                    raise ValueError(f"Duplicate input: {role}")
                source = Path(path).absolute()
                inputs[ref] = Asset(read_file(source.parent, source.name), file_format)
        spec = load_toolchain_spec(toolchain_path)
        if spec.embedded and any(backend.support_profiles or 'runtime' in backend.settings
                                 for backend in spec.backends.values()):
            backends = load_case(toolchain_path, image=args.image, include_agent=False).backends
        else:
            backends = load_toolchain(toolchain_path, **({'image': args.image} if args.image else {}))
        report = run_evaluation(plan, inputs, backends, args.output,
                                task_sha256=task_digest,
                                task_witnessed=task.witnessed if args.command == "evaluate" else None)
    except (TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"ICLayout-Bench command failed: {error}\n")
    summary = {"report": str(args.output / "report.json"), **{
        key: report[key] for key in ("mode", "outcome", "physical_valid", "specs_pass", "task_success", "metrics")
    }}
    if args.command == "evaluate":
        summary["task_witnessed"] = report["task_witnessed"]
    if report.get("score") is not None:
        summary["score"] = {key: report["score"].get(key)
                            for key in ("method", "value", "maximum", "reference", "components")
                            if key in report["score"]}
    print(json.dumps(summary, indent=2, allow_nan=False))
    if report["outcome"] != "passed":
        parser.exit(1 if report["outcome"] == "failed" else 2)

def qualification_main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit", "run", "verify"))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--case")
    parser.add_argument("--image", help="Tool image override; defaults to the external runtime or open EDA image")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--retain-evaluation", action="store_true",
                        help="Keep full evaluation artifacts under output/evaluation, including failed runs")
    args = parser.parse_args(argv)
    if args.retain_evaluation and args.action != "run":
        parser.error("--retain-evaluation requires run")
    from benchmarking.evaluation.qualification import audit, run, verify

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
