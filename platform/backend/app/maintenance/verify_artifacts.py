from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.store import ArtifactHashMismatch, LocalArtifactStore
from app.db.models import ArtifactVersion


@dataclass(frozen=True, slots=True)
class ArtifactVerificationFailure:
    artifact_version_id: str
    relative_storage_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class ArtifactVerificationReport:
    total: int
    verified: int
    failures: tuple[ArtifactVerificationFailure, ...]


def verify_all_artifacts(
    session: Session,
    store: LocalArtifactStore,
) -> ArtifactVerificationReport:
    versions = session.scalars(
        select(ArtifactVersion).order_by(ArtifactVersion.created_at, ArtifactVersion.id)
    ).all()
    failures: list[ArtifactVerificationFailure] = []
    for version in versions:
        try:
            payload = store.read_verified(
                version.relative_storage_path,
                version.content_hash,
            )
            if len(payload) != version.size_bytes:
                raise ValueError(
                    f"size mismatch: expected {version.size_bytes}, got {len(payload)}"
                )
        except (ArtifactHashMismatch, OSError, ValueError) as exc:
            failures.append(
                ArtifactVerificationFailure(
                    artifact_version_id=str(version.id),
                    relative_storage_path=version.relative_storage_path,
                    reason=str(exc),
                )
            )
    return ArtifactVerificationReport(
        total=len(versions),
        verified=len(versions) - len(failures),
        failures=tuple(failures),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify every ArtifactVersion against the Artifact Store"
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args(argv)

    engine = create_engine(args.database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as session:
            report = verify_all_artifacts(
                session,
                LocalArtifactStore(args.artifact_root),
            )
    finally:
        engine.dispose()
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
