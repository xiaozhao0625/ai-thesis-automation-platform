from __future__ import annotations

import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.artifacts.store import ArchivedFile, LocalArtifactStore
from app.db.enums import ArtifactKind
from app.db.models import Artifact, ArtifactVersion, NodeRunOutput


OUTPUT_KIND_BY_NAME = {
    "ingest-manifest.json": ArtifactKind.INGEST_MANIFEST,
    "summary.json": ArtifactKind.INGEST_SUMMARY,
    "artifacts.jsonl": ArtifactKind.INGEST_ARTIFACTS,
    "excluded-items.jsonl": ArtifactKind.INGEST_EXCLUDED_ITEMS,
    "duplicate-groups.jsonl": ArtifactKind.INGEST_DUPLICATE_GROUPS,
    "primary-candidates.jsonl": ArtifactKind.INGEST_PRIMARY_CANDIDATES,
    "reference-candidates.jsonl": ArtifactKind.INGEST_REFERENCE_CANDIDATES,
    "sensitive-items.jsonl": ArtifactKind.INGEST_SENSITIVE_ITEMS,
    "ingest-issues.jsonl": ArtifactKind.INGEST_ISSUES,
    "source-mounts.json": ArtifactKind.SOURCE_MOUNTS,
}


class ArtifactRecorder:
    def __init__(self, session: Session, store: LocalArtifactStore) -> None:
        self.session = session
        self.store = store

    def archive_and_record(
        self,
        files: tuple[Path, ...],
        *,
        task_id: UUID,
        node_run_id: UUID,
        attempt_id: UUID,
        now: datetime | None = None,
    ) -> list[ArtifactVersion]:
        timestamp = now or datetime.now(UTC)
        versions: list[ArtifactVersion] = []
        for path in files:
            kind = OUTPUT_KIND_BY_NAME[path.name]
            archived = self.store.archive(
                path,
                task_id=task_id,
                node_run_id=node_run_id,
                attempt_id=attempt_id,
            )
            versions.append(
                self._record_one(
                    archived,
                    task_id=task_id,
                    node_run_id=node_run_id,
                    attempt_id=attempt_id,
                    kind=kind,
                    timestamp=timestamp,
                )
            )
        self.session.flush()
        return versions

    def _record_one(
        self,
        archived: ArchivedFile,
        *,
        task_id: UUID,
        node_run_id: UUID,
        attempt_id: UUID,
        kind: ArtifactKind,
        timestamp: datetime,
    ) -> ArtifactVersion:
        artifact = self.session.scalar(
            select(Artifact).where(
                Artifact.task_id == task_id,
                Artifact.kind == kind,
            )
        )
        if artifact is None:
            artifact = Artifact(task_id=task_id, kind=kind, created_at=timestamp)
            self.session.add(artifact)
            self.session.flush()
        version_number = self.session.scalar(
            select(func.coalesce(func.max(ArtifactVersion.version), 0)).where(
                ArtifactVersion.artifact_id == artifact.id
            )
        )
        self.session.execute(
            update(NodeRunOutput)
            .where(
                NodeRunOutput.node_run_id == node_run_id,
                NodeRunOutput.output_role == kind.value,
                NodeRunOutput.is_current.is_(True),
            )
            .values(is_current=False)
        )
        version = ArtifactVersion(
            artifact_id=artifact.id,
            version=int(version_number or 0) + 1,
            content_hash=archived.content_hash,
            relative_storage_path=archived.relative_path,
            original_filename=archived.original_filename,
            media_type=_media_type(archived.original_filename),
            size_bytes=archived.size_bytes,
            producer_attempt_id=attempt_id,
            created_at=timestamp,
        )
        self.session.add(version)
        self.session.flush()
        self.session.add(
            NodeRunOutput(
                node_run_id=node_run_id,
                artifact_version_id=version.id,
                output_role=kind.value,
                is_current=True,
                created_at=timestamp,
            )
        )
        return version


def _media_type(filename: str) -> str:
    if filename.endswith(".jsonl"):
        return "application/x-ndjson"
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
