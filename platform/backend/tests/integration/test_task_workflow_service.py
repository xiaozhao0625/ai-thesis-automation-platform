from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.errors import DomainConflict
from app.db.enums import OutboxStatus
from app.db.models import NodeRun, NodeRunLog, OutboxEvent
from app.domain.workflow import ApprovalDecision, NodeStatus, TaskStatus
from app.workflow.service import TaskWorkflowService


@pytest.mark.postgres
@pytest.mark.integration
def test_create_task_persists_approval_workflow_and_exact_nodes(db_session) -> None:
    service = TaskWorkflowService(db_session)

    result = service.create_task(
        title="实验室设备管理系统",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
        now=datetime(2026, 7, 16, tzinfo=UTC),
    )
    db_session.commit()

    assert result.task.status is TaskStatus.WAITING_FOR_APPROVAL
    assert result.approval.task_id == result.task.id
    assert result.workflow.task_id == result.task.id
    assert [(node.node_key, node.status) for node in result.nodes] == [
        ("task_start_approval", NodeStatus.WAITING_FOR_APPROVAL),
        ("material_ingest", NodeStatus.PENDING),
        ("project_fact_review", NodeStatus.PENDING),
    ]


@pytest.mark.postgres
@pytest.mark.integration
def test_approval_atomically_queues_ingest_and_creates_pending_outbox(
    db_session,
) -> None:
    service = TaskWorkflowService(db_session)
    created = service.create_task(
        title="实验室设备管理系统",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
    )
    db_session.commit()

    service.decide_task_start(
        created.approval.id,
        decision=ApprovalDecision.APPROVE,
        decided_by="reviewer-01",
        comment="资料范围已确认",
    )
    db_session.commit()

    nodes = db_session.scalars(
        select(NodeRun)
        .where(NodeRun.workflow_run_id == created.workflow.id)
        .order_by(NodeRun.created_at, NodeRun.node_key)
    ).all()
    by_key = {node.node_key: node for node in nodes}
    outbox = db_session.scalars(select(OutboxEvent)).one()
    transitions = db_session.scalars(
        select(NodeRunLog)
        .where(NodeRunLog.node_run_id == by_key["material_ingest"].id)
        .order_by(NodeRunLog.sequence)
    ).all()

    assert created.task.status is TaskStatus.RUNNING
    assert by_key["task_start_approval"].status is NodeStatus.SUCCEEDED
    assert by_key["material_ingest"].status is NodeStatus.QUEUED
    assert by_key["material_ingest"].execution_fingerprint
    assert by_key["project_fact_review"].status is NodeStatus.PENDING
    assert outbox.status is OutboxStatus.PENDING
    assert outbox.aggregate_id == by_key["material_ingest"].id
    assert outbox.payload_json["execution_fingerprint"] == (
        by_key["material_ingest"].execution_fingerprint
    )
    assert [log.event for log in transitions] == [
        "NODE_READY",
        "NODE_QUEUED",
    ]


@pytest.mark.postgres
@pytest.mark.integration
def test_duplicate_approval_is_rejected_without_second_outbox(db_session) -> None:
    service = TaskWorkflowService(db_session)
    created = service.create_task(
        title="实验室设备管理系统",
        capability_pack="python_web_management_v1",
        source_mount_path="benchmark/ingest-fixture-v1",
        created_by="operator-01",
    )
    db_session.commit()
    service.decide_task_start(
        created.approval.id,
        decision=ApprovalDecision.APPROVE,
        decided_by="reviewer-01",
    )
    db_session.commit()

    with pytest.raises(DomainConflict) as raised:
        service.decide_task_start(
            created.approval.id,
            decision=ApprovalDecision.APPROVE,
            decided_by="reviewer-02",
        )

    assert raised.value.code == "APPROVAL_ALREADY_DECIDED"
    assert len(db_session.scalars(select(OutboxEvent)).all()) == 1
