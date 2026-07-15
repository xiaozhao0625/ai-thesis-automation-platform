from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from thesis_ingest.canonical_json import dumps_bytes
from thesis_ingest.pipeline import run_scan
from thesis_ingest.verification import VerificationError, verify_package
from tests.support import build_small_source, read_jsonl, write_config


def completed_output(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )
    return run_scan(config, scan_id="scan-reference-check").output_path


def rewrite_jsonl_and_rehash(
    output: Path, name: str, records: list[dict[str, object]]
) -> None:
    payload = b"".join(dumps_bytes(record) + b"\n" for record in records)
    (output / name).write_bytes(payload)
    manifest_path = output / "ingest-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    descriptor = next(
        item for item in manifest["output_hashes"] if item["relative_path"] == name
    )
    descriptor["content_hash"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    descriptor["size_bytes"] = len(payload)
    descriptor["record_count"] = len(records)
    manifest_path.write_bytes(dumps_bytes(manifest) + b"\n")


def test_reference_candidate_must_point_to_existing_ingest_record(
    tmp_path: Path,
) -> None:
    output = completed_output(tmp_path)
    references = read_jsonl(output / "reference-candidates.jsonl")
    references[0]["source_ingest_record_id"] = "missing-record"
    rewrite_jsonl_and_rehash(output, "reference-candidates.jsonl", references)

    with pytest.raises(VerificationError, match="RECORD_REFERENCE_MISSING"):
        verify_package(output)


def test_duplicate_group_members_must_all_exist(tmp_path: Path) -> None:
    output = completed_output(tmp_path)
    groups = read_jsonl(output / "duplicate-groups.jsonl")
    groups[0]["member_ingest_record_ids"][0] = "missing-record"
    rewrite_jsonl_and_rehash(output, "duplicate-groups.jsonl", groups)

    with pytest.raises(VerificationError, match="RECORD_REFERENCE_MISSING"):
        verify_package(output)


def test_artifact_issue_reference_must_exist(tmp_path: Path) -> None:
    output = completed_output(tmp_path)
    artifacts = read_jsonl(output / "artifacts.jsonl")
    accepted = next(
        record for record in artifacts if record["ingest_decision"] == "ACCEPTED"
    )
    accepted["issue_refs"] = ["missing-issue"]
    rewrite_jsonl_and_rehash(output, "artifacts.jsonl", artifacts)

    with pytest.raises(VerificationError, match="RECORD_REFERENCE_MISSING"):
        verify_package(output)
