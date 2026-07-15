from __future__ import annotations

import os
import uuid

import pytest
from redis import Redis

from app.outbox.redis_stream import RedisStreamPublisher
from app.worker.redis_consumer import RedisStreamConsumer


@pytest.mark.redis
@pytest.mark.integration
def test_real_redis_stream_publish_consume_and_ack() -> None:
    if os.getenv("RUN_REDIS_TESTS") != "1":
        pytest.skip("set RUN_REDIS_TESTS=1 when a real Redis service is available")
    client = Redis.from_url(
        os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=False,
    )
    client.ping()
    suffix = uuid.uuid4().hex
    stream = f"test:thesis:jobs:{suffix}"
    group = f"test:workers:{suffix}"
    consumer = RedisStreamConsumer(
        client,
        stream_name=stream,
        group_name=group,
        consumer_name="worker-integration",
    )
    consumer.ensure_group()
    RedisStreamPublisher(client, stream).publish(
        {
            "event_id": "event-1",
            "event_type": "MATERIAL_INGEST_REQUESTED",
            "node_run_id": "00000000-0000-0000-0000-000000000001",
            "execution_fingerprint": "sha256:abc",
        }
    )

    message = consumer.read_one(block_milliseconds=1000)

    assert message is not None
    assert message.fields["event_id"] == "event-1"
    assert consumer.ack(message) == 1
    assert client.xpending(stream, group)["pending"] == 0
    client.delete(stream)
