from __future__ import annotations

import logging
import time

from redis import Redis

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.outbox.publisher import OutboxPublisher
from app.outbox.redis_stream import RedisStreamPublisher


LOGGER = logging.getLogger("thesis_platform.outbox")


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    publisher = OutboxPublisher(
        RedisStreamPublisher(client, settings.redis_stream)
    )
    factory = get_session_factory()
    while True:
        try:
            with factory() as session:
                result = publisher.publish_batch(session)
            if result.published or result.failed:
                LOGGER.info(
                    "outbox batch published=%s failed=%s",
                    result.published,
                    result.failed,
                )
        except KeyboardInterrupt:
            return
        except Exception:
            LOGGER.exception("outbox publisher iteration failed")
        time.sleep(0.5)


if __name__ == "__main__":
    run_forever()
