from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.worker.leases import LeaseService


LOGGER = logging.getLogger("thesis_platform.worker.heartbeat")


class LeaseHeartbeat:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        lease_id: UUID,
        lease_token: str,
        interval_seconds: int,
        ttl_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.lease_id = lease_id
        self.lease_token = lease_token
        self.interval_seconds = interval_seconds
        self.ttl_seconds = ttl_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-heartbeat-{lease_id}",
            daemon=True,
        )
        self.error: Exception | None = None

    def __enter__(self) -> LeaseHeartbeat:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1, self.interval_seconds + 1))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                with self.session_factory() as session:
                    LeaseService(session, ttl_seconds=self.ttl_seconds).heartbeat(
                        self.lease_id, lease_token=self.lease_token
                    )
                    session.commit()
            except Exception as exc:
                self.error = exc
                LOGGER.exception("lease heartbeat failed")
                return
