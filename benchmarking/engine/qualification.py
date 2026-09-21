"""Qualify a Dataset witness through direct, participant-check and final evaluation."""

import argparse
import hashlib
import json
import math
import re
import secrets
import shlex
import threading
from pathlib import Path

from benchmarking.client import Client
from benchmarking.dataset import load_dataset, process_manifest
from benchmarking.files import atomic_write, read_file
from benchmarking.participants.bridge import Bridge
from benchmarking.protocol import json_bytes

from .evaluate import run_evaluation
from .identity import evaluation_identity
from .runtime import load_case


def participant_identity():
    """Code that transports, freezes and checks a participant candidate."""
    root = Path(__file__).resolve().parents[1]
    paths = ("client.py", "protocol.py", "harnesses.py", "participants/bridge.py",
             "service/server.py", "engine/execution.py", "engine/session.py",
             "engine/snapshot.py", "engine/workspace.py", "engine/process_check.py",
             "engine/qualification.py")
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}


def verdict(report):
    """Exact acceptance decisions; numerical repeatability is recorded separately."""
    return {**{key: report[key] for key in (
        "outcome", "physical_valid", "specs_pass", "task_success")},
        "jobs": {name: job["status"] for name, job in report["jobs"].items()},
        "metrics": {name: metric["status"] for name, metric in report["metrics"].items()}}


def repeatability(reports, plan):
    """Bound every declared observation, not just aggregates or final score.

    The 0.1% full-scale budget is an engineering repeatability requirement,
    not a confidence interval or a relaxation of electrical acceptance bounds.
    """
    from benchmarking.evaluation import number

    def within(span, limit):
        return span <= limit or math.isclose(span, limit, rel_tol=1e-12, abs_tol=0.0)

    relative_limit, score_limit = 1e-3, 0.1
    observations = [{"metrics": r["metrics"], "score": r["score"],
                     "measurements": {name: j.get("measurements") for name, j in r["jobs"].items()}}
                    for r in reports]
    scores = {stage: number(r["score"]["value"]) if r["score"] else None
              for stage, r in zip(("direct", "check", "final"), reports, strict=True)}
    scored = [value for value in scores.values() if value is not None]
    if scored and len(scored) != len(reports):
        raise ValueError("Mixed scored and unscored repeatability reports")
    score_spread = max(scored) - min(scored) if scored else 0.0
    checks = {}
    for metric in plan.metrics:
        for index, ref in enumerate(metric.observations):
            job, name = ref.split(':')
            measurements = [r['jobs'][job]['measurements'][name] for r in reports]
            if any(m['unit'] != metric.unit for m in measurements):
                raise ValueError('Repeatability measurement units changed')
            values = [number(m['value']) for m in measurements]
            scale = [abs(value) for value in values]
            scale.extend(abs(number(v)) for v in (metric.scale, metric.lower, metric.upper) if v is not None)
            if metric.baseline:
                source, measurement = metric.baseline[index].split(':')
                scale.append(abs(number(plan.pre_layout[source]['measurements'][measurement]['value'])))
            limit = relative_limit * max(scale)
            span = max(values) - min(values)
            checks[f'{metric.id}/{ref}'] = {
                'unit': metric.unit, 'minimum': min(values), 'maximum': max(values),
                'spread': span, 'limit': limit, 'within_limit': within(span, limit)}
    return {'observations_identical': all(value == observations[0] for value in observations[1:]),
            'policy': {'relative_spread': relative_limit, 'score_spread': score_limit},
            'scores': scores, 'score_spread': score_spread,
            'observations': checks,
            'within_limits': within(score_spread, score_limit) and all(c['within_limit'] for c in checks.values())}


def verify(runtime, directory):
    """Reject stale evidence using the installed evaluator and current Dataset bindings."""
    directory = Path(directory)
    record = json.loads((directory / "qualification.json").read_bytes())
    if record["evaluator"] != evaluation_identity(runtime.task, runtime.backends):
        raise ValueError("Qualification evaluator or task bindings changed")
    if record["participant_implementation"] != participant_identity():
        raise ValueError("Qualification participant checking implementation changed")
    if record["witness_sha256"] != runtime.witness().sha256:
        raise ValueError("Qualification witness changed")
    manifest = process_manifest(runtime.config)
    if record["pdk_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError("Qualification PDK declaration changed")
    reports = []
    for stage in ("direct", "check", "final"):
        entry = record["reports"][stage]
        raw = read_file(directory, entry["path"])
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Qualification report digest mismatch: " + stage)
        report = json.loads(raw)
        if (report["task_sha256"] != runtime.task.digest
                or report["inputs"]["candidate"]["sha256"] != record["witness_sha256"]
                or report["plan"]["sha256"] != record["evaluator"]["plan_sha256"]
                or {k: hashlib.sha256(json_bytes(v)).hexdigest() for k, v in report["backends"].items()}
                   != record["evaluator"]["backends"]
                or report["engine_sha256"] != record["evaluator"]["implementation"]):
            raise ValueError("Qualification report belongs to another evaluator or candidate: " + stage)
        if (report["outcome"] != "passed" or report["task_success"] is not True
                or set(report["jobs"]) != {j.id for j in runtime.task.evaluation.jobs}
                or any(j["status"] != "passed" for j in report["jobs"].values())):
            raise ValueError("Qualification did not pass the complete plan: " + stage)
        reports.append(report)
    if not verdict(reports[0]) == verdict(reports[1]) == verdict(reports[2]):
        raise ValueError("Direct, participant-check and final evaluation diverged")
    if record["repeatability"] != repeatability(reports, runtime.task.evaluation):
        raise ValueError("Qualification repeatability disclosure differs from recorded observations")
    if not record['repeatability']['within_limits']:
        raise ValueError('Qualification numerical repeatability exceeds its limits')
    return record


def run(runtime, output, image):
    """Maintenance only: the witness is explicitly supplied, never mounted for a solver."""
    from benchmarking.service.server import LocalService, serve

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    witness = runtime.witness()
    run_evaluation(runtime.task.evaluation,
                   {**runtime.task.evaluation_inputs(), "candidate": witness},
                   runtime.backends, output / "direct", task_sha256=runtime.task.digest,
                   task_witnessed=runtime.task.witnessed)
    service = LocalService(output / "service", runtime.task, runtime.agent_resources(),
                           runtime.backends, image, secrets.token_urlsafe(32))
    server = serve(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}"
        response = Client(endpoint, service.token, timeout=600).create(runtime.task.id, {
            "harness_kind": "agent", "harness_id": "qualification", "harness_version": "1",
            "model": "none", "prompt_sha256": None, "configuration_sha256": None}, key="create")
        client = Client(endpoint, response["session_token"], timeout=60)
        sid = response["session_id"]
        bridge = Bridge(client, sid, output / "bridge.jsonl")
        directory = str(Path(runtime.task.output.path).parent)
        bridge.call("execute", {"command": "mkdir -p " + shlex.quote(directory)})
        candidate = shlex.quote(runtime.task.output.path)
        part_path = runtime.task.output.path + ".qualification-part"
        part = shlex.quote(part_path)
        bridge.call("execute", {"command": ": > " + candidate})
        chunk_bytes = response["limits"]["max_file_bytes"]
        for offset in range(0, len(witness.content), chunk_bytes):
            client.write(sid, part_path, witness.content[offset:offset + chunk_bytes],
                         key=f"witness-{offset}")
            appended = bridge.call("execute", {"command": f"cat {part} >> {candidate} && rm {part}"})
            if appended["exit_code"] != 0:
                raise ValueError("Witness upload failed: " + appended["output"])
        checked = bridge.call("check", {})
        if checked["exit_code"] != 0 or checked["truncated"]:
            raise ValueError("Participant check failed: " + checked["output"])
        feedback = json.loads(checked["output"])["feedback"]
        if (feedback["candidate"]["sha256"] != witness.sha256
                or feedback["tool_identity"] != service.evaluator_identity):
            raise ValueError("Participant check did not use the frozen witness and evaluator")
        if client.session(sid)["last_submission"] is not None:
            raise ValueError("Participant check unexpectedly submitted a candidate")
        client.submit(sid, runtime.task.output.path, key="submit")
        client.close(sid, key="close")
        while service.threads[sid].is_alive():
            service.threads[sid].join(timeout=1)
        if client.result(sid)["outcome"] != "pass":
            raise ValueError("Reference failed final HTTP evaluation")
        paths = {"direct": output / "direct/report.json",
                 "check": service.root / sid / "run" / feedback["report_path"],
                 "final": service.root / sid / "run/evaluation/report.json"}
        # Keep the three full reports in portable locations; service scratch is optional.
        reports = {}
        for stage, path in paths.items():
            raw = path.read_bytes()
            target = output / f"{stage}.json"
            atomic_write(target, raw)
            reports[stage] = {"path": target.name, "sha256": hashlib.sha256(raw).hexdigest()}
        record = {"case": runtime.task.id, "evaluator": service.evaluator_identity,
                  "participant_implementation": participant_identity(),
                  "witness_sha256": witness.sha256,
                  "pdk_sha256": hashlib.sha256((process_manifest(runtime.config)).read_bytes()).hexdigest(),
                  "reports": reports,
                  "repeatability": repeatability([json.loads(paths[stage].read_bytes())
                                                  for stage in ("direct", "check", "final")], runtime.task.evaluation)}
        atomic_write(output / "qualification.json", json_bytes(record))
        verify(runtime, output)
        return record
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        service.shutdown()


def acceptance_summary(runtime, directory, design_commit):
    """Export only verified acceptance facts, without requiring private report paths."""
    if not re.fullmatch(r"[0-9a-f]{40}", design_commit):
        raise ValueError("Acceptance summaries require an authoring Git commit")
    record = verify(runtime, directory)
    summary = {
        "task_sha256": runtime.task.digest,
        "design_commit": design_commit,
        "witness_sha256": record["witness_sha256"],
        "evidence_sha256": hashlib.sha256(read_file(directory, "qualification.json")).hexdigest(),
        "scope": "direct/check/final",
        "passed": True,
    }
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "verify", "verify-core"))
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--case")
    parser.add_argument("--image", default="iclayout-bench-tools:local")
    parser.add_argument("--output", type=Path, help="New run directory, or retained evidence to verify")
    parser.add_argument("--evidence", type=Path, help="Explicit JSON map of case IDs to relative evidence directories")
    parser.add_argument("--summaries", type=Path, help="Explicit author-owned acceptance map for verify-core")
    parser.add_argument("--summary", type=Path, help="Write a compact publication acceptance summary after verification")
    parser.add_argument("--design-commit", help="Authoring Git commit for the acceptance summary")
    args = parser.parse_args(argv)
    if args.summary and (not args.design_commit or not re.fullmatch(r"[0-9a-f]{40}", args.design_commit)):
        parser.error("--summary requires a full --design-commit")
    dataset = load_dataset(args.dataset, revision=args.revision, include_reference=True)
    if args.action == "verify-core":
        if args.case or args.output or args.summary or not args.evidence or not args.summaries:
            parser.error("verify-core requires --evidence and --summaries; omit --case/--output")
        _, cases = dataset.native_cases("core", "test")
        evidence_paths = json.loads(args.evidence.read_bytes())
        summaries = json.loads(args.summaries.read_bytes())
        failures, varying = [], []
        for name, path in cases.items():
            try:
                from benchmarking.files import relative

                evidence = args.evidence.parent / relative(evidence_paths[name], "evidence directory")
                if not (evidence / "qualification.json").is_file():
                    raise ValueError("Missing end-to-end qualification evidence")
                runtime = load_case(path, image=args.image)
                record = verify(runtime, evidence)
                published = summaries[name]
                if published != acceptance_summary(runtime, evidence, published["design_commit"]):
                    raise ValueError("External acceptance summary differs from verified evidence")
                if not record["repeatability"]["observations_identical"]:
                    varying.append(name)
            except (OSError, ValueError, KeyError) as error:
                failures.append(f"{name}: {error}")
        if failures:
            parser.exit(1, "Core publication gate failed:\n" + "\n".join(failures) + "\n")
        print(f"PASS: all {len(cases)} core cases have current direct/check/final evidence")
        if varying:
            print("Within repeatability limits, with non-identical observations: " + ", ".join(varying))
        return
    if args.evidence or args.summaries:
        parser.error("--evidence and --summaries are only used by verify-core")
    if not args.case or not args.output:
        parser.error("run/verify require --case and --output")
    runtime = load_case(dataset.case(args.case), image=args.image)
    if args.action == "run":
        run(runtime, args.output, args.image)
    else:
        verify(runtime, args.output)
    if args.summary:
        summary = acceptance_summary(runtime, args.output, args.design_commit)
        atomic_write(args.summary, json_bytes(summary), mode=0o644)
    print(f"PASS: {runtime.task.id}; direct/check/final qualification: {args.output}")


if __name__ == "__main__":
    main()
