from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.errors import DomainConflict
from app.db.enums import AttemptStatus, LeaseStatus, OutboxStatus, WorkerStatus
from app.db.models import NodeExecutionAttempt, NodeRun, OutboxEvent, WorkerLease
from app.domain.workflow import ApprovalDecision, NodeStatus
from app.worker.leases import LeaseService, RecoveryCoordinator
from app.worker.registry import heartbeat_worker
from app.workflow.service import TaskWorkflowService


def queued_material(db_session) -> NodeRun:
    workflow = TaskWorkflowService(db_session)
    created = workflow.create_task(
        title="实验室设备管理系统",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
    )
    db_session.commit()
    workflow.decide_task_start(
        created.approval.id,
        decision=ApprovalDecision.APPROVE,
        decided_by="reviewer-01",
    )
    db_session.commit()
    return db_session.scalar(
        select(NodeRun).where(
            NodeRun.workflow_run_id == created.workflow.id,
            NodeRun.node_key == "material_ingest",
        )
    )


@pytest.mark.postgres
@pytest.mark.integration
def test_claim_creates_single_active_lease_and_immutable_attempt(db_session) -> None:
    node = queued_material(db_session)
    now = datetime(2026, 7, 16, 2, 0, tzinfo=UTC)

    claimed = LeaseService(db_session).claim(
        node.id,
        execution_fingerprint=node.execution_fingerprint,
        worker_id="worker-01",
        now=now,
    )
    db_session.commit()

    assert claimed.should_execute is True
    assert claimed.attempt.attempt_number == 1
    assert claimed.attempt.status is AttemptStatus.RUNNING
    assert claimed.lease.status is LeaseStatus.ACTIVE
    assert claimed.lease.expires_at == now + timedelta(seconds=60)
    assert claimed.attempt.lease_id == claimed.lease.id
    assert node.status is NodeStatus.RUNNING
    assert node.attempt_count == 1


@pytest.mark.postgres
@pytest.mark.integration
def test_second_worker_cannot_claim_node_with_valid_lease(db_session) -> None:
    node = queued_material(db_session)
    service = LeaseService(db_session)
    now = datetime(2026, 7, 16, 2, 0, tzinfo=UTC)
    service.claim(
        node.id,
        execution_fingerprint=node.execution_fingerprint,
        worker_id="worker-01",
        now=now,
    )
    db_session.commit()

    with pytest.raises(DomainConflict) as raised:
        service.claim(
            node.id,
            execution_fingerprint=node.execution_fingerprint,
            worker_id="worker-02",
            now=now + timedelta(seconds=10),
        )

    assert raised.value.code == "LEASE_NOT_AVAILABLE"
    assert len(db_session.scalars(select(NodeExecutionAttempt)).all()) == 1


@pytest.mark.postgres
@pytest.mark.integration
def test_heartbeat_extends_lease_and_attempt_heartbeat(db_session) -> None:
    node = queued_material(db_session)
    service = LeaseService(db_session)
    now = datetime(2026, 7, 16, 2, 0, tzinfo=UTC)
    claimed = service.claim(
        node.id,
        execution_fingerprint=node.execution_fingerprint,
        worker_id="worker-01",
        now=now,
    )
    db_session.commit()

    service.heartbeat(
        claimed.lease.id,
        lease_token=claimed.lease.lease_token,
        now=now + timedelta(seconds=15),
    )
    db_session.commit()

    assert claimed.lease.heartbeat_at == now + timedelta(seconds=15)
    assert claimed.lease.expires_at == now + timedelta(seconds=75)
    assert claimed.attempt.heartbeat_at == now + timedelta(seconds=15)


@pytest.mark.postgres
@pytest.mark.integration
def test_expired_lease_is_audited_and_requeued_without_losing_attempt(
    db_session,
) -> None:
    node = queued_material(db_session)
    service = LeaseService(db_session)
    now = datetime(2026, 7, 16, 2, 0, tzinfo=UTC)
    first = service.claim(
        node.id,
        execution_fingerprint=node.execution_fingerprint,
        worker_id="worker-01",
        now=now,
    )
    db_session.commit()

    result = RecoveryCoordinator(db_session).recover_expired(
        now=now + timedelta(seconds=61)
    )
    db_session.commit()

    assert result.requeued == 1
    assert first.lease.status is LeaseStatus.EXPIRED
    assert first.attempt.status is AttemptStatus.FAILED
    assert first.attempt.error_code == "LEASE_EXPIRED"
    assert node.status is NodeStatus.QUEUED
    recovery_event = db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.status == OutboxStatus.PENDING)
    ).all()[-1]
    assert recovery_event.payload_json["node_run_id"] == str(node.id)

    second = service.claim(
        node.id,
        execution_fingerprint=node.execution_fingerprint,
        worker_id="worker-02",
        now=now + timedelta(seconds=62),
    )
    assert second.attempt.attempt_number == 2


@pytest.mark.postgres
@pytest.mark.integration
def test_third_expired_attempt_transitions_node_to_failed(db_session) -> None:
    node = queued_material(db_session)
    service = LeaseService(db_session)
    recovery = RecoveryCoordinator(db_session)
    now = datetime(2026, 7, 16, 2, 0, tzinfo=UTC)

    for attempt_number in range(1, 4):
        claimed = service.claim(
            node.id,
            execution_fingerprint=node.execution_fingerprint,
            worker_id=f"worker-{attempt_number}",
            now=now,
        )
        db_session.commit()
        result = recovery.recover_expired(
            now=now + timedelta(seconds=61)
        )
        db_session.commit()
        now += timedelta(seconds=62)

    assert result.failed == 1
    assert claimed.attempt.status is AttemptStatus.FAILED
    assert node.status is NodeStatus.FAILED
    assert node.attempt_count == 3


@pytest.mark.postgres
@pytest.mark.integration
def test_fingerprint_mismatch_is_rejected_before_attempt_creation(db_session) -> None:
    node = queued_material(db_session)

    with pytest.raises(DomainConflict) as raised:
        LeaseService(db_session).claim(
            node.id,
            execution_fingerprint="sha256:different",
            worker_id="worker-01",
        )

    assert raised.value.code == "EXECUTION_FINGERPRINT_MISMATCH"
    assert not db_session.scalars(select(WorkerLease)).all()


@pytest.mark.postgres
@pytest.mark.integration
def test_worker_heartbeat_normalizes_stream_node_id_to_uuid(db_session) -> None:
    node = queued_material(db_session)

    worker = heartbeat_worker(
        db_session,
        "worker-stream-01",
        status=WorkerStatus.BUSY,
        current_node_run_id=str(node.id),
    )

    assert worker.current_node_run_id == node.id
