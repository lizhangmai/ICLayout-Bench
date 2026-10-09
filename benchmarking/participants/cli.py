"""Command line interface for participant experiment runs."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from . import batch, case, scheduler
from .planning import ExperimentRequest, plan_conditions, prepare_batch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--config", type=Path, nargs="+", help="TOML files with explicit experiment conditions")
    inputs.add_argument("--matrix", type=Path, help="TOML [defaults] and [[runs]] combinations")
    parser.add_argument("--case", action="append", help="Select a configured case by full ID or unique final name; repeat for multiple cases")
    parser.add_argument("--repetitions", type=int, help="Override repetitions for this invocation")
    parser.add_argument("--concurrency", type=int, help="Override concurrent sessions for this invocation")
    parser.add_argument("--dataset", help="HF Dataset repo ID or local Dataset directory")
    parser.add_argument("--revision", help="HF dataset revision (resolved to a fixed commit)")
    parser.add_argument("--offline", action="store_true", help="Use only the Hugging Face cache")
    parser.add_argument("--image", default=os.environ.get("ICLAYOUT_BENCH_IMAGE") or "iclayout-eda-open:local")
    parser.add_argument("--endpoint", default=os.environ.get("ICLAYOUT_BENCH_ENDPOINT"))
    parser.add_argument("--token-env", default="ICLAYOUT_BENCH_TOKEN")
    parser.add_argument("--output", type=Path, default=os.environ.get("ICLAYOUT_BENCH_OUTPUT") or None,
                        help="Condition directory (requires one condition); default: results/<config-stem>/<timestamp>")
    parser.add_argument("--results-data", type=Path, default=os.environ.get("ICLAYOUT_BENCH_RESULTS_DATA"),
                        help="Copy terminal results to this database/archive; indexing failures stay queued")
    parser.add_argument("--resume", action="store_true", help="Recover the batch at --output without replacing attempts")
    parser.add_argument("--replace-unfinished", action="store_true",
                        help="Explicitly replace selected unfinished cases, retaining old attempts and solve conditions")
    parser.add_argument("--collect-only", action="store_true",
                        help="Settle existing sessions at --output without launching models or changing their identity")
    parser.add_argument("--dry-run", action="store_true", help="Resolve combinations without service/model calls")
    parser.add_argument("--detach", action="store_true", help="Run one condition in an independent coordinator; print its PID and log")
    parser.add_argument("--status", action="store_true", help="Read scheduling state at --output without model or service calls")
    args = parser.parse_args(argv)
    try:
        if args.status:
            if not args.output or args.config or args.matrix or args.resume or args.replace_unfinished or args.dry_run or args.detach or args.collect_only:
                raise ValueError('--status requires --output and no execution options')
            print(json.dumps(scheduler.status(args.output), indent=2))
            return 0
        if args.detach and (args.collect_only or args.dry_run):
            raise ValueError('--detach cannot be combined with --collect-only or --dry-run')
        if args.collect_only:
            if not args.output or args.config or args.matrix or args.resume or args.replace_unfinished or args.dry_run:
                raise ValueError("--collect-only requires --output and no config, matrix, resume or dry-run")
            return case.collect_batch(case.CollectRequest(args.output, args.case, args.results_data))
        request = ExperimentRequest(**{key: getattr(args, key) for key in ExperimentRequest.__dataclass_fields__})
        experiment = plan_conditions(request)
        if args.dry_run:
            print(json.dumps([dict(c.description(), **({"results_data": c.row["results_data"]}
                              if "results_data" in c.row else {}))
                              for c in experiment.conditions], indent=2, ensure_ascii=False))
            return 0
        options, slots = prepare_batch(request, experiment)
        if args.detach:
            if len(slots) != 1:
                raise ValueError('--detach requires exactly one condition')
            return scheduler.detach(options, slots[0])
        code = 0
        blocked = set()
        for slot in slots:
            code = max(code, batch.execute_condition(options, slot.planned.row, slot.planned.selection,
                                                    slot.output, slot.identity, blocked))
        return code
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
