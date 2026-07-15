from __future__ import annotations

from dataclasses import dataclass

from redis.exceptions import ResponseError


@dataclass(frozen=True, slots=True)
class StreamMessage:
    message_id: str
    fields: dict[str, str]


class RedisStreamConsumer:
    def __init__(
        self,
        client,
        *,
        stream_name: str,
        group_name: str,
        consumer_name: str,
    ) -> None:
        self.client = client
        self.stream_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name

    def ensure_group(self) -> None:
        try:
            self.client.xgroup_create(
                self.stream_name, self.group_name, id="0-0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read_one(self, *, block_milliseconds: int) -> StreamMessage | None:
        response = self.client.xreadgroup(
            self.group_name,
            self.consumer_name,
            {self.stream_name: ">"},
            count=1,
            block=block_milliseconds,
        )
        if not response:
            return None
        _, messages = response[0]
        if not messages:
            return None
        message_id, fields = messages[0]
        return StreamMessage(
            message_id=_decode(message_id),
            fields={_decode(key): _decode(value) for key, value in fields.items()},
        )

    def claim_one_stale(self, *, min_idle_milliseconds: int) -> StreamMessage | None:
        response = self.client.xautoclaim(
            self.stream_name,
            self.group_name,
            self.consumer_name,
            min_idle_milliseconds,
            "0-0",
            count=1,
        )
        messages = response[1] if response and len(response) > 1 else []
        if not messages:
            return None
        message_id, fields = messages[0]
        return StreamMessage(
            message_id=_decode(message_id),
            fields={_decode(key): _decode(value) for key, value in fields.items()},
        )

    def ack(self, message: StreamMessage) -> int:
        return int(
            self.client.xack(
                self.stream_name, self.group_name, message.message_id
            )
        )


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
