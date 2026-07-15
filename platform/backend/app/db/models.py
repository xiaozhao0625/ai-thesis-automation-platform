from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.enums import (
    ApprovalType,
    ArtifactKind,
    AttemptStatus,
    LeaseStatus,
    OutboxStatus,
    WorkerStatus,
    WorkflowStatus,
)
from app.domain.workflow import ApprovalDecision, ApprovalStatus, NodeStatus, TaskStatus


def enum_column(enum_type: type, name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
    )


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus, "task_status"), nullable=False
    )
    capability_pack: Mapped[str] = mapped_column(String(120), nullable=False)
    source_mount_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)

    approvals: Mapped[list[HumanApproval]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="task")


class HumanApproval(Base):
    __tablename__ = "human_approvals"
    __table_args__ = (
        UniqueConstraint("task_id", "approval_type", name="uq_task_approval_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approval_type: Mapped[ApprovalType] = mapped_column(
        enum_column(ApprovalType, "approval_type"), nullable=False
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus, "approval_status"), nullable=False
    )
    submitted_by: Mapped[str] = mapped_column(String(160), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(160))
    decision: Mapped[ApprovalDecision | None] = mapped_column(
        enum_column(ApprovalDecision, "approval_decision")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task] = relationship(back_populates="approvals")


class WorkflowRun(TimestampMixin, Base):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        enum_column(WorkflowStatus, "workflow_status"), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task] = relationship(back_populates="workflow_runs")
    node_runs: Mapped[list[NodeRun]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )


class NodeRun(TimestampMixin, Base):
    __tablename__ = "node_runs"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "node_key", name="uq_workflow_run_node_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[NodeStatus] = mapped_column(
        enum_column(NodeStatus, "node_status"), nullable=False
    )
    execution_fingerprint: Mapped[str | None] = mapped_column(String(128))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    current_output_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="node_runs")
    attempts: Mapped[list[NodeExecutionAttempt]] = relationship(
        back_populates="node_run", cascade="all, delete-orphan"
    )
    leases: Mapped[list[WorkerLease]] = relationship(back_populates="node_run")
    outputs: Mapped[list[NodeRunOutput]] = relationship(back_populates="node_run")
    logs: Mapped[list[NodeRunLog]] = relationship(back_populates="node_run")


class NodeExecutionAttempt(Base):
    __tablename__ = "node_execution_attempts"
    __table_args__ = (
        UniqueConstraint(
            "node_run_id", "attempt_number", name="uq_node_attempt_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("node_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(160), nullable=False)
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[AttemptStatus] = mapped_column(
        enum_column(AttemptStatus, "attempt_status"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_reason: Mapped[str | None] = mapped_column(Text)

    node_run: Mapped[NodeRun] = relationship(back_populates="attempts")
    artifact_versions: Mapped[list[ArtifactVersion]] = relationship(
        back_populates="producer_attempt"
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_outbox_deduplication_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        enum_column(OutboxStatus, "outbox_status"), nullable=False
    )
    publish_attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerLease(TimestampMixin, Base):
    __tablename__ = "worker_leases"
    __table_args__ = (
        Index(
            "uq_worker_leases_active_node",
            "node_run_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("node_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    worker_id: Mapped[str] = mapped_column(String(160), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[LeaseStatus] = mapped_column(
        enum_column(LeaseStatus, "lease_status"), nullable=False
    )

    node_run: Mapped[NodeRun] = relationship(back_populates="leases")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[ArtifactKind] = mapped_column(
        enum_column(ArtifactKind, "artifact_kind"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    task: Mapped[Task] = relationship(back_populates="artifacts")
    versions: Mapped[list[ArtifactVersion]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_artifact_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    relative_storage_path: Mapped[str] = mapped_column(String(1200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    producer_attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("node_execution_attempts.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    artifact: Mapped[Artifact] = relationship(back_populates="versions")
    producer_attempt: Mapped[NodeExecutionAttempt] = relationship(
        back_populates="artifact_versions"
    )
    node_outputs: Mapped[list[NodeRunOutput]] = relationship(
        back_populates="artifact_version"
    )


class NodeRunOutput(Base):
    __tablename__ = "node_run_outputs"
    __table_args__ = (
        UniqueConstraint(
            "node_run_id",
            "artifact_version_id",
            "output_role",
            name="uq_node_output_version_role",
        ),
        Index(
            "uq_node_outputs_current_role",
            "node_run_id",
            "output_role",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("node_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    output_role: Mapped[str] = mapped_column(String(120), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    node_run: Mapped[NodeRun] = relationship(back_populates="outputs")
    artifact_version: Mapped[ArtifactVersion] = relationship(
        back_populates="node_outputs"
    )


class NodeRunLog(Base):
    __tablename__ = "node_run_logs"
    __table_args__ = (
        UniqueConstraint("node_run_id", "sequence", name="uq_node_log_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("node_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("node_execution_attempts.id", ondelete="SET NULL")
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    event: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    node_run: Mapped[NodeRun] = relationship(back_populates="logs")


class WorkerInstance(TimestampMixin, Base):
    __tablename__ = "worker_instances"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[WorkerStatus] = mapped_column(
        enum_column(WorkerStatus, "worker_status"), nullable=False
    )
    current_node_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    hostname: Mapped[str] = mapped_column(String(240), nullable=False)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
