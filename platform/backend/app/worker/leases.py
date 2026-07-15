from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainConflict, ResourceNotFound
from app.db.enums import AttemptStatus, LeaseStatus, OutboxStatus
from app.db.models import (
    NodeExecutionAttempt,
    NodeRun,
    NodeRunLog,
    OutboxEvent,
    WorkerLease,
)
from app.domain.workflow import NodeStatus
from app.workflow.service import MATERIAL_INGEST_EVENT


@dataclass(frozen=True, slots=True)
class ClaimResult:
    should_execute: bool
    attempt: NodeExecutionAttempt | None
    lease: WorkerLease | None


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    requeued: int
    failed: int


class LeaseService:
    def __init__(self, session: Session, *, ttl_seconds: int = 60) -> None:
        self.session = session
        self.ttl = timedelta(seconds=ttl_seconds)

    def claim(
        self,
        node_run_id: UUID,
        *,
        execution_fingerprint: str | None,
        worker_id: str,
        now: datetime | None = None,
    ) -> ClaimResult:
        timestamp = now or datetime.now(UTC)
        node = self.session.scalar(
            select(NodeRun)
            .where(NodeRun.id == node_run_id)
            .with_for_update()
        )
        if node is None:
            raise ResourceNotFound("NODE_RUN_NOT_FOUND", "node run does not exist")
        if node.execution_fingerprint != execution_fingerprint:
            raise DomainConflict(
                "EXECUTION_FINGERPRINT_MISMATCH",
                "message fingerprint does not match node run",
            )
        if node.status is NodeStatus.SUCCEEDED:
            return ClaimResult(False, None, None)

        active = self.session.scalar(
            select(WorkerLease).where(
                WorkerLease.node_run_id == node.id,
                WorkerLease.status == LeaseStatus.ACTIVE,
            )
        )
        if active is not None and active.expires_at > timestamp:
            raise DomainConflict(
                "LEASE_NOT_AVAILABLE", "node run already has a valid lease"
            )
        if active is not None:
            _expire_lease(self.session, active, node, timestamp)

        if node.attempt_count >= node.max_attempts:
            node.status = NodeStatus.FAILED
            raise DomainConflict(
                "MAX_ATTEMPTS_EXCEEDED", "node run exhausted its attempts"
            )
        if node.status not in {
            NodeStatus.QUEUED,
            NodeStatus.RETRYING,
            NodeStatus.RUNNING,
        }:
            raise DomainConflict(
                "INVALID_STATE_TRANSITION",
                f"cannot claim node in {node.status.value}",
            )

        lease = WorkerLease(
            node_run_id=node.id,
            worker_id=worker_id,
            lease_token=secrets.token_urlsafe(32),
            expires_at=timestamp + self.ttl,
            heartbeat_at=timestamp,
            status=LeaseStatus.ACTIVE,
        )
        self.session.add(lease)
        self.session.flush()
        attempt_number = node.attempt_count + 1
        attempt = NodeExecutionAttempt(
            node_run_id=node.id,
            attempt_number=attempt_number,
            worker_id=worker_id,
            lease_id=lease.id,
            status=AttemptStatus.RUNNING,
            started_at=timestamp,
            heartbeat_at=timestamp,
        )
        self.session.add(attempt)
        node.attempt_count = attempt_number
        node.status = NodeStatus.RUNNING
        self.session.flush()
        _append_log(
            self.session,
            node,
            attempt,
            "NODE_RUNNING",
            f"Worker {worker_id} acquired lease",
            timestamp,
        )
        return ClaimResult(True, attempt, lease)

    def heartbeat(
        self,
        lease_id: UUID,
        *,
        lease_token: str,
        now: datetime | None = None,
    ) -> WorkerLease:
        timestamp = now or datetime.now(UTC)
        lease = self.session.scalar(
            select(WorkerLease)
            .where(WorkerLease.id == lease_id)
            .with_for_update()
        )
        if lease is None:
            raise ResourceNotFound("LEASE_NOT_FOUND", "lease does not exist")
        if lease.lease_token != lease_token:
            raise DomainConflict("LEASE_TOKEN_INVALID", "lease token is invalid")
        if lease.status is not LeaseStatus.ACTIVE or lease.expires_at <= timestamp:
            raise DomainConflict("LEASE_EXPIRED", "lease is no longer valid")

        lease.heartbeat_at = timestamp
        lease.expires_at = timestamp + self.ttl
        attempt = self.session.scalar(
            select(NodeExecutionAttempt).where(
                NodeExecutionAttempt.lease_id == lease.id,
                NodeExecutionAttempt.status == AttemptStatus.RUNNING,
            )
        )
        if attempt is not None:
            attempt.heartbeat_at = timestamp
        self.session.flush()
        return lease


class RecoveryCoordinator:
    def __init__(self, session: Session) -> None:
        self.session = session

    def recover_expired(self, *, now: datetime | None = None) -> RecoveryResult:
        timestamp = now or datetime.now(UTC)
        leases = self.session.scalars(
            select(WorkerLease)
            .where(
                WorkerLease.status == LeaseStatus.ACTIVE,
                WorkerLease.expires_at <= timestamp,
            )
            .with_for_update(skip_locked=True)
        ).all()
        requeued = 0
        failed = 0
        for lease in leases:
            node = self.session.scalar(
                select(NodeRun)
                .where(NodeRun.id == lease.node_run_id)
                .with_for_update()
            )
            if node is None:
                lease.status = LeaseStatus.EXPIRED
                continue
            attempt = _expire_lease(self.session, lease, node, timestamp)
            if node.attempt_count >= node.max_attempts:
                node.status = NodeStatus.FAILED
                failed += 1
                _append_log(
                    self.session,
                    node,
                    attempt,
                    "NODE_FAILED",
                    "Lease expired and maximum attempts were exhausted",
                    timestamp,
                )
                continue

            node.status = NodeStatus.RETRYING
            _append_log(
                self.session,
                node,
                attempt,
                "NODE_RETRYING",
                "Lease expired; scheduling a replacement attempt",
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
                        f"recovery-{node.attempt_count}"
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
                "Recovery Outbox event created",
                timestamp,
            )
            requeued += 1
        self.session.flush()
        return RecoveryResult(requeued=requeued, failed=failed)


def _expire_lease(
    session: Session,
    lease: WorkerLease,
    node: NodeRun,
    timestamp: datetime,
) -> NodeExecutionAttempt | None:
    lease.status = LeaseStatus.EXPIRED
    attempt = session.scalar(
        select(NodeExecutionAttempt).where(
            NodeExecutionAttempt.lease_id == lease.id,
            NodeExecutionAttempt.status == AttemptStatus.RUNNING,
        )
    )
    if attempt is not None:
        attempt.status = AttemptStatus.FAILED
        attempt.finished_at = timestamp
        attempt.error_code = "LEASE_EXPIRED"
        attempt.error_message = "worker heartbeat stopped before lease expiry"
        attempt.retry_reason = "lease expired"
    return attempt


def _append_log(
    session: Session,
    node: NodeRun,
    attempt: NodeExecutionAttempt | None,
    event: str,
    message: str,
    timestamp: datetime,
) -> None:
    sequence = session.scalar(
        select(func.coalesce(func.max(NodeRunLog.sequence), 0)).where(
            NodeRunLog.node_run_id == node.id
        )
    )
    session.add(
        NodeRunLog(
            node_run_id=node.id,
            attempt_id=attempt.id if attempt else None,
            sequence=int(sequence or 0) + 1,
            level="ERROR" if event == "NODE_FAILED" else "INFO",
            event=event,
            message=message,
            details_json={"status": node.status.value},
            created_at=timestamp,
        )
    )
    session.flush()
