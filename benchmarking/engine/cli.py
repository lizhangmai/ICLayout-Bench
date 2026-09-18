"""Task inspection and configurable independent evaluation."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from benchmarking.benchmark import load_benchmark
from benchmarking.engine.evaluate import run_evaluation
from benchmarking.engine.inference import (
    load_inference_config,
    validate_harness_wire,
)
from benchmarking.engine.model_config import load_run_config
from benchmarking.engine.recorder import recover_submissions
from benchmarking.engine.toolchains import load_toolchain
from benchmarking.evaluation import identifier, parse_evaluation
from benchmarking.files import Asset, read_file
from benchmarking.tasks import load_task


def _inference_preflight(profile, config, credential_present):
    """Describe a model profile without making a provider request."""
    return {
        "status": "ready" if credential_present else "missing_credential",
        "model_call": False,
        "endpoint": profile.base_url,
        "model": profile.model,
        "wire_api": profile.wire_api,
        "credential_env": profile.api_key_env,
        "credential_present": credential_present,
        "harness": config.harness.identity() if config else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    benchmark_parser = subcommands.add_parser("benchmark", help="Validate a versioned benchmark and list its cases")
    benchmark_parser.add_argument("config", type=Path)
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
    recover_parser = subcommands.add_parser("recover", help="Verify durable submissions without resuming or scoring a run")
    recover_parser.add_argument("directory", type=Path)
    inference_parser = subcommands.add_parser(
        "inference-check", help="Validate an inference profile and host credential without making a model call"
    )
    inference_parser.add_argument("profile", type=Path)
    inference_parser.add_argument("--agent", type=Path, help="Optional harness configuration to check wire compatibility")
    args = parser.parse_args()
    try:
        if args.command == "benchmark":
            benchmark = load_benchmark(args.config)
            print(json.dumps({**benchmark.description(), "contracts": benchmark.contracts}, indent=2))
            return
        if args.command == "recover":
            print(json.dumps(recover_submissions(args.directory), indent=2, allow_nan=False))
            return
        if args.command == "inference-check":
            profile = load_inference_config(args.profile)
            config = load_run_config(args.agent) if args.agent else None
            if config:
                validate_harness_wire(config.harness.wire_api, profile.wire_api)
            result = _inference_preflight(profile, config, bool(os.environ.get(profile.api_key_env)))
            print(json.dumps(result, indent=2, allow_nan=False))
            if not result["credential_present"]:
                parser.exit(1)
            return
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
        report = run_evaluation(plan, inputs, load_toolchain(toolchain_path), args.output,
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


if __name__ == "__main__":
    main()
