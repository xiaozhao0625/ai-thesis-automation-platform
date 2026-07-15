from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainConflict, ResourceNotFound
from app.db.enums import ApprovalType, OutboxStatus, WorkflowStatus
from app.db.models import (
    HumanApproval,
    NodeRun,
    NodeRunLog,
    OutboxEvent,
    Task,
    WorkflowRun,
)
from app.domain.workflow import ApprovalDecision, ApprovalStatus, NodeStatus, TaskStatus


WORKFLOW_DEFINITION_VERSION = "p1-1.v1"
MATERIAL_INGEST_EVENT = "MATERIAL_INGEST_REQUESTED"


@dataclass(slots=True)
class CreatedTaskWorkflow:
    task: Task
    approval: HumanApproval
    workflow: WorkflowRun
    nodes: list[NodeRun]


class TaskWorkflowService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_task(
        self,
        *,
        title: str,
        capability_pack: str,
        source_mount_path: str,
        created_by: str,
        now: datetime | None = None,
    ) -> CreatedTaskWorkflow:
        timestamp = now or datetime.now(UTC)
        task = Task(
            title=title,
            status=TaskStatus.WAITING_FOR_APPROVAL,
            capability_pack=capability_pack,
            source_mount_path=source_mount_path,
            created_by=created_by,
        )
        self.session.add(task)
        self.session.flush()

        approval = HumanApproval(
            task_id=task.id,
            approval_type=ApprovalType.TASK_START,
            status=ApprovalStatus.PENDING,
            submitted_by=created_by,
            submitted_at=timestamp,
        )
        workflow = WorkflowRun(
            task_id=task.id,
            definition_version=WORKFLOW_DEFINITION_VERSION,
            status=WorkflowStatus.WAITING_FOR_APPROVAL,
        )
        self.session.add_all([approval, workflow])
        self.session.flush()

        nodes = [
            NodeRun(
                workflow_run_id=workflow.id,
                node_key="task_start_approval",
                display_name="启动审批",
                status=NodeStatus.WAITING_FOR_APPROVAL,
                max_attempts=1,
            ),
            NodeRun(
                workflow_run_id=workflow.id,
                node_key="material_ingest",
                display_name="资料摄取",
                status=NodeStatus.PENDING,
                max_attempts=3,
            ),
            NodeRun(
                workflow_run_id=workflow.id,
                node_key="project_fact_review",
                display_name="ProjectFact 人工确认",
                status=NodeStatus.PENDING,
                max_attempts=1,
            ),
        ]
        self.session.add_all(nodes)
        self.session.flush()
        return CreatedTaskWorkflow(task, approval, workflow, nodes)

    def decide_task_start(
        self,
        approval_id: UUID,
        *,
        decision: ApprovalDecision,
        decided_by: str,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> HumanApproval:
        timestamp = now or datetime.now(UTC)
        approval = self.session.scalar(
            select(HumanApproval)
            .where(HumanApproval.id == approval_id)
            .with_for_update()
        )
        if approval is None:
            raise ResourceNotFound(
                "APPROVAL_NOT_FOUND", "approval does not exist"
            )
        if approval.status is not ApprovalStatus.PENDING:
            raise DomainConflict(
                "APPROVAL_ALREADY_DECIDED", "approval is already decided"
            )

        task = self.session.get(Task, approval.task_id)
        workflow = self.session.scalar(
            select(WorkflowRun)
            .where(WorkflowRun.task_id == approval.task_id)
            .with_for_update()
        )
        if task is None or workflow is None:
            raise ResourceNotFound(
                "WORKFLOW_NOT_FOUND", "task workflow does not exist"
            )
        nodes = self.session.scalars(
            select(NodeRun)
            .where(NodeRun.workflow_run_id == workflow.id)
            .with_for_update()
        ).all()
        by_key = {node.node_key: node for node in nodes}

        approval.decided_by = decided_by
        approval.decision = decision
        approval.comment = comment
        approval.decided_at = timestamp

        if decision is ApprovalDecision.REJECT:
            approval.status = ApprovalStatus.REJECTED
            task.status = TaskStatus.BLOCKED
            workflow.status = WorkflowStatus.BLOCKED
            workflow.finished_at = timestamp
            by_key["task_start_approval"].status = NodeStatus.FAILED
            by_key["material_ingest"].status = NodeStatus.BLOCKED
            by_key["project_fact_review"].status = NodeStatus.BLOCKED
            self.session.flush()
            return approval

        approval.status = ApprovalStatus.APPROVED
        task.status = TaskStatus.RUNNING
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = timestamp
        by_key["task_start_approval"].status = NodeStatus.SUCCEEDED
        material = by_key["material_ingest"]
        material.execution_fingerprint = _execution_fingerprint(task, workflow, material)

        material.status = NodeStatus.READY
        self.session.add(
            _node_log(
                material,
                1,
                "NODE_READY",
                "启动审批已通过，资料摄取节点就绪",
                timestamp,
            )
        )
        material.status = NodeStatus.QUEUED
        self.session.add(
            _node_log(
                material,
                2,
                "NODE_QUEUED",
                "资料摄取节点已写入 Outbox",
                timestamp,
            )
        )
        outbox = OutboxEvent(
            aggregate_type="NodeRun",
            aggregate_id=material.id,
            event_type=MATERIAL_INGEST_EVENT,
            payload_json={
                "node_run_id": str(material.id),
                "workflow_run_id": str(workflow.id),
                "task_id": str(task.id),
                "execution_fingerprint": material.execution_fingerprint,
                "event_type": MATERIAL_INGEST_EVENT,
            },
            deduplication_key=(
                f"material-ingest:{material.id}:{material.execution_fingerprint}:initial"
            ),
            status=OutboxStatus.PENDING,
            publish_attempt_count=0,
            created_at=timestamp,
        )
        self.session.add(outbox)
        self.session.flush()
        return approval


def _execution_fingerprint(
    task: Task, workflow: WorkflowRun, material: NodeRun
) -> str:
    payload = json.dumps(
        {
            "capability_pack": task.capability_pack,
            "definition_version": workflow.definition_version,
            "node_key": material.node_key,
            "source_mount_path": task.source_mount_path,
            "task_id": str(task.id),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _node_log(
    node: NodeRun,
    sequence: int,
    event: str,
    message: str,
    timestamp: datetime,
) -> NodeRunLog:
    return NodeRunLog(
        node_run_id=node.id,
        sequence=sequence,
        level="INFO",
        event=event,
        message=message,
        details_json={"status": node.status.value},
        created_at=timestamp,
    )
