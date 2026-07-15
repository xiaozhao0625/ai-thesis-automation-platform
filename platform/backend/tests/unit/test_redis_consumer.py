from __future__ import annotations

from app.worker.redis_consumer import RedisStreamConsumer


class FakeRedis:
    def __init__(self) -> None:
        self.acked: list[tuple[str, str, str]] = []

    def xgroup_create(self, *args, **kwargs):
        return True

    def xreadgroup(self, *args, **kwargs):
        return [
            (
                b"thesis:node-jobs:v1",
                [
                    (
                        b"1720000000000-0",
                        {
                            b"event_id": b"event-1",
                            b"node_run_id": b"00000000-0000-0000-0000-000000000001",
                            b"execution_fingerprint": b"sha256:abc",
                        },
                    )
                ],
            )
        ]

    def xack(self, stream, group, message_id):
        self.acked.append((stream, group, message_id))
        return 1


def test_consumer_decodes_stream_message_and_acknowledges_exact_id() -> None:
    redis = FakeRedis()
    consumer = RedisStreamConsumer(
        redis,
        stream_name="thesis:node-jobs:v1",
        group_name="material-workers:v1",
        consumer_name="worker-01",
    )

    consumer.ensure_group()
    message = consumer.read_one(block_milliseconds=1)

    assert message.message_id == "1720000000000-0"
    assert message.fields["event_id"] == "event-1"
    assert message.fields["execution_fingerprint"] == "sha256:abc"
    assert consumer.ack(message) == 1
    assert redis.acked == [
        (
            "thesis:node-jobs:v1",
            "material-workers:v1",
            "1720000000000-0",
        )
    ]
