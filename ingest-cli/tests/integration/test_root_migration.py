from __future__ import annotations

from pathlib import Path

from thesis_ingest.hashing import hash_file
from thesis_ingest.paths import make_source_occurrence_key


def test_root_uri_migration_keeps_source_occurrence_identity(tmp_path: Path) -> None:
    first_root = tmp_path / "disk-a"
    second_root = tmp_path / "disk-b"
    first_root.mkdir()
    second_root.mkdir()
    relative_path = Path("project") / "任务书.txt"
    (first_root / relative_path).parent.mkdir()
    (second_root / relative_path).parent.mkdir()
    payload = "same controlled content".encode()
    (first_root / relative_path).write_bytes(payload)
    (second_root / relative_path).write_bytes(payload)

    first_hash = hash_file(first_root / relative_path).content_hash
    second_hash = hash_file(second_root / relative_path).content_hash
    first_key = make_source_occurrence_key(
        "controlled-sample", "project/任务书.txt", first_hash
    )
    second_key = make_source_occurrence_key(
        "controlled-sample", "project/任务书.txt", second_hash
    )

    assert first_key == second_key
