from __future__ import annotations

import os
from pathlib import Path

import pytest

from thesis_ingest.checkpoint import (
    CheckpointError,
    CheckpointState,
    SourceSnapshot,
    load_checkpoint,
    save_checkpoint,
)
from thesis_ingest.hashing import hash_file


pytestmark = pytest.mark.recovery


def state(source: Path) -> CheckpointState:
    hashed = hash_file(source)
    metadata = source.stat()
    return CheckpointState(
        checkpoint_id="checkpoint-001",
        scan_id="scan-001",
        config_hash="sha256:" + "1" * 64,
        rule_set_version="ingest-rules-0.1",
        path_normalization_version="path-nfc-posix-v1",
        next_index=1,
        source_snapshots=(
            SourceSnapshot(
                relative_path="source.txt",
                size_bytes=metadata.st_size,
                modified_time_ns=metadata.st_mtime_ns,
                content_hash=hashed.content_hash,
            ),
        ),
        payload={"records": [{"id": "record-001"}]},
    )


def load(path: Path, source_root: Path) -> CheckpointState:
    return load_checkpoint(
        path,
        expected_scan_id="scan-001",
        expected_config_hash="sha256:" + "1" * 64,
        expected_rule_set_version="ingest-rules-0.1",
        expected_path_normalization_version="path-nfc-posix-v1",
        source_root=source_root,
    )


def test_checkpoint_round_trip_preserves_cursor_payload_and_sources(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("stable", encoding="utf-8")
    checkpoint = tmp_path / "checkpoint.json"

    save_checkpoint(checkpoint, state(source))
    restored = load(checkpoint, tmp_path)

    assert restored.next_index == 1
    assert restored.payload == {"records": [{"id": "record-001"}]}
    assert restored.source_snapshots[0].content_hash.startswith("sha256:")


def test_checkpoint_write_is_atomic_and_leaves_no_temp_file(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("stable", encoding="utf-8")
    checkpoint = tmp_path / "checkpoint.json"

    save_checkpoint(checkpoint, state(source))

    assert checkpoint.is_file()
    assert not checkpoint.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("expected_scan_id", "scan-other", "CHECKPOINT_SCAN_MISMATCH"),
        (
            "expected_config_hash",
            "sha256:" + "2" * 64,
            "CHECKPOINT_CONFIG_MISMATCH",
        ),
        (
            "expected_rule_set_version",
            "ingest-rules-9.9",
            "CHECKPOINT_RULE_SET_MISMATCH",
        ),
        (
            "expected_path_normalization_version",
            "path-other-v1",
            "CHECKPOINT_PATH_VERSION_MISMATCH",
        ),
    ],
)
def test_checkpoint_context_mismatch_is_rejected(
    tmp_path: Path, field: str, value: str, error: str
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("stable", encoding="utf-8")
    checkpoint = tmp_path / "checkpoint.json"
    save_checkpoint(checkpoint, state(source))
    arguments = {
        "expected_scan_id": "scan-001",
        "expected_config_hash": "sha256:" + "1" * 64,
        "expected_rule_set_version": "ingest-rules-0.1",
        "expected_path_normalization_version": "path-nfc-posix-v1",
        "source_root": tmp_path,
    }
    arguments[field] = value

    with pytest.raises(CheckpointError, match=error):
        load_checkpoint(checkpoint, **arguments)


def test_source_size_or_mtime_change_rejects_resume(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("stable", encoding="utf-8")
    checkpoint = tmp_path / "checkpoint.json"
    save_checkpoint(checkpoint, state(source))
    source.write_text("changed length", encoding="utf-8")

    with pytest.raises(CheckpointError, match="CHECKPOINT_SOURCE_CHANGED"):
        load(checkpoint, tmp_path)


def test_same_size_same_mtime_content_change_is_detected_by_hash(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"first!")
    checkpoint = tmp_path / "checkpoint.json"
    saved = state(source)
    save_checkpoint(checkpoint, saved)
    source.write_bytes(b"second")
    os.utime(
        source,
        ns=(
            source.stat().st_atime_ns,
            saved.source_snapshots[0].modified_time_ns,
        ),
    )

    with pytest.raises(CheckpointError, match="CHECKPOINT_SOURCE_HASH_MISMATCH"):
        load(checkpoint, tmp_path)


def test_corrupt_checkpoint_is_rejected(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"same":1,"same":2}', encoding="utf-8")

    with pytest.raises(CheckpointError, match="CHECKPOINT_INVALID"):
        load(checkpoint, tmp_path)
