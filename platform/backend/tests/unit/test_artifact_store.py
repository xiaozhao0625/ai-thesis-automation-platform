from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from app.artifacts.store import ArtifactHashMismatch, LocalArtifactStore


def test_archive_is_content_addressed_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "ingest-manifest.json"
    payload = b'{"status":"COMPLETED"}\n'
    source.write_bytes(payload)
    before = source.stat()
    store = LocalArtifactStore(tmp_path / "store")

    archived = store.archive(
        source,
        task_id=uuid4(),
        node_run_id=uuid4(),
        attempt_id=uuid4(),
    )

    assert archived.content_hash == f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert archived.size_bytes == len(payload)
    assert not Path(archived.relative_path).is_absolute()
    assert store.read_verified(archived.relative_path, archived.content_hash) == payload
    after = source.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


def test_tampered_archive_fails_hash_verification(tmp_path: Path) -> None:
    source = tmp_path / "summary.json"
    source.write_bytes(b"{}\n")
    store = LocalArtifactStore(tmp_path / "store")
    archived = store.archive(
        source,
        task_id=uuid4(),
        node_run_id=uuid4(),
        attempt_id=uuid4(),
    )
    (store.root / archived.relative_path).write_bytes(b"tampered")

    with pytest.raises(ArtifactHashMismatch):
        store.read_verified(archived.relative_path, archived.content_hash)


def test_path_traversal_cannot_escape_artifact_root(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "store")

    with pytest.raises(ValueError, match="escapes artifact store"):
        store.resolve("../secret.txt")
