from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import OutboxStatus
from app.db.models import OutboxEvent


class StreamPublisher(Protocol):
    def publish(self, fields: dict[str, str]) -> str: ...


@dataclass(frozen=True, slots=True)
class PublishBatchResult:
    published: int
    failed: int


class OutboxPublisher:
    def __init__(self, stream: StreamPublisher, *, batch_size: int = 50) -> None:
        self.stream = stream
        self.batch_size = batch_size

    def publish_batch(self, session: Session) -> PublishBatchResult:
        events = session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(self.batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        published = 0
        failed = 0
        for event in events:
            event.publish_attempt_count += 1
            event.last_error = None
            try:
                self.stream.publish(_stream_fields(event))
            except Exception as exc:  # transport boundary; event remains retryable
                event.last_error = str(exc)[:4000]
                failed += 1
                continue
            event.status = OutboxStatus.PUBLISHED
            event.published_at = datetime.now(UTC)
            published += 1
        session.commit()
        return PublishBatchResult(published=published, failed=failed)


def _stream_fields(event: OutboxEvent) -> dict[str, str]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "node_run_id": str(
            event.payload_json.get("node_run_id", event.aggregate_id)
        ),
        "execution_fingerprint": str(
            event.payload_json.get("execution_fingerprint", "")
        ),
    }
