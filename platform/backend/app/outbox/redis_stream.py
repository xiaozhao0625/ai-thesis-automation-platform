from __future__ import annotations

from redis import Redis


class RedisStreamPublisher:
    def __init__(self, client: Redis, stream_name: str) -> None:
        self.client = client
        self.stream_name = stream_name

    def publish(self, fields: dict[str, str]) -> str:
        message_id = self.client.xadd(self.stream_name, fields)
        if isinstance(message_id, bytes):
            return message_id.decode("ascii")
        return str(message_id)
