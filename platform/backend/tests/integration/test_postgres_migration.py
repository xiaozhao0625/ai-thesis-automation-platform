from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


@pytest.mark.postgres
@pytest.mark.integration
def test_alembic_can_rebuild_all_tables_from_an_empty_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres@127.0.0.1:55432/thesis_p1_1",
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "tasks",
        "human_approvals",
        "workflow_runs",
        "node_runs",
        "node_execution_attempts",
        "outbox_events",
        "worker_leases",
        "artifacts",
        "artifact_versions",
        "node_run_outputs",
        "node_run_logs",
        "worker_instances",
    } <= tables
    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar()
    engine.dispose()

    command.downgrade(config, "base")
    command.upgrade(config, "head")
