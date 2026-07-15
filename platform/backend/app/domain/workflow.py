from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum


class InvalidTransition(ValueError):
    """Raised when a command violates the frozen workflow state machine."""


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class NodeStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True, slots=True)
class NodeSnapshot:
    key: str
    display_name: str
    status: NodeStatus


@dataclass(frozen=True, slots=True)
class WorkflowSnapshot:
    task_status: TaskStatus
    approval_status: ApprovalStatus
    nodes: tuple[NodeSnapshot, ...]

    def node(self, key: str) -> NodeSnapshot:
        try:
            return next(node for node in self.nodes if node.key == key)
        except StopIteration as exc:
            raise KeyError(key) from exc


def build_initial_workflow() -> WorkflowSnapshot:
    return WorkflowSnapshot(
        task_status=TaskStatus.WAITING_FOR_APPROVAL,
        approval_status=ApprovalStatus.PENDING,
        nodes=(
            NodeSnapshot(
                "task_start_approval",
                "启动审批",
                NodeStatus.WAITING_FOR_APPROVAL,
            ),
            NodeSnapshot("material_ingest", "资料摄取", NodeStatus.PENDING),
            NodeSnapshot(
                "project_fact_review", "ProjectFact 人工确认", NodeStatus.PENDING
            ),
        ),
    )


def decide_task_start(
    workflow: WorkflowSnapshot, decision: ApprovalDecision
) -> WorkflowSnapshot:
    if workflow.approval_status is not ApprovalStatus.PENDING:
        raise InvalidTransition("approval is already decided")

    if decision is ApprovalDecision.APPROVE:
        replacements = {
            "task_start_approval": NodeStatus.SUCCEEDED,
            "material_ingest": NodeStatus.READY,
        }
        task_status = TaskStatus.RUNNING
        approval_status = ApprovalStatus.APPROVED
    else:
        replacements = {
            "task_start_approval": NodeStatus.FAILED,
            "material_ingest": NodeStatus.BLOCKED,
            "project_fact_review": NodeStatus.BLOCKED,
        }
        task_status = TaskStatus.BLOCKED
        approval_status = ApprovalStatus.REJECTED

    return WorkflowSnapshot(
        task_status=task_status,
        approval_status=approval_status,
        nodes=tuple(
            replace(node, status=replacements.get(node.key, node.status))
            for node in workflow.nodes
        ),
    )
