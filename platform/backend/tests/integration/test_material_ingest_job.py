from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.artifacts.store import LocalArtifactStore
from app.db.enums import AttemptStatus, LeaseStatus
from app.db.models import (
    ArtifactVersion,
    NodeExecutionAttempt,
    NodeRun,
    NodeRunOutput,
    OutboxEvent,
    WorkerLease,
)
from app.domain.workflow import ApprovalDecision, NodeStatus
from app.ingest_adapter.adapter import IngestCliAdapter
from app.ingest_adapter.paths import ControlledSourceResolver
from app.maintenance.verify_artifacts import main as verify_artifacts_main
from app.maintenance.verify_artifacts import verify_all_artifacts
from app.worker.job import MaterialIngestJobHandler
from app.workflow.service import TaskWorkflowService


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PLATFORM_ROOT = REPOSITORY_ROOT / "platform"


def queued_job(db_session, source_mount_path: str = "benchmark/ingest-fixture-v1"):
    service = TaskWorkflowService(db_session)
    created = service.create_task(
        title="实验室设备管理系统",
        capability_pack="python_web_management_v1",
        source_mount_path=source_mount_path,
        created_by="operator-01",
    )
    db_session.commit()
    service.decide_task_start(
        created.approval.id,
        decision=ApprovalDecision.APPROVE,
        decided_by="reviewer-01",
    )
    db_session.commit()
    node = db_session.scalar(
        select(NodeRun).where(
            NodeRun.workflow_run_id == created.workflow.id,
            NodeRun.node_key == "material_ingest",
        )
    )
    return created, node


def handler(db_session, tmp_path: Path) -> MaterialIngestJobHandler:
    artifact_root = tmp_path / "artifacts"
    return MaterialIngestJobHandler(
        session=db_session,
        worker_id="worker-test-01",
        source_resolver=ControlledSourceResolver(
            platform_root=PLATFORM_ROOT,
            allowed_roots=[PLATFORM_ROOT / "benchmark"],
            artifact_store_root=artifact_root,
        ),
        adapter=IngestCliAdapter(
            cli_src=REPOSITORY_ROOT / "ingest-cli" / "src",
            work_root=tmp_path / "attempt-work",
        ),
        artifact_store=LocalArtifactStore(artifact_root),
    )


@pytest.mark.postgres
@pytest.mark.integration
def test_real_cli_job_archives_outputs_and_advances_project_fact_gate(
    db_session, tmp_path: Path
) -> None:
    created, node = queued_job(db_session)
    job = handler(db_session, tmp_path)

    result = job.handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )

    db_session.refresh(node)
    attempt = db_session.scalars(select(NodeExecutionAttempt)).one()
    lease = db_session.scalars(select(WorkerLease)).one()
    project_fact = db_session.scalar(
        select(NodeRun).where(
            NodeRun.workflow_run_id == created.workflow.id,
            NodeRun.node_key == "project_fact_review",
        )
    )
    versions = db_session.scalars(select(ArtifactVersion)).all()
    outputs = db_session.scalars(
        select(NodeRunOutput).where(NodeRunOutput.is_current.is_(True))
    ).all()

    assert result.status == "SUCCEEDED"
    assert result.output_count == 10
    assert node.status is NodeStatus.SUCCEEDED
    assert node.current_output_count == 10
    assert attempt.status is AttemptStatus.SUCCEEDED
    assert lease.status is LeaseStatus.COMPLETED
    assert project_fact.status is NodeStatus.WAITING_FOR_APPROVAL
    assert len(versions) == len(outputs) == 10
    assert all(
        (tmp_path / "artifacts" / version.relative_storage_path).is_file()
        for version in versions
    )

    duplicate = job.handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )
    assert duplicate.status == "DUPLICATE_ALREADY_SUCCEEDED"
    assert db_session.scalar(select(func.count()).select_from(ArtifactVersion)) == 10
    assert db_session.scalar(
        select(func.count()).select_from(NodeExecutionAttempt)
    ) == 1


@pytest.mark.postgres
@pytest.mark.integration
def test_missing_source_records_failed_attempt_and_retry_outbox(
    db_session, tmp_path: Path
) -> None:
    _, node = queued_job(db_session, "benchmark/missing")

    result = handler(db_session, tmp_path).handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )

    db_session.refresh(node)
    attempt = db_session.scalars(select(NodeExecutionAttempt)).one()
    assert result.status == "RETRY_SCHEDULED"
    assert node.status is NodeStatus.QUEUED
    assert attempt.status is AttemptStatus.FAILED
    assert attempt.error_code == "SOURCE_PATH_NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(OutboxEvent)) == 2


@pytest.mark.postgres
@pytest.mark.integration
def test_artifact_verifier_accepts_every_recorded_file(
    db_session, tmp_path: Path
) -> None:
    _, node = queued_job(db_session)
    artifact_root = tmp_path / "artifacts"
    result = handler(db_session, tmp_path).handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )
    assert result.status == "SUCCEEDED"

    report = verify_all_artifacts(
        db_session,
        LocalArtifactStore(artifact_root),
    )

    assert report.total == 10
    assert report.verified == 10
    assert report.failures == ()


@pytest.mark.postgres
@pytest.mark.integration
def test_artifact_verifier_reports_tampered_file_without_stopping_audit(
    db_session, tmp_path: Path
) -> None:
    _, node = queued_job(db_session)
    artifact_root = tmp_path / "artifacts"
    result = handler(db_session, tmp_path).handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )
    assert result.status == "SUCCEEDED"
    version = db_session.scalars(
        select(ArtifactVersion).order_by(ArtifactVersion.created_at)
    ).first()
    (artifact_root / version.relative_storage_path).write_bytes(b"tampered")

    report = verify_all_artifacts(
        db_session,
        LocalArtifactStore(artifact_root),
    )

    assert report.total == 10
    assert report.verified == 9
    assert len(report.failures) == 1
    assert report.failures[0].artifact_version_id == str(version.id)
    assert "hash mismatch" in report.failures[0].reason


@pytest.mark.postgres
@pytest.mark.integration
def test_artifact_verifier_cli_returns_nonzero_for_tampered_file(
    db_session, tmp_path: Path, capsys
) -> None:
    _, node = queued_job(db_session)
    artifact_root = tmp_path / "artifacts"
    result = handler(db_session, tmp_path).handle(
        {
            "node_run_id": str(node.id),
            "execution_fingerprint": node.execution_fingerprint,
        }
    )
    assert result.status == "SUCCEEDED"
    version = db_session.scalars(select(ArtifactVersion)).first()
    (artifact_root / version.relative_storage_path).write_bytes(b"tampered")
    db_session.commit()

    exit_code = verify_artifacts_main(
        [
            "--database-url",
            str(db_session.get_bind().url),
            "--artifact-root",
            str(artifact_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["total"] == 10
    assert payload["verified"] == 9
    assert len(payload["failures"]) == 1
