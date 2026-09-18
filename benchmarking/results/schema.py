"""Version-one result archive schema; identities are portable across SQL backends."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()
tasks = Table(
    "task_versions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("task_id", Text, nullable=False, index=True),
    Column("identity", JSON, nullable=False),
    Column("title", Text),
    Column("pdk", Text),
    Column("presentation", JSON),
)
conditions = Table(
    "conditions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("data", JSON, nullable=False),
)
experiments = Table(
    "experiments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", Text, nullable=False),
    Column("schedule", JSON, nullable=False),
)
runs = Table(
    "runs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("session_id", Text),
    Column("task_version", ForeignKey("task_versions.id"), nullable=False, index=True),
    Column("condition_id", ForeignKey("conditions.id"), nullable=False, index=True),
    Column("repetition", Integer, nullable=False),
    Column("elapsed_seconds", Float),
    Column("data", JSON, nullable=False),
    Column("imported_at", Text, nullable=False),
)
experiment_runs = Table(
    "experiment_runs",
    metadata,
    Column("experiment_id", ForeignKey("experiments.id"), primary_key=True),
    Column("run_id", ForeignKey("runs.id"), primary_key=True),
)
evaluations = Table(
    "evaluations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("fingerprint", String(64), nullable=False),
    Column("method", Text),
    Column("score", Float),
    Column("outcome", Text),
    Column("task_success", Boolean),
    Column("verification_level", Text, nullable=False),
    Column("data", JSON, nullable=False),
    Column("imported_at", Text, nullable=False),
    UniqueConstraint("run_id", "fingerprint"),
)
metrics = Table(
    "metrics",
    metadata,
    Column("evaluation_id", ForeignKey("evaluations.id"), primary_key=True),
    Column("name", String(255), primary_key=True),
    Column("value", Float),
    Column("unit", Text),
    Column("status", Text),
    Column("data", JSON, nullable=False),
)
artifacts = Table(
    "artifacts",
    metadata,
    Column("sha256", String(64), primary_key=True),
    Column("size", Integer, nullable=False),
)
run_artifacts = Table(
    "run_artifacts",
    metadata,
    Column("evaluation_id", ForeignKey("evaluations.id"), primary_key=True),
    Column("name", String(512), primary_key=True),
    Column("sha256", ForeignKey("artifacts.sha256"), nullable=False),
    Column("media_type", Text, nullable=False),
)
task_artifacts = Table(
    "task_artifacts",
    metadata,
    Column("task_version", ForeignKey("task_versions.id"), primary_key=True),
    Column("name", String(512), primary_key=True),
    Column("sha256", ForeignKey("artifacts.sha256"), nullable=False),
    Column("media_type", Text, nullable=False),
)
