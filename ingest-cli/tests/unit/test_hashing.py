from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from thesis_ingest.hashing import (
    FileChangedDuringHash,
    HashingError,
    hash_file,
)


def test_hash_file_streams_raw_bytes_into_prefixed_sha256(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 64
    source = tmp_path / "payload.bin"
    source.write_bytes(payload)

    result = hash_file(source, chunk_size=257)

    assert result.content_hash == "sha256:" + hashlib.sha256(payload).hexdigest()
    assert result.size_bytes == len(payload)
    assert result.bytes_read == len(payload)
    assert result.modified_time_ns == source.stat().st_mtime_ns


def test_hash_file_rechecks_size_and_mtime_after_streaming(tmp_path: Path) -> None:
    source = tmp_path / "changing.bin"
    source.write_bytes(b"a" * 64)
    changed = False

    def mutate_after_first_chunk(bytes_read: int) -> None:
        nonlocal changed
        if not changed and bytes_read:
            changed = True
            with source.open("ab") as handle:
                handle.write(b"changed")

    with pytest.raises(
        FileChangedDuringHash, match="FILE_CHANGED_DURING_SCAN"
    ):
        hash_file(source, chunk_size=8, progress=mutate_after_first_chunk)


def test_changed_file_error_never_exposes_partial_content_hash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "changing.bin"
    source.write_bytes(b"first")

    def mutate(_: int) -> None:
        source.write_bytes(b"second version")

    with pytest.raises(FileChangedDuringHash) as captured:
        hash_file(source, chunk_size=1024, progress=mutate)

    assert captured.value.content_hash is None


def test_hash_read_failure_has_stable_error_code(tmp_path: Path) -> None:
    missing = tmp_path / "missing.bin"

    with pytest.raises(HashingError, match="HASH_READ_FAILED") as captured:
        hash_file(missing)

    assert captured.value.code == "HASH_READ_FAILED"


def test_empty_file_has_the_standard_sha256_identity(tmp_path: Path) -> None:
    source = tmp_path / "empty.txt"
    source.write_bytes(b"")

    result = hash_file(source)

    assert result.content_hash == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )
