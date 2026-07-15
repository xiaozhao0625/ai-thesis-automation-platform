from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.maintenance.snapshot import collect_snapshot
from app.maintenance.snapshot import main as snapshot_main
from app.workflow.service import TaskWorkflowService


@pytest.mark.postgres
@pytest.mark.integration
def test_handoff_snapshot_reports_database_and_artifact_store_counts(
    db_session, tmp_path: Path
) -> None:
    TaskWorkflowService(db_session).create_task(
        title="受控材料任务",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
    )
    db_session.flush()
    artifact_root = tmp_path / "artifact-store"
    (artifact_root / "tasks" / "one").mkdir(parents=True)
    (artifact_root / "tasks" / "one" / "a.json").write_bytes(b"123")
    (artifact_root / "tasks" / "one" / "b.jsonl").write_bytes(b"4567")
    (artifact_root / ".staging").mkdir()
    (artifact_root / ".staging" / "partial.tmp").write_bytes(b"ignore")

    snapshot = collect_snapshot(db_session, artifact_root)

    assert snapshot["alembic_revision"] == "2c13448999a3"
    assert snapshot["table_counts"]["tasks"] == 1
    assert snapshot["table_counts"]["workflow_runs"] == 1
    assert snapshot["table_counts"]["node_runs"] == 3
    assert snapshot["artifact_store"] == {"file_count": 2, "size_bytes": 7}


@pytest.mark.postgres
@pytest.mark.integration
def test_handoff_snapshot_cli_prints_portable_json(
    db_session, tmp_path: Path, capsys
) -> None:
    TaskWorkflowService(db_session).create_task(
        title="换机交接任务",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
    )
    db_session.commit()
    artifact_root = tmp_path / "artifact-store"
    artifact_root.mkdir()
    (artifact_root / "one.bin").write_bytes(b"portable")

    exit_code = snapshot_main(
        [
            "--database-url",
            str(db_session.get_bind().url),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["table_counts"]["tasks"] == 1
    assert payload["artifact_store"] == {"file_count": 1, "size_bytes": 8}


@pytest.mark.postgres
@pytest.mark.integration
def test_handoff_snapshot_fresh_process_loads_all_model_tables(
    db_session, tmp_path: Path
) -> None:
    TaskWorkflowService(db_session).create_task(
        title="独立进程快照任务",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
    )
    db_session.commit()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.maintenance.snapshot",
            "--database-url",
            str(db_session.get_bind().url),
            "--artifact-root",
            str(tmp_path / "artifact-store"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["table_counts"]["tasks"] == 1
    assert payload["table_counts"]["node_runs"] == 3
