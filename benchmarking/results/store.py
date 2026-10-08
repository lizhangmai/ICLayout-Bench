"""Import, query and compare immutable measurements through one archive interface."""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from benchmarking.protocol import evaluation_mode, layout_score_value

from . import schema as s
from .comparison import aggregate
from .importing import prepare_result
from .normalization import digest, finite, media
from .objects import FileObjects

__all__ = ["ResultStore", "ensure_record", "now"]


def now():
    return datetime.now(UTC).isoformat()


def ensure_record(conn, table, key, values):
    """Insert once within the caller transaction; return the existing row on conflict."""
    predicate = [table.c[k] == v for k, v in key.items()]
    insert = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert
    result = conn.execute(
        insert(table).values(**key, **values).on_conflict_do_nothing()
    )
    if result.rowcount:
        return None
    return conn.execute(select(table).where(*predicate)).mappings().one()


class ResultStore:
    """Own SQL metadata and copied, content-addressed artifacts under a durable directory."""

    def __init__(self, root, *, database_url=None, object_store=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.object_store = object_store if object_store is not None else FileObjects(self.root / "objects")
        self.engine = create_engine(
            database_url or f"sqlite:///{self.root / 'results.sqlite3'}"
        )
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def configure(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=30000")
                connection.execute("PRAGMA journal_mode=WAL")

        # Serialize table initialization across local CLI / web processes.
        from benchmarking.locking import BatchLease

        with BatchLease(self.root), self.engine.begin() as conn:
            s.metadata.create_all(conn)

    def close(self):
        self.engine.dispose()

    def import_result(
        self,
        path,
        *,
        experiment="Imported results",
        namespace="local",
        reevaluation=False,
    ):
        prepared = prepare_result(path, namespace)
        raw, evaluation, condition = prepared.raw, prepared.evaluation, prepared.condition
        task_id, identity, repetition = prepared.task_id, prepared.identity, prepared.repetition
        run_data, files, missing = prepared.run_data, prepared.files, prepared.missing
        tid, cid = digest([task_id, identity]), digest(condition)
        sid = evaluation.get("session_id")
        endpoint = (raw.get("identity") or {}).get("endpoint")
        origin = digest(endpoint) if endpoint else None
        rid = digest(
            [namespace, origin, sid or digest(raw)]
            if origin
            else [namespace, sid or digest(raw)]
        )
        fingerprint = digest(evaluation)
        eid = digest([rid, fingerprint])
        stored = {name: self.object_store.put(content) for name, content in files.items()}
        immutable = {
            k: v
            for k, v in run_data.items()
            if k not in {"image", "tool_identity", "limits"}
        }
        value = layout_score_value(evaluation.get("score"))
        if evaluation["outcome"] == "error":
            value = None
        xvalues = {"name": experiment, "schedule": []}
        xid = digest([namespace, experiment])
        with self.engine.begin() as conn:
            ensure_record(
                conn, s.tasks, {"id": tid}, {"task_id": task_id, "identity": identity}
            )
            ensure_record(conn, s.conditions, {"id": cid}, {"data": condition})
            ensure_record(conn, s.experiments, {"id": xid}, xvalues)
            old = ensure_record(
                conn,
                s.runs,
                {"id": rid},
                {
                    "session_id": sid,
                    "task_version": tid,
                    "condition_id": cid,
                    "repetition": repetition,
                    "elapsed_seconds": finite(
                        (raw.get("execution") or {}).get("elapsed_seconds")
                    ),
                    "data": run_data,
                    "imported_at": now(),
                },
            )
            if old and (
                old["task_version"] != tid
                or old["condition_id"] != cid
                or old["repetition"] != repetition
                or {
                    k: v
                    for k, v in old["data"].items()
                    if k not in {"image", "tool_identity", "limits"}
                }
                != immutable
            ):
                raise ValueError("Conflicting run identity; source was not overwritten")
            previous = (
                conn.execute(
                    select(s.evaluations.c.id).where(s.evaluations.c.run_id == rid)
                )
                .scalars()
                .all()
            )
            if previous and eid not in previous and not reevaluation:
                raise ValueError(
                    "Changed evaluation; use explicit --reevaluation to retain a new revision"
                )
            ensure_record(
                conn, s.experiment_runs, {"experiment_id": xid, "run_id": rid}, {}
            )
            ensure_record(
                conn,
                s.evaluations,
                {"id": eid},
                {
                    "run_id": rid,
                    "fingerprint": fingerprint,
                    "method": "layout",
                    "score": value,
                    "outcome": evaluation["outcome"],
                    "task_success": evaluation.get("task_success"),
                    "evaluation_mode": evaluation_mode(evaluation),
                    "data": evaluation,
                    "imported_at": now(),
                },
            )
            for name, metric in evaluation.get("metrics", {}).items():
                ensure_record(
                    conn,
                    s.metrics,
                    {"evaluation_id": eid, "name": name},
                    {
                        "value": finite(metric.get("value")),
                        "unit": metric.get("unit"),
                        "status": metric.get("status"),
                        "data": metric,
                    },
                )
            for name, (sha, size) in stored.items():
                ensure_record(conn, s.artifacts, {"sha256": sha}, {"size": size})
                old_file = ensure_record(
                    conn,
                    s.run_artifacts,
                    {"evaluation_id": eid, "name": name},
                    {"sha256": sha, "media_type": media(name)},
                )
                if (
                    old_file
                    and old_file["sha256"] != sha
                    and name not in {"layout.png", "result.json", "report.md"}
                ):
                    raise ValueError("Conflicting immutable artifact: " + name)
                    # Keep the original export; derived preview updates use an explicit presentation operation.
            if old and old["data"].get("image") != run_data["image"]:
                conn.execute(
                    s.runs.update().where(s.runs.c.id == rid).values(data=run_data)
                )
        return {
            "run_id": rid,
            "evaluation_id": eid,
            "status": "existing" if eid in previous else "imported",
            "missing": missing,
        }

    def import_directory(self, source, **options):
        source = Path(source)
        paths = (
            [source]
            if source.is_file()
            else (
                [source / "result.json"]
                if (source / "result.json").is_file()
                else sorted(source.rglob("result.json"))
            )
        )
        results = []
        for path in paths:
            if any(
                part.startswith(".")
                for part in path.relative_to(
                    source if source.is_dir() else source.parent
                ).parts
            ):
                continue
            # Nested evaluator reports are not result exports.
            if (
                "participant"
                in path.relative_to(source if source.is_dir() else source.parent).parts
            ):
                continue
            try:
                results.append(
                    {"source": str(path), **self.import_result(path, **options)}
                )
            except (ValueError, OSError) as error:
                results.append(
                    {"source": str(path), "status": "error", "error": str(error)}
                )
        return results

    def register_experiment(self, name, schedule, *, namespace="local"):
        xid = digest([namespace, name])
        with self.engine.begin() as conn:
            old = ensure_record(
                conn, s.experiments, {"id": xid}, {"name": name, "schedule": schedule}
            )
            if old:
                merged = {digest(row): row for row in old["schedule"] + schedule}
                conn.execute(
                    s.experiments.update()
                    .where(s.experiments.c.id == xid)
                    .values(schedule=list(merged.values()))
                )
        return xid

    def list_runs(
        self,
        *,
        model=None,
        task=None,
        evaluation_mode=None,
        experiment=None,
        pdk=None,
        effort=None,
        harness=None,
        outcome=None,
        offset=0,
        limit=100,
    ):
        ranked = select(
            s.evaluations,
            func.row_number()
            .over(
                partition_by=s.evaluations.c.run_id,
                order_by=(
                    s.evaluations.c.imported_at.desc(),
                    s.evaluations.c.id.desc(),
                ),
            )
            .label("position"),
        ).subquery()
        query = select(
            s.runs,
            s.tasks.c.task_id,
            s.tasks.c.title,
            s.tasks.c.pdk,
            s.tasks.c.identity.label("task_identity"),
            s.conditions.c.data.label("condition"),
            ranked.c.id.label("evaluation_id"),
            ranked.c.score,
            ranked.c.outcome,
            ranked.c.evaluation_mode,
            ranked.c.method,
            ranked.c.data.label("evaluation"),
            ranked.c.imported_at.label("evaluated_at"),
        )
        query = (
            query.join(s.tasks, s.runs.c.task_version == s.tasks.c.id)
            .join(s.conditions, s.runs.c.condition_id == s.conditions.c.id)
            .join(ranked, s.runs.c.id == ranked.c.run_id)
            .where(ranked.c.position == 1)
        )
        for column, value in [
            (s.tasks.c.task_id, task),
            (s.tasks.c.pdk, pdk),
            (ranked.c.evaluation_mode, evaluation_mode),
            (ranked.c.outcome, outcome),
        ]:
            if value:
                query = query.where(column == value)
        for key, value in [
            ("model", model),
            ("effort_resolved", effort),
            ("harness", harness),
        ]:
            if value:
                query = query.where(s.conditions.c.data[key].as_string() == value)
        if experiment:
            query = query.join(
                s.experiment_runs, s.experiment_runs.c.run_id == s.runs.c.id
            ).where(s.experiment_runs.c.experiment_id == experiment)
        with self.engine.connect() as conn:
            total = conn.execute(
                select(func.count()).select_from(query.subquery())
            ).scalar_one()
            rows = [
                dict(r)
                for r in conn.execute(
                    query.order_by(ranked.c.imported_at.desc(), ranked.c.id.desc())
                    .offset(offset)
                    .limit(limit)
                ).mappings()
            ]
        return {"total": total, "items": rows}

    def detail(self, run_id, evaluation_id=None):
        with self.engine.connect() as conn:
            run = (
                conn.execute(select(s.runs).where(s.runs.c.id == run_id))
                .mappings()
                .first()
            )
            if run is None:
                raise KeyError(run_id)
            history = [
                dict(r)
                for r in conn.execute(
                    select(s.evaluations)
                    .where(s.evaluations.c.run_id == run_id)
                    .order_by(s.evaluations.c.imported_at.desc(), s.evaluations.c.id)
                ).mappings()
            ]
            evaluation = (
                next((r for r in history if r["id"] == evaluation_id), None)
                if evaluation_id
                else history[0]
            )
            if evaluation is None:
                raise KeyError(evaluation_id)
            task = dict(
                conn.execute(select(s.tasks).where(s.tasks.c.id == run["task_version"]))
                .mappings()
                .one()
            )
            task["artifacts"] = [
                dict(r)
                for r in conn.execute(
                    select(s.task_artifacts).where(
                        s.task_artifacts.c.task_version == task["id"]
                    )
                ).mappings()
            ]
            condition = conn.execute(
                select(s.conditions.c.data).where(
                    s.conditions.c.id == run["condition_id"]
                )
            ).scalar_one()
            files = [
                dict(r)
                for r in conn.execute(
                    select(s.run_artifacts).where(
                        s.run_artifacts.c.evaluation_id == evaluation["id"]
                    )
                ).mappings()
            ]
        checks = {}
        report = next((a for a in files if a["name"] == "evaluation/report.json"), None)
        if report:
            report_data = json.loads(self.artifact(report["sha256"]).read_bytes())
            checks = {
                name: {
                    "status": job.get("status"),
                    "gate": job.get("gate"),
                    "reason": job.get("reason"),
                }
                for name, job in report_data.get("jobs", {}).items()
            }
        return {
            **dict(run),
            "checks": checks,
            "task": task,
            "condition": condition,
            "evaluation": evaluation,
            "history": [
                {
                    "id": h["id"],
                    "score": h["score"],
                    "outcome": h["outcome"],
                    "method": h["method"],
                    "imported_at": h["imported_at"],
                }
                for h in history
            ],
            "artifacts": files,
        }

    def attach(self, owner, name, raw, *, task=False):
        if not task and name not in {
            "layout.geometry.json",
            "layout.drc.json",
            "layout.png",
        }:
            raise ValueError("Only derived presentation artifacts can be attached")
        sha, size = self.object_store.put(raw)
        table, key = (
            (s.task_artifacts, "task_version")
            if task
            else (s.run_artifacts, "evaluation_id")
        )
        with self.engine.begin() as conn:
            ensure_record(conn, s.artifacts, {"sha256": sha}, {"size": size})
            old = ensure_record(
                conn,
                table,
                {key: owner, "name": name},
                {"sha256": sha, "media_type": media(name)},
            )
            if old and old["sha256"] != sha:
                conn.execute(
                    table.update()
                    .where(table.c[key] == owner, table.c.name == name)
                    .values(sha256=sha)
                )
        return sha

    def update_task_presentation(self, task_version, *, title, pdk, metadata):
        """Bind reader metadata without changing task identity or evaluations."""
        with self.engine.begin() as conn:
            conn.execute(s.tasks.update().where(s.tasks.c.id == task_version)
                         .values(title=title, pdk=pdk, presentation=metadata))

    def artifact(self, sha):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(s.artifacts).where(s.artifacts.c.sha256 == sha))
                .mappings()
                .first()
            )
        if row is None:
            raise KeyError(sha)
        path = self.object_store.path(sha)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise ValueError("Missing or corrupt stored artifact")
        return path

    def comparison(self, **filters):
        rows = self.list_runs(limit=1_000_000, **filters)["items"]
        with self.engine.connect() as conn:
            schedule_query = select(s.experiments)
            if filters.get("experiment"):
                schedule_query = schedule_query.where(
                    s.experiments.c.id == filters["experiment"]
                )
            schedules = [
                p
                for x in conn.execute(schedule_query).mappings()
                for p in x["schedule"]
            ]
        return aggregate(rows, schedules, filters)

    def inventory(self):
        with self.engine.connect() as conn:
            return {
                "experiments": [
                    dict(r) for r in conn.execute(select(s.experiments)).mappings()
                ],
                "tasks": [dict(r) for r in conn.execute(select(s.tasks)).mappings()],
                "conditions": [
                    dict(r) for r in conn.execute(select(s.conditions)).mappings()
                ],
            }

    def verify(self):
        failures = []
        with self.engine.connect() as conn:
            objects = list(conn.execute(select(s.artifacts)).mappings())
        for artifact in objects:
            try:
                self.artifact(artifact["sha256"])
            except (OSError, ValueError) as error:
                failures.append({"sha256": artifact["sha256"], "error": str(error)})
        return {"objects": len(objects), "failures": failures}
