from __future__ import annotations

import pytest

from app.domain.workflow import (
    ApprovalDecision,
    ApprovalStatus,
    InvalidTransition,
    NodeStatus,
    TaskStatus,
    build_initial_workflow,
    decide_task_start,
)


def test_initial_workflow_has_exactly_three_frozen_nodes() -> None:
    workflow = build_initial_workflow()

    assert workflow.task_status is TaskStatus.WAITING_FOR_APPROVAL
    assert workflow.approval_status is ApprovalStatus.PENDING
    assert [(node.key, node.status) for node in workflow.nodes] == [
        ("task_start_approval", NodeStatus.WAITING_FOR_APPROVAL),
        ("material_ingest", NodeStatus.PENDING),
        ("project_fact_review", NodeStatus.PENDING),
    ]


def test_approval_moves_only_ingest_to_ready() -> None:
    approved = decide_task_start(
        build_initial_workflow(), ApprovalDecision.APPROVE
    )

    assert approved.task_status is TaskStatus.RUNNING
    assert approved.approval_status is ApprovalStatus.APPROVED
    assert approved.node("task_start_approval").status is NodeStatus.SUCCEEDED
    assert approved.node("material_ingest").status is NodeStatus.READY
    assert approved.node("project_fact_review").status is NodeStatus.PENDING


def test_rejection_blocks_task_without_queueing_ingest() -> None:
    rejected = decide_task_start(
        build_initial_workflow(), ApprovalDecision.REJECT
    )

    assert rejected.task_status is TaskStatus.BLOCKED
    assert rejected.approval_status is ApprovalStatus.REJECTED
    assert rejected.node("task_start_approval").status is NodeStatus.FAILED
    assert rejected.node("material_ingest").status is NodeStatus.BLOCKED


def test_decided_approval_cannot_be_decided_twice() -> None:
    approved = decide_task_start(
        build_initial_workflow(), ApprovalDecision.APPROVE
    )

    with pytest.raises(InvalidTransition, match="approval is already decided"):
        decide_task_start(approved, ApprovalDecision.APPROVE)
