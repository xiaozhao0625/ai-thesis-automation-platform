from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import LeaseStatus
from app.db.models import WorkerLease
from app.db.session import get_session_factory
from app.worker.leases import RecoveryCoordinator, RecoveryResult


def reconcile_restored_database(
    session: Session,
    *,
    expire_active: bool,
    now: datetime | None = None,
) -> RecoveryResult:
    timestamp = now or datetime.now(UTC)
    if expire_active:
        leases = session.scalars(
            select(WorkerLease)
            .where(WorkerLease.status == LeaseStatus.ACTIVE)
            .with_for_update()
        ).all()
        for lease in leases:
            lease.expires_at = timestamp
        session.flush()
    return RecoveryCoordinator(session).recover_expired(now=timestamp)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile queued/running work after database restore"
    )
    parser.add_argument("--expire-active", action="store_true")
    args = parser.parse_args()
    with get_session_factory()() as session:
        result = reconcile_restored_database(
            session, expire_active=args.expire_active
        )
        session.commit()
    print(json.dumps({"requeued": result.requeued, "failed": result.failed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
