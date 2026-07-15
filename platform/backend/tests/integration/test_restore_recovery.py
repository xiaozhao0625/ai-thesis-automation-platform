from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.enums import LeaseStatus
from app.db.models import WorkerLease
from app.worker.leases import LeaseService
from app.worker.recover import reconcile_restored_database
from tests.integration.test_worker_leases import queued_material


@pytest.mark.postgres
@pytest.mark.integration
def test_restore_reconciliation_expires_active_lease_and_requeues(db_session) -> None:
    node = queued_material(db_session)
    LeaseService(db_session).claim(
        node.id,
        execution_fingerprint=node.execution_fingerprint,
        worker_id="worker-old-machine",
        now=datetime(2026, 7, 16, 2, 0, tzinfo=UTC),
    )
    db_session.commit()

    result = reconcile_restored_database(
        db_session,
        expire_active=True,
        now=datetime(2026, 7, 16, 2, 0, tzinfo=UTC),
    )
    db_session.commit()

    lease = db_session.scalars(select(WorkerLease)).one()
    assert result.requeued == 1
    assert lease.status is LeaseStatus.EXPIRED
