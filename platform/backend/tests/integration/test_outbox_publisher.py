from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.enums import OutboxStatus
from app.db.models import OutboxEvent
from app.outbox.publisher import OutboxPublisher


class RecordingStream:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict[str, str]] = []

    def publish(self, fields: dict[str, str]) -> str:
        self.messages.append(fields)
        if self.fail:
            raise ConnectionError("redis unavailable")
        return f"stream-{len(self.messages)}"


def pending_event() -> OutboxEvent:
    node_id = uuid4()
    return OutboxEvent(
        aggregate_type="NodeRun",
        aggregate_id=node_id,
        event_type="MATERIAL_INGEST_REQUESTED",
        payload_json={
            "node_run_id": str(node_id),
            "execution_fingerprint": "sha256:abc",
        },
        deduplication_key=f"test:{node_id}",
        status=OutboxStatus.PENDING,
        publish_attempt_count=0,
        created_at=datetime.now(UTC),
    )


@pytest.mark.postgres
@pytest.mark.integration
def test_publisher_writes_stable_stream_message_and_marks_published(
    db_session,
) -> None:
    event = pending_event()
    db_session.add(event)
    db_session.commit()
    stream = RecordingStream()

    result = OutboxPublisher(stream).publish_batch(db_session)

    db_session.refresh(event)
    assert result.published == 1
    assert result.failed == 0
    assert event.status is OutboxStatus.PUBLISHED
    assert event.publish_attempt_count == 1
    assert event.published_at is not None
    assert stream.messages == [
        {
            "event_id": str(event.id),
            "event_type": "MATERIAL_INGEST_REQUESTED",
            "node_run_id": str(event.aggregate_id),
            "execution_fingerprint": "sha256:abc",
        }
    ]


@pytest.mark.postgres
@pytest.mark.integration
def test_redis_failure_keeps_event_pending_for_later_retry(db_session) -> None:
    event = pending_event()
    db_session.add(event)
    db_session.commit()

    result = OutboxPublisher(RecordingStream(fail=True)).publish_batch(db_session)

    db_session.refresh(event)
    assert result.published == 0
    assert result.failed == 1
    assert event.status is OutboxStatus.PENDING
    assert event.publish_attempt_count == 1
    assert event.published_at is None
    assert event.last_error == "redis unavailable"
    assert db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.status == OutboxStatus.PENDING)
    ).one()
