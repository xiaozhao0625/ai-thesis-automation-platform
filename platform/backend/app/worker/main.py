from __future__ import annotations

import logging
import socket
import time
import uuid

from redis import Redis

from app.artifacts.store import LocalArtifactStore
from app.core.config import PLATFORM_ROOT, get_settings
from app.core.errors import DomainConflict
from app.db.enums import WorkerStatus
from app.db.session import get_session_factory
from app.ingest_adapter.adapter import IngestCliAdapter
from app.ingest_adapter.paths import ControlledSourceResolver
from app.worker.job import MaterialIngestJobHandler
from app.worker.leases import RecoveryCoordinator
from app.worker.redis_consumer import RedisStreamConsumer
from app.worker.registry import heartbeat_worker


LOGGER = logging.getLogger("thesis_platform.worker")


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    consumer = RedisStreamConsumer(
        redis,
        stream_name=settings.redis_stream,
        group_name=settings.redis_consumer_group,
        consumer_name=worker_id,
    )
    consumer.ensure_group()
    factory = get_session_factory()
    with factory() as session:
        heartbeat_worker(session, worker_id, status=WorkerStatus.ONLINE)
    LOGGER.info("worker started id=%s", worker_id)

    while True:
        try:
            with factory() as session:
                recovered = RecoveryCoordinator(session).recover_expired()
                session.commit()
                if recovered.requeued or recovered.failed:
                    LOGGER.info(
                        "recovery requeued=%s failed=%s",
                        recovered.requeued,
                        recovered.failed,
                    )
                heartbeat_worker(session, worker_id, status=WorkerStatus.ONLINE)

            message = consumer.claim_one_stale(min_idle_milliseconds=60_000)
            if message is None:
                message = consumer.read_one(
                    block_milliseconds=settings.worker_poll_milliseconds
                )
            if message is None:
                continue
            node_run_id = message.fields.get("node_run_id")
            with factory() as session:
                heartbeat_worker(
                    session,
                    worker_id,
                    status=WorkerStatus.BUSY,
                    current_node_run_id=node_run_id,
                )
                handler = MaterialIngestJobHandler(
                    session=session,
                    worker_id=worker_id,
                    source_resolver=ControlledSourceResolver(
                        platform_root=PLATFORM_ROOT,
                        allowed_roots=[settings.benchmark_root],
                        artifact_store_root=settings.artifact_store_root,
                    ),
                    adapter=IngestCliAdapter(
                        cli_src=settings.ingest_cli_src,
                        work_root=settings.ingest_work_root,
                    ),
                    artifact_store=LocalArtifactStore(
                        settings.artifact_store_root
                    ),
                    heartbeat_session_factory=factory,
                    heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
                    lease_ttl_seconds=settings.lease_ttl_seconds,
                )
                try:
                    result = handler.handle(message.fields)
                except DomainConflict as exc:
                    if exc.code != "LEASE_NOT_AVAILABLE":
                        raise
                    LOGGER.info("duplicate leased message skipped id=%s", message.message_id)
                else:
                    LOGGER.info(
                        "message handled id=%s status=%s",
                        message.message_id,
                        result.status,
                    )
                consumer.ack(message)
                heartbeat_worker(session, worker_id, status=WorkerStatus.ONLINE)
        except KeyboardInterrupt:
            return
        except Exception:
            LOGGER.exception("worker iteration failed")
            time.sleep(1)


if __name__ == "__main__":
    run_forever()
