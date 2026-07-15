from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.enums import WorkerStatus
from app.db.models import WorkerInstance


def heartbeat_worker(
    session: Session,
    worker_id: str,
    *,
    status: WorkerStatus,
    current_node_run_id: UUID | str | None = None,
) -> WorkerInstance:
    timestamp = datetime.now(UTC)
    normalized_node_run_id = (
        UUID(current_node_run_id)
        if isinstance(current_node_run_id, str)
        else current_node_run_id
    )
    worker = session.get(WorkerInstance, worker_id)
    if worker is None:
        worker = WorkerInstance(
            id=worker_id,
            status=status,
            current_node_run_id=normalized_node_run_id,
            started_at=timestamp,
            heartbeat_at=timestamp,
            hostname=socket.gethostname(),
            process_id=os.getpid(),
        )
        session.add(worker)
    else:
        worker.status = status
        worker.current_node_run_id = normalized_node_run_id
        worker.heartbeat_at = timestamp
    session.commit()
    return worker
