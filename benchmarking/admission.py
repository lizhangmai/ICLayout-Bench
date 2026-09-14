"""Operator-pinned local admission and conservative aggregate export.

The pin and ledger must be controlled by the evaluator, outside participant
configuration. Attestations record human review; they do not prove their claims.
"""

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .evaluation import identifier
from .files import Asset, keys, read_file, text
from .provenance import json_asset
from .recorder import sync_directory

QUALIFICATION_CHECKS = {
    "witness", "invalid_physical", "invalid_geometry", "invalid_performance",
    "calibration", "repeated_stability", "input_semantics",
}
BENCH_SCORE_METHOD = "bench-v1"
TASK_SCORE_METHOD = "layout-v1"
# The policy freezes the suite-level result. ``TASK_SCORE_METHOD`` is kept
# beside it so a task score cannot be substituted for the BenchScore export.
SCORE_METHOD = BENCH_SCORE_METHOD
SCORE_MAXIMUM = 100
# ``score`` is the only ranked result.  Infrastructure errors remain an
# explicitly approved diagnostic and never become a second ranking metric.
EXPORT_FIELDS = {"score", "infrastructure_error_rate"}


def conditions(manifest):
    """Stable review subject, excluding archive location and Git working-tree prose."""
    return {**{key: manifest[key] for key in (
        "schema_version", "run_kind", "id", "scope", "plan", "host", "repetitions",
        "order", "seed", "max_infrastructure_retries", "concurrency", "statistics", "tasks", "agents", "schedule")},
        "framework_sha256": manifest["framework"]["sha256"]}


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a lowercase SHA-256 digest")
    return value


def _label(value):
    identifier(value)
    if len(value) > 64:
        raise ValueError("Public label exceeds 64 characters")


def _deadline(data):
    deadline = datetime.fromisoformat(text(data["valid_until"], "valid_until"))
    if deadline.tzinfo is None:
        raise ValueError("Admission expiry requires an explicit timezone")
    return deadline


def _rounded_rate(value, decimals):
    """Validate and round an allowlisted rate from trusted summary evidence."""
    if value is None:
        return None
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Export evidence has an invalid infrastructure error rate")
    return round(value, decimals)


@dataclass(frozen=True)
class Policy:
    source: Asset
    evidence: tuple[tuple[str, Asset], ...]

    @property
    def data(self):
        return json.loads(self.source.content)

    def check_time(self):
        if datetime.now(UTC) >= _deadline(self.data):
            raise ValueError("Admission policy has expired")


def _parse_policy(source):
    data = json.loads(source.content)
    keys(data, {"schema_version", "id", "conditions_sha256", "valid_until", "ledger",
                "dataset", "exposure_mode", "tasks", "agents", "export"}, set(), "admission policy")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported admission policy")
    _label(data["id"])
    _digest(data["conditions_sha256"])
    _deadline(data)
    ledger = Path(text(data["ledger"], "ledger"))
    if not ledger.is_absolute() or str(ledger) != data["ledger"] or ".." in ledger.parts:
        raise ValueError("Ledger must be an absolute normalized operator path")
    if data["dataset"] not in {"public", "hidden", "synthetic_hidden"}:
        raise ValueError("Unknown admission dataset category")
    if data["exposure_mode"] not in {"offline", "external_api"}:
        raise ValueError("Unknown approved inference exposure mode")
    for group in ("tasks", "agents"):
        if not isinstance(data[group], dict) or not data[group]:
            raise ValueError(f"Admission needs a nonempty {group} table")
    references = []
    for task_id, task in data["tasks"].items():
        identifier(task_id)
        keys(task, {"qualification", "materials", "authorization", "source_kind"}, set(), "task admission")
        allowed = {"public": {"public"}, "hidden": {"independent_unpublished", "authorized_unpublished"},
                   "synthetic_hidden": {"synthetic"}}[data["dataset"]]
        if task["source_kind"] not in allowed:
            raise ValueError("Task source is incompatible with the approved dataset")
        references.extend([task["qualification"], task["authorization"]])
        if not isinstance(task["materials"], list) or not task["materials"]:
            raise ValueError("Qualification needs archived supporting materials")
        references.extend(task["materials"])
    for agent_id, agent in data["agents"].items():
        identifier(agent_id)
        keys(agent, {"conditions_sha256", "resource_review", "endpoint"}, set(), "agent admission")
        _digest(agent["conditions_sha256"])
        references.append(agent["resource_review"])
        endpoint = agent["endpoint"]
        if endpoint is not None:
            keys(endpoint, {"provider", "base_url", "model", "no_training", "zero_data_retention",
                            "authorization"}, set(), "endpoint admission")
            for key in ("provider", "base_url", "model"):
                text(endpoint[key], key)
            if endpoint["no_training"] is not True or endpoint["zero_data_retention"] is not True:
                raise ValueError("Endpoint requires reviewed no-training and zero-retention arrangements")
            references.append(endpoint["authorization"])
    export = data["export"]
    keys(export, {"score", "fields", "min_tasks", "min_families", "min_trials", "decimals", "groups"}, set(), "export policy")
    score = export["score"]
    keys(score, {"method", "task_score_method", "maximum"}, set(), "export score")
    if (score["method"] != SCORE_METHOD or score["task_score_method"] != TASK_SCORE_METHOD
            or score["maximum"] != SCORE_MAXIMUM):
        raise ValueError("Export score must use the approved BenchScore contract")
    if (not isinstance(export["fields"], list) or not export["fields"]
            or any(field not in EXPORT_FIELDS for field in export["fields"])
            or "score" not in export["fields"]
            or len(set(export["fields"])) != len(export["fields"])):
        raise ValueError("Export fields must uniquely include the layout-v1 score")
    for name, minimum, maximum in (("min_tasks", 2, None), ("min_families", 2, None),
                                   ("min_trials", 2, None), ("decimals", 0, 3)):
        value = export[name]
        if type(value) is not int or value < minimum or maximum is not None and value > maximum:
            raise ValueError(f"Invalid export {name}")
    if not isinstance(export["groups"], list) or not export["groups"]:
        raise ValueError("Export needs predetermined groups")
    labels, pairs = set(), set()
    for group in export["groups"]:
        keys(group, {"configuration_id", "run_kind", "label"}, set(), "export group")
        identifier(group["configuration_id"])
        identifier(group["run_kind"])
        _label(group["label"])
        pair = (group["configuration_id"], group["run_kind"])
        if group["label"] in labels or pair in pairs:
            raise ValueError("Duplicate export group or label")
        labels.add(group["label"])
        pairs.add(pair)
    for ref in references:
        keys(ref, {"path", "sha256"}, set(), "review evidence")
        _digest(ref["sha256"])
    return data, references


def load_policy(path, expected_sha256):
    """A caller-supplied pin is meaningful only when supplied by the trusted operator."""
    path = Path(path).absolute()
    source = Asset(read_file(path.parent, path.name), "json")
    if source.sha256 != _digest(expected_sha256):
        raise ValueError("Admission policy differs from the operator pin")
    _, references = _parse_policy(source)
    evidence = {}
    for ref in references:
        asset = Asset(read_file(path.parent, ref["path"]), "binary")
        if not asset.content or asset.sha256 != ref["sha256"]:
            raise ValueError("Admission review evidence integrity mismatch")
        evidence[asset.sha256] = asset
    return Policy(source, tuple(sorted(evidence.items())))


def validate_policy(policy, manifest):
    """Validate frozen conditions and scoped qualification, without consuming access."""
    data, _ = _parse_policy(policy.source)
    if json_asset(conditions(manifest)).sha256 != data["conditions_sha256"]:
        raise ValueError("Execution conditions were not approved")
    scopes = {"public": "public_development", "hidden": "hidden_development", "synthetic_hidden": "synthetic"}
    if manifest["scope"] != scopes[data["dataset"]]:
        raise ValueError("Plan scope differs from operator-approved dataset")
    if set(data["tasks"]) != set(manifest["tasks"]) or set(data["agents"]) != set(manifest["agents"]):
        raise ValueError("Approval must cover the exact task and configuration sets")
    evidence = dict(policy.evidence)
    for task_id, approval in data["tasks"].items():
        record = json.loads(evidence[approval["qualification"]["sha256"]].content)
        keys(record, {"schema_version", "task_sha256", "backends_sha256", "framework_sha256", "checks", "review"},
             set(), "qualification record")
        task = manifest["tasks"][task_id]
        if (type(record["schema_version"]) is not int or record["schema_version"] != 1
                or record["task_sha256"] != task["task_sha256"]
                or record["backends_sha256"] != json_asset(task["backends"]).sha256
                or record["framework_sha256"] != manifest["framework"]["sha256"]):
            raise ValueError("Qualification does not cover the actual task, framework and tools")
        keys(record["checks"], QUALIFICATION_CHECKS, set(), "qualification coverage")
        if any(value is not True for value in record["checks"].values()):
            raise ValueError("Qualification coverage is incomplete")
        text(record["review"], "qualification review")
    for agent_id, approval in data["agents"].items():
        agent = manifest["agents"][agent_id]
        if json_asset(agent).sha256 != approval["conditions_sha256"]:
            raise ValueError("Agent resources, image, budget or inference were not approved")
        endpoint, inference = approval["endpoint"], agent["inference"]
        if ("external_api" if inference else "offline") != data["exposure_mode"]:
            raise ValueError("Inference exposure mode differs from the approved task pool")
        if (endpoint is None) != (inference is None):
            raise ValueError("Inference access differs from endpoint approval")
        if inference:
            if any(endpoint[key] != inference[key] for key in ("base_url", "model")):
                raise ValueError("Actual endpoint/model is outside authorization")
            if data["dataset"] == "hidden" and agent["run_kind"] == "model_protocol_test":
                raise ValueError("Protocol test transport cannot access a hidden dataset")
    available = set()
    for agent_id, agent in manifest["agents"].items():
        available.add((agent_id, agent["run_kind"]))
        # A configured inference endpoint can be unused. The run recorder
        # then truthfully labels the resulting offline cohort separately.
        if agent["inference"] is not None:
            available.add((agent_id, "offline_cli_development"))
    if any((g["configuration_id"], g["run_kind"]) not in available for g in data["export"]["groups"]):
        raise ValueError("Export group is outside the approved execution")


def reserve(policy, execution_sha256):
    """Consume this policy once before any solver input; interruptions never refund it."""
    policy.check_time()
    root = Path(policy.data["ledger"])
    # The evaluator provisions this directory independently of a batch or participant.
    if root.resolve(strict=True) != root or not root.is_dir():
        raise ValueError("Ledger must be a regular operator directory without symlinks")
    stat = root.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise ValueError("Admission ledger must be owned by the operator with private permissions")
    path = root / (policy.source.sha256 + ".json")
    record = {"policy_sha256": policy.source.sha256, "execution_sha256": execution_sha256,
              "reserved_at": datetime.now(UTC).isoformat()}
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json_asset(record).content)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(root)
    return record


def freeze_admission(policy, manifest, archive):
    policy.check_time()
    validate_policy(policy, manifest)
    return {"schema_version": 1, "status": "policy_checked_development", "policy": archive(policy.source),
            "evidence": {digest: archive(asset) for digest, asset in policy.evidence}}


def restore_policy(root, manifest, expected_sha256):
    admission = manifest.get("admission")
    if not admission or admission.get("status") != "policy_checked_development":
        raise ValueError("Batch has no frozen admission policy")
    def read(ref):
        asset = Asset(read_file(root, ref["path"]), ref["format"])
        if any(ref[key] != value for key, value in asset.identity().items()):
            raise ValueError("Archived admission evidence integrity mismatch")
        return asset
    source = read(admission["policy"])
    if source.sha256 != _digest(expected_sha256):
        raise ValueError("Frozen policy differs from the operator export pin")
    policy = Policy(source, tuple((digest, read(ref)) for digest, ref in admission["evidence"].items()))
    _, refs = _parse_policy(source)
    if any(dict(policy.evidence).get(ref["sha256"], Asset(b"", "binary")).sha256 != ref["sha256"] for ref in refs):
        raise ValueError("Missing archived review evidence")
    validate_policy(policy, manifest)
    return policy


def export_batch(destination, expected_policy_sha256):
    """Return a new allowlisted aggregate object; never copy arbitrary internal fields."""
    from .report import _read_json, summarize_batch

    root = Path(destination).absolute()
    batch = json.loads(read_file(root, "batch.json"))
    if batch.get("phase") != "finished":
        raise ValueError("Only finished batches may be exported")
    manifest = _read_json(root, batch["execution"])
    policy = restore_policy(root, manifest, expected_policy_sha256)
    summary = summarize_batch(root)
    # Publication uses the same statistical implementation reviewed before execution.
    if summary["statistics_implementation_sha256"] != manifest["framework"]["files"]["benchmarking/report.py"]["sha256"]:
        raise ValueError("Export requires the approved statistics implementation")
    if Asset(Path(__file__).read_bytes(), "python").sha256 != manifest["framework"]["files"]["benchmarking/admission.py"]["sha256"]:
        raise ValueError("Export requires the approved admission implementation")
    rules = policy.data["export"]
    bench_score = summary.get("bench_score")
    if (not isinstance(bench_score, dict)
            or bench_score.get("method") != rules["score"]["method"]
            or bench_score.get("task_score_method") != rules["score"]["task_score_method"]
            or bench_score.get("maximum") != rules["score"]["maximum"]
            or bench_score.get("suite_sha256") != manifest["statistics"].get("suite_sha256")
            or type(bench_score.get("complete")) is not bool
            or not isinstance(bench_score.get("cohorts"), list)):
        raise ValueError("BenchScore evidence is missing or does not match the frozen policy")
    groups = {(g["configuration_id"], g["run_kind"]): g for g in bench_score["cohorts"]
              if isinstance(g, dict) and "configuration_id" in g and "run_kind" in g}
    if len(groups) != len(bench_score["cohorts"]):
        raise ValueError("BenchScore cohort evidence is malformed")

    # Coverage and gradability are separate properties. An evaluator error is
    # a terminal report for its scheduled slot, so it may leave a cohort's
    # score unknown while still allowing a complete schedule to be exported.
    # A slot with no terminal report remains ``missing`` and must never pass
    # this gate. The report implementation owns the classification; admission
    # only checks the resulting, recomputed evidence.
    for group in groups.values():
        tasks = group.get("tasks")
        if (group.get("method") != rules["score"]["method"]
                or group.get("task_score_method") != rules["score"]["task_score_method"]
                or group.get("maximum") != rules["score"]["maximum"]
                or group.get("suite_sha256") != bench_score["suite_sha256"]
                or not isinstance(tasks, dict)
                or type(group.get("task_count")) is not int or group["task_count"] < 0
                or group.get("task_count") != len(tasks)
                or set(tasks) != set(manifest["tasks"])):
            raise ValueError("BenchScore cohort evidence does not match the frozen policy")
        group_missing = group.get("missing")
        group_unknown = group.get("unknown")
        if (type(group_missing) is not int or group_missing < 0
                or type(group_unknown) is not int or group_unknown < 0):
            raise ValueError("BenchScore cohort coverage evidence is malformed")
        task_missing, task_unknown = 0, 0
        for task_id, task in tasks.items():
            if (not isinstance(task, dict)
                    or task.get("coefficient") != manifest["tasks"][task_id]["coefficient"]
                    or task.get("maximum") != rules["score"]["maximum"]
                    or type(task.get("scheduled")) is not int or task["scheduled"] < 0
                    or task["scheduled"] != manifest["repetitions"]
                    or type(task.get("measured")) is not int or task["measured"] < 0
                    or type(task.get("missing")) is not int or task["missing"] < 0
                    or type(task.get("unknown")) is not int or task["unknown"] < 0
                    or task["measured"] + task["missing"] != task["scheduled"]
                    or task["unknown"] > task["measured"]):
                raise ValueError("BenchScore cohort task evidence is malformed")
            task_missing += task["missing"]
            task_unknown += task["unknown"]
        if group_missing != task_missing or group_unknown != task_unknown:
            raise ValueError("BenchScore cohort coverage evidence is inconsistent")
        expected_complete = group_missing == 0 and group_unknown == 0
        if type(group.get("complete")) is not bool or group["complete"] != expected_complete:
            raise ValueError("BenchScore cohort completeness evidence is inconsistent")
        if group_missing:
            raise ValueError("Incomplete batches are not eligible for this aggregate export")
        if "value" not in group:
            raise ValueError("BenchScore evidence is missing its value")
        value = group["value"]
        if (value is not None
                and (type(value) not in {int, float} or not math.isfinite(value)
                     or not 0 <= value <= rules["score"]["maximum"])):
            raise ValueError("Score evidence has an invalid value")
        if (group_unknown and value is not None) or (not group_unknown and value is None):
            raise ValueError("BenchScore value does not match its coverage evidence")

    # ``bench_score.complete`` means every covered slot has a usable score;
    # it is allowed to be false only when the scorer has explicitly left one
    # or more covered slots unknown. Coverage itself was checked above.
    any_unknown = any(group["unknown"] for group in groups.values())
    if bench_score["complete"] != (not any_unknown):
        raise ValueError("BenchScore completeness evidence is inconsistent")
    released = []
    for approved in rules["groups"]:
        group = groups.get((approved["configuration_id"], approved["run_kind"]))
        if group is None:
            raise ValueError("BenchScore cohort is missing from the approved export")
        if (group.get("method") != rules["score"]["method"]
                or group.get("task_score_method") != rules["score"]["task_score_method"]
                or group.get("maximum") != rules["score"]["maximum"]
                or group.get("suite_sha256") != bench_score["suite_sha256"]
                or not isinstance(group.get("tasks"), dict)
                or group.get("task_count") != len(group["tasks"])
                or set(group.get("tasks", {})) != set(manifest["tasks"])):
            raise ValueError("BenchScore cohort evidence does not match the frozen policy")
        trials = sum(task["measured"] for task in group["tasks"].values())
        family_count = len({manifest["tasks"][task_id]["family"] for task_id in group["tasks"]})
        if (group.get("task_count") < rules["min_tasks"]
                or family_count < rules["min_families"] or trials < rules["min_trials"]):
            continue  # No suppressed labels, task hashes, counts or partial subgroup results.
        score = group
        value = score["value"]
        if value is not None:
            if group["unknown"]:
                raise ValueError("Unknown BenchScore evidence must be exported as null")
            value = round(value, rules["decimals"])
        diagnostic_groups = [item for item in summary["groups"]
                             if item["configuration_id"] == approved["configuration_id"]
                             and item["run_kind"] == approved["run_kind"]]
        finished_attempts = sum(item["attempts_finished"] for item in diagnostic_groups)
        infrastructure_errors = sum(item["infrastructure_errors"] for item in diagnostic_groups)
        infrastructure_rate = (infrastructure_errors / finished_attempts
                                if finished_attempts else None)
        values = {
            "score": {"method": score["method"], "value": value, "maximum": score["maximum"]},
            # The diagnostic belongs to the regular group summary. It is
            # deliberately copied only when the operator listed it in fields.
            "infrastructure_error_rate": _rounded_rate(infrastructure_rate, rules["decimals"]),
        }
        released.append({"label": approved["label"], "run_kind": group["run_kind"],
                         "task_count": len(group["tasks"]), "family_count": family_count,
                         "trials": trials, **{field: values[field] for field in rules["fields"]}})
    return {"schema_version": 1, "run_kind": "policy_checked_development_export",
            "release_id": policy.data["id"], "dataset": policy.data["dataset"],
            "exposure_mode": policy.data["exposure_mode"], "groups": released}
