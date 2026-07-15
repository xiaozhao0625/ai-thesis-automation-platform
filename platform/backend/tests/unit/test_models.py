from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app.db.models import NodeRun, Task, WorkerLease


def test_metadata_contains_all_p1_1_tables() -> None:
    assert set(Base.metadata.tables) == {
        "artifact_versions",
        "artifacts",
        "human_approvals",
        "node_execution_attempts",
        "node_run_logs",
        "node_run_outputs",
        "node_runs",
        "outbox_events",
        "tasks",
        "worker_instances",
        "worker_leases",
        "workflow_runs",
    }


def test_core_identifiers_are_uuid_columns() -> None:
    assert str(inspect(Task).columns.id.type) == "UUID"
    assert str(inspect(NodeRun).columns.id.type) == "UUID"


def test_worker_lease_defines_postgres_active_lease_guard() -> None:
    indexes = {index.name: index for index in WorkerLease.__table__.indexes}

    guard = indexes["uq_worker_leases_active_node"]
    assert guard.unique is True
    assert str(guard.dialect_options["postgresql"]["where"]) == (
        "status = 'ACTIVE'"
    )


def test_every_mutable_aggregate_has_timezone_aware_timestamp_columns() -> None:
    for model in (Task, NodeRun, WorkerLease):
        for name in ("created_at", "updated_at"):
            column = inspect(model).columns[name]
            assert column.type.timezone is True, f"{model.__name__}.{name}"
