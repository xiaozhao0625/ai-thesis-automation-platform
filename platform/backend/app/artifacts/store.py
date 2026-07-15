from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID


class ArtifactHashMismatch(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArchivedFile:
    relative_path: str
    content_hash: str
    size_bytes: int
    original_filename: str


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def archive(
        self,
        source: Path,
        *,
        task_id: UUID,
        node_run_id: UUID,
        attempt_id: UUID,
    ) -> ArchivedFile:
        source = source.resolve(strict=True)
        before = source.stat()
        digest = _sha256_file(source)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ArtifactHashMismatch("source changed while archiving")

        relative = PurePosixPath(
            "tasks",
            str(task_id),
            "nodes",
            str(node_run_id),
            "attempts",
            str(attempt_id),
            digest,
            source.name,
        )
        destination = self.resolve(str(relative))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            staging = self.root / ".staging" / f"{uuid.uuid4().hex}.tmp"
            staging.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, staging)
            if _sha256_file(staging) != digest:
                staging.unlink(missing_ok=True)
                raise ArtifactHashMismatch("staged artifact hash differs from source")
            os.replace(staging, destination)
        elif _sha256_file(destination) != digest:
            raise ArtifactHashMismatch("existing content-addressed artifact is corrupt")

        return ArchivedFile(
            relative_path=str(relative),
            content_hash=f"sha256:{digest}",
            size_bytes=after.st_size,
            original_filename=source.name,
        )

    def resolve(self, relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ValueError("artifact path escapes artifact store")
        resolved = (self.root / relative).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("artifact path escapes artifact store")
        return resolved

    def read_verified(self, relative_path: str, expected_hash: str) -> bytes:
        path = self.resolve(relative_path)
        payload = path.read_bytes()
        digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if digest != expected_hash:
            raise ArtifactHashMismatch("artifact content hash mismatch")
        return payload


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
