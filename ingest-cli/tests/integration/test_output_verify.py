from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from thesis_ingest.output import (
    OutputError,
    PackageContents,
    publish_package,
)
from thesis_ingest.verification import VerificationError, verify_package


OUTPUT_NAMES = {
    "ingest-manifest.json",
    "source-mounts.json",
    "artifacts.jsonl",
    "excluded-items.jsonl",
    "duplicate-groups.jsonl",
    "primary-candidates.jsonl",
    "reference-candidates.jsonl",
    "sensitive-items.jsonl",
    "ingest-issues.jsonl",
    "summary.json",
}


def empty_contents() -> PackageContents:
    source_mount = {
        "schema_version": "0.1",
        "record_type": "SOURCE_MOUNT",
        "source_mount_id": "controlled-sample",
        "name": "Controlled sample",
        "mount_type": "LOCAL_DIRECTORY",
        "root_uri": "file:///controlled/sample",
        "binding_revision": 1,
        "read_only": True,
        "status": "ACTIVE",
        "case_policy": "CASE_SENSITIVE",
        "unicode_normalization": "NFC",
        "path_normalization_version": "path-nfc-posix-v1",
        "last_scan_id": None,
        "last_scan_at": None,
        "root_fingerprint": None,
        "access_policy": {
            "preview_policy": "RESTRICTED",
            "external_model_policy": "DENY_EXTERNAL_MODEL",
            "export_policy": "REDACT_SOURCE_URI",
            "audit_required": True,
        },
    }
    counts = {
        "total_files": 0,
        "accepted_files": 0,
        "excluded_files": 0,
        "quarantined_files": 0,
        "duplicate_files": 0,
        "needs_review_files": 0,
        "failed_files": 0,
        "pruned_directories": 0,
        "issue_count": 0,
    }
    summary = {
        "summary_version": "0.1",
        "scan_id": "scan-empty-001",
        "source_mount_id": "controlled-sample",
        "status": "COMPLETED",
        **counts,
        "by_artifact_role": {},
        "by_media_type": {},
        "by_data_classification": {},
        "by_issue_severity": {},
        "duration_ms": 1,
        "resumed_from_checkpoint": False,
        "checkpoint_count": 0,
        "unread_files": 0,
        "unhashed_files": 0,
        "duplicate_group_count": 0,
        "primary_candidate_count": 0,
        "reference_candidate_count": 0,
        "sensitive_item_count": 0,
    }
    manifest = {
        "manifest_version": "0.1",
        "record_type": "INGEST_MANIFEST",
        "scan_id": "scan-empty-001",
        "status": "COMPLETED",
        "source_mount_id": "controlled-sample",
        "binding_revision": 1,
        "config_version": "0.1",
        "config_hash": "sha256:" + "1" * 64,
        "path_normalization_version": "path-nfc-posix-v1",
        "rule_set_version": "ingest-rules-0.1",
        "scanner_version": "thesis-ingest-0.1",
        "root_fingerprint": {
            "algorithm": "SHA-256",
            "canonicalization_version": "RFC8785-JCS-v1",
            "scope": "RECORDED_ITEMS",
            "strength": "STRONG",
            "record_count": 0,
            "hashed_record_count": 0,
            "value": "sha256:" + hashlib.sha256(b"[]").hexdigest(),
        },
        "started_at": "2026-07-15T08:00:00Z",
        "finished_at": "2026-07-15T08:00:01Z",
        **counts,
        "resume_info": {
            "resumed_from_checkpoint": False,
            "checkpoint_id": None,
            "checkpoint_count": 0,
        },
    }
    return PackageContents(
        manifest=manifest,
        source_mounts={
            "schema_version": "0.1",
            "record_type": "SOURCE_MOUNT_COLLECTION",
            "source_mounts": [source_mount],
        },
        artifacts=[],
        excluded_items=[],
        duplicate_groups=[],
        primary_candidates=[],
        reference_candidates=[],
        sensitive_items=[],
        ingest_issues=[],
        summary=summary,
    )


def test_publish_creates_exact_complete_output_tree(tmp_path: Path) -> None:
    output = tmp_path / "ingest-output"

    published = publish_package(output, empty_contents())

    assert published == output
    assert {path.name for path in output.iterdir()} == OUTPUT_NAMES
    assert not any(path.name.endswith(".tmp") for path in output.iterdir())


def test_manifest_hashes_match_every_non_manifest_output(tmp_path: Path) -> None:
    output = publish_package(tmp_path / "ingest-output", empty_contents())
    manifest = json.loads((output / "ingest-manifest.json").read_text("utf-8"))

    assert len(manifest["output_hashes"]) == 9
    for descriptor in manifest["output_hashes"]:
        payload = (output / descriptor["relative_path"]).read_bytes()
        assert descriptor["content_hash"] == (
            "sha256:" + hashlib.sha256(payload).hexdigest()
        )
        assert descriptor["size_bytes"] == len(payload)


def test_empty_jsonl_files_are_zero_length_without_truncated_records(
    tmp_path: Path,
) -> None:
    output = publish_package(tmp_path / "ingest-output", empty_contents())

    for name in OUTPUT_NAMES:
        if name.endswith(".jsonl"):
            assert (output / name).read_bytes() == b""


def test_publish_refuses_nonempty_target_directory(tmp_path: Path) -> None:
    output = tmp_path / "ingest-output"
    output.mkdir()
    (output / "existing.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(OutputError, match="OUTPUT_TARGET_NOT_EMPTY"):
        publish_package(output, empty_contents())

    assert (output / "existing.txt").read_text("utf-8") == "do not overwrite"


def test_validation_failure_never_exposes_final_output(tmp_path: Path) -> None:
    contents = empty_contents()
    contents.summary["status"] = "PARTIAL"
    output = tmp_path / "ingest-output"

    with pytest.raises(OutputError):
        publish_package(output, contents)

    assert not output.exists()


def test_fresh_complete_package_verifies_offline(tmp_path: Path) -> None:
    output = publish_package(tmp_path / "ingest-output", empty_contents())

    report = verify_package(output)

    assert report.status == "COMPLETED"
    assert report.file_count == 10
    assert report.record_counts["artifacts.jsonl"] == 0


def test_tampered_output_hash_fails_verification(tmp_path: Path) -> None:
    output = publish_package(tmp_path / "ingest-output", empty_contents())
    (output / "summary.json").write_bytes(b"{}\n")

    with pytest.raises(VerificationError, match="OUTPUT_HASH_MISMATCH"):
        verify_package(output)


def test_partial_manifest_cannot_masquerade_as_completed(tmp_path: Path) -> None:
    output = publish_package(tmp_path / "ingest-output", empty_contents())
    manifest_path = output / "ingest-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["status"] = "PARTIAL"
    manifest["root_fingerprint"] = None
    manifest["output_hashes"] = []
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(VerificationError, match="MANIFEST_NOT_COMPLETED"):
        verify_package(output)


def test_duplicate_json_key_is_rejected_even_if_manifest_hash_is_updated(
    tmp_path: Path,
) -> None:
    output = publish_package(tmp_path / "ingest-output", empty_contents())
    summary_path = output / "summary.json"
    payload = b'{"same":1,"same":2}\n'
    summary_path.write_bytes(payload)
    manifest_path = output / "ingest-manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    descriptor = next(
        item
        for item in manifest["output_hashes"]
        if item["relative_path"] == "summary.json"
    )
    descriptor["content_hash"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    descriptor["size_bytes"] = len(payload)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(VerificationError, match="STRICT_JSON_INVALID"):
        verify_package(output)
