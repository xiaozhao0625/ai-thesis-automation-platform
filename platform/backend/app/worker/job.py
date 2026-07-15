from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.recorder import ArtifactRecorder
from app.artifacts.store import LocalArtifactStore
from app.core.errors import ApplicationError
from app.db.enums import AttemptStatus, LeaseStatus, OutboxStatus
from app.db.models import (
    NodeExecutionAttempt,
    NodeRun,
    OutboxEvent,
    Task,
    WorkerLease,
    WorkflowRun,
)
from app.domain.workflow import NodeStatus
from app.ingest_adapter.adapter import IngestCliAdapter
from app.ingest_adapter.paths import ControlledSourceResolver
from app.worker.leases import LeaseService, _append_log
from app.worker.heartbeat import LeaseHeartbeat
from app.workflow.service import MATERIAL_INGEST_EVENT


@dataclass(frozen=True, slots=True)
class MaterialJobResult:
    status: str
    attempt_id: UUID | None = None
    output_count: int = 0


class MaterialIngestJobHandler:
    def __init__(
        self,
        *,
        session: Session,
        worker_id: str,
        source_resolver: ControlledSourceResolver,
        adapter: IngestCliAdapter,
        artifact_store: LocalArtifactStore,
        heartbeat_session_factory: Callable[[], Session] | None = None,
        heartbeat_interval_seconds: int = 15,
        lease_ttl_seconds: int = 60,
    ) -> None:
        self.session = session
        self.worker_id = worker_id
        self.source_resolver = source_resolver
        self.adapter = adapter
        self.artifact_store = artifact_store
        self.heartbeat_session_factory = heartbeat_session_factory
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.lease_ttl_seconds = lease_ttl_seconds

    def handle(self, message: dict[str, str]) -> MaterialJobResult:
        node_run_id = UUID(message["node_run_id"])
        fingerprint = message.get("execution_fingerprint")
        claim = LeaseService(self.session).claim(
            node_run_id,
            execution_fingerprint=fingerprint,
            worker_id=self.worker_id,
        )
        self.session.commit()
        if not claim.should_execute:
            return MaterialJobResult("DUPLICATE_ALREADY_SUCCEEDED")
        assert claim.attempt is not None and claim.lease is not None

        node, workflow, task = self._load_context(node_run_id)
        heartbeat = (
            LeaseHeartbeat(
                session_factory=self.heartbeat_session_factory,
                lease_id=claim.lease.id,
                lease_token=claim.lease.lease_token,
                interval_seconds=self.heartbeat_interval_seconds,
                ttl_seconds=self.lease_ttl_seconds,
            )
            if self.heartbeat_session_factory is not None
            else None
        )
        try:
            source_root = self.source_resolver.resolve(task.source_mount_path)
            if heartbeat is None:
                cli_result = self.adapter.scan_and_verify(
                    source_root=source_root,
                    task_id=task.id,
                    node_run_id=node.id,
                    attempt_id=claim.attempt.id,
                )
            else:
                with heartbeat:
                    cli_result = self.adapter.scan_and_verify(
                        source_root=source_root,
                        task_id=task.id,
                        node_run_id=node.id,
                        attempt_id=claim.attempt.id,
                    )
                if heartbeat.error is not None:
                    raise heartbeat.error
            self.session.refresh(claim.lease)
            if (
                claim.lease.status is not LeaseStatus.ACTIVE
                or claim.lease.expires_at <= datetime.now(UTC)
            ):
                raise ApplicationError(
                    "LEASE_EXPIRED", "lease expired before result commit"
                )
            versions = ArtifactRecorder(
                self.session, self.artifact_store
            ).archive_and_record(
                cli_result.output_files,
                task_id=task.id,
                node_run_id=node.id,
                attempt_id=claim.attempt.id,
            )
            self._finish_success(
                node=node,
                workflow=workflow,
                attempt=claim.attempt,
                lease=claim.lease,
                output_count=len(versions),
                summary=cli_result.summary,
            )
            self.session.commit()
            return MaterialJobResult(
                "SUCCEEDED", attempt_id=claim.attempt.id, output_count=len(versions)
            )
        except Exception as exc:
            self.session.rollback()
            code, message_text = _error_details(exc)
            status = self._finish_failure(
                node_run_id=node_run_id,
                attempt_id=claim.attempt.id,
                lease_id=claim.lease.id,
                code=code,
                message=message_text,
            )
            self.session.commit()
            return MaterialJobResult(status, attempt_id=claim.attempt.id)

    def _load_context(self, node_run_id: UUID) -> tuple[NodeRun, WorkflowRun, Task]:
        row = self.session.execute(
            select(NodeRun, WorkflowRun, Task)
            .join(WorkflowRun, WorkflowRun.id == NodeRun.workflow_run_id)
            .join(Task, Task.id == WorkflowRun.task_id)
            .where(NodeRun.id == node_run_id)
        ).one()
        return row[0], row[1], row[2]

    def _finish_success(
        self,
        *,
        node: NodeRun,
        workflow: WorkflowRun,
        attempt: NodeExecutionAttempt,
        lease: WorkerLease,
        output_count: int,
        summary: dict[str, object],
    ) -> None:
        timestamp = datetime.now(UTC)
        attempt.status = AttemptStatus.SUCCEEDED
        attempt.finished_at = timestamp
        attempt.heartbeat_at = timestamp
        lease.status = LeaseStatus.COMPLETED
        lease.heartbeat_at = timestamp
        node.status = NodeStatus.SUCCEEDED
        node.current_output_count = output_count
        project_fact = self.session.scalar(
            select(NodeRun).where(
                NodeRun.workflow_run_id == workflow.id,
                NodeRun.node_key == "project_fact_review",
            )
        )
        if project_fact is not None:
            project_fact.status = NodeStatus.WAITING_FOR_APPROVAL
        _append_log(
            self.session,
            node,
            attempt,
            "INGEST_SUCCEEDED",
            "Ingest CLI scan and verify completed",
            timestamp,
        )
        _append_log(
            self.session,
            node,
            attempt,
            "ARTIFACTS_ARCHIVED",
            f"Archived {output_count} immutable outputs; total_files="
            f"{summary.get('total_files')}",
            timestamp,
        )

    def _finish_failure(
        self,
        *,
        node_run_id: UUID,
        attempt_id: UUID,
        lease_id: UUID,
        code: str,
        message: str,
    ) -> str:
        timestamp = datetime.now(UTC)
        node = self.session.scalar(
            select(NodeRun).where(NodeRun.id == node_run_id).with_for_update()
        )
        attempt = self.session.scalar(
            select(NodeExecutionAttempt)
            .where(NodeExecutionAttempt.id == attempt_id)
            .with_for_update()
        )
        lease = self.session.scalar(
            select(WorkerLease)
            .where(WorkerLease.id == lease_id)
            .with_for_update()
        )
        assert node is not None and attempt is not None and lease is not None
        attempt.status = AttemptStatus.FAILED
        attempt.finished_at = timestamp
        attempt.error_code = code
        attempt.error_message = message[:4000]
        lease.status = LeaseStatus.RELEASED
        if node.attempt_count >= node.max_attempts:
            node.status = NodeStatus.FAILED
            _append_log(
                self.session,
                node,
                attempt,
                "NODE_FAILED",
                f"{code}: {message}",
                timestamp,
            )
            return "FAILED"

        node.status = NodeStatus.RETRYING
        _append_log(
            self.session,
            node,
            attempt,
            "NODE_RETRYING",
            f"{code}: {message}",
            timestamp,
        )
        node.status = NodeStatus.QUEUED
        self.session.add(
            OutboxEvent(
                aggregate_type="NodeRun",
                aggregate_id=node.id,
                event_type=MATERIAL_INGEST_EVENT,
                payload_json={
                    "node_run_id": str(node.id),
                    "execution_fingerprint": node.execution_fingerprint,
                    "event_type": MATERIAL_INGEST_EVENT,
                },
                deduplication_key=(
                    f"material-ingest:{node.id}:{node.execution_fingerprint}:"
                    f"retry-{node.attempt_count}"
                ),
                status=OutboxStatus.PENDING,
                publish_attempt_count=0,
                created_at=timestamp,
            )
        )
        _append_log(
            self.session,
            node,
            attempt,
            "NODE_QUEUED",
            "Retry Outbox event created",
            timestamp,
        )
        return "RETRY_SCHEDULED"


def _error_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, ApplicationError):
        return exc.code, exc.message
    return "INGEST_EXECUTION_FAILED", str(exc)
