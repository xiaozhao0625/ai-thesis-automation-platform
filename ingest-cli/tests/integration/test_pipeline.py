from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from thesis_ingest.pipeline import (
    PipelineError,
    ScanInterrupted,
    run_scan,
)
from thesis_ingest.verification import verify_package
from tests.support import build_small_source, read_jsonl, write_config


def test_small_controlled_sample_completes_the_full_ingest_loop(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    original = build_small_source(source)
    original_hashes = {
        path: hashlib.sha256(payload).hexdigest() for path, payload in original.items()
    }
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )

    result = run_scan(config, scan_id="scan-integration-001")
    report = verify_package(result.output_path)

    assert result.status == "COMPLETED"
    assert report.status == "COMPLETED"
    manifest = json.loads(
        (result.output_path / "ingest-manifest.json").read_text("utf-8")
    )
    assert manifest["total_files"] == len(original)
    assert manifest["total_files"] == sum(
        manifest[name]
        for name in (
            "accepted_files",
            "excluded_files",
            "quarantined_files",
            "duplicate_files",
            "needs_review_files",
        )
    )

    records = read_jsonl(result.output_path / "artifacts.jsonl") + read_jsonl(
        result.output_path / "excluded-items.jsonl"
    )
    by_path = {record["relative_path"]: record for record in records}
    assert by_path["project/.venv/Lib/site.py"]["ingest_decision"] == "EXCLUDED"
    assert by_path["project/.venv/Lib/site.py"]["hash_status"] == "SKIPPED_BY_POLICY"
    assert by_path["project/vendor/pkg/data.pdf"]["parser_eligible"] is False
    assert by_path["project/tools/run.exe"]["ingest_decision"] == "QUARANTINED"
    assert by_path["project/config/secrets.json"]["data_classification"] == "RESTRICTED"
    assert all(str(source) not in repr(record) for record in records)

    groups = read_jsonl(result.output_path / "duplicate-groups.jsonl")
    assert len(groups) == 1
    canonical_id = groups[0]["canonical_ingest_record_id"]
    canonical = next(record for record in records if record["ingest_record_id"] == canonical_id)
    assert canonical["ingest_decision"] == "ACCEPTED"
    assert canonical["parser_eligible"] is True

    candidates = read_jsonl(result.output_path / "primary-candidates.jsonl")
    document_candidate = next(
        item for item in candidates if item["selection_type"] == "PRIMARY_DOCUMENT"
    )
    assert document_candidate["recommendation_status"] == "RECOMMENDED"
    assert document_candidate["requires_human_confirmation"] is True

    references = read_jsonl(result.output_path / "reference-candidates.jsonl")
    assert references
    assert {item["verification_status"] for item in references} == {"UNVERIFIED"}
    assert all("evidence_chunk_id" not in item for item in references)

    sensitive = read_jsonl(result.output_path / "sensitive-items.jsonl")
    assert any("FACE_IMAGE" in item["content_categories"] for item in sensitive)
    assert any("SOURCE_CODE" in item["content_categories"] for item in sensitive)

    for relative_path, expected_hash in original_hashes.items():
        assert hashlib.sha256((source / Path(*relative_path.split("/"))).read_bytes()).hexdigest() == expected_hash


@pytest.mark.recovery
def test_resume_after_interruption_has_no_lost_or_duplicate_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    original = build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )

    with pytest.raises(ScanInterrupted) as interrupted:
        run_scan(
            config,
            scan_id="scan-resume-001",
            fail_after_records=5,
        )
    assert interrupted.value.exit_code == 4
    assert not (tmp_path / "ingest-output").exists()

    resumed = run_scan(config, scan_id="scan-resume-001")
    records = read_jsonl(resumed.output_path / "artifacts.jsonl") + read_jsonl(
        resumed.output_path / "excluded-items.jsonl"
    )

    assert resumed.resumed_from_checkpoint is True
    assert len(records) == len(original)
    assert len({record["ingest_record_id"] for record in records}) == len(records)


@pytest.mark.recovery
def test_resume_rejects_source_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )
    with pytest.raises(ScanInterrupted):
        run_scan(config, scan_id="scan-mutation-001", fail_after_records=3)
    checkpoint_path = (
        tmp_path
        / ".ingest-output.staging"
        / "scan-mutation-001"
        / "checkpoint.json"
    )
    checkpoint = json.loads(checkpoint_path.read_text("utf-8"))
    first_path = checkpoint["source_snapshots"][0]["relative_path"]
    (source / Path(*first_path.split("/"))).write_bytes(b"mutated after checkpoint")

    with pytest.raises(PipelineError, match="SOURCE_MUTATED_DURING_SCAN"):
        run_scan(config, scan_id="scan-mutation-001")


@pytest.mark.recovery
def test_resume_rejects_new_file_inserted_before_checkpoint_cursor(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    build_small_source(source)
    config = write_config(
        tmp_path / "ingest-config.json",
        source_root=source,
        output_directory="ingest-output/",
    )
    with pytest.raises(ScanInterrupted):
        run_scan(config, scan_id="scan-inserted-file-001", fail_after_records=3)
    (source / "000-new-before-cursor.txt").write_text("new", encoding="utf-8")

    with pytest.raises(PipelineError, match="SOURCE_MUTATED_DURING_SCAN"):
        run_scan(config, scan_id="scan-inserted-file-001")


def test_root_rebinding_keeps_occurrence_keys_in_full_outputs(tmp_path: Path) -> None:
    first_source = tmp_path / "source-a"
    second_source = tmp_path / "source-b"
    first_source.mkdir()
    build_small_source(first_source)
    shutil.copytree(first_source, second_source)
    first_config = write_config(
        tmp_path / "config-a.json",
        source_root=first_source,
        output_directory="output-a/",
    )
    second_config = write_config(
        tmp_path / "config-b.json",
        source_root=second_source,
        output_directory="output-b/",
    )

    first = run_scan(first_config, scan_id="scan-root-a")
    second = run_scan(second_config, scan_id="scan-root-b")
    first_records = read_jsonl(first.output_path / "artifacts.jsonl") + read_jsonl(
        first.output_path / "excluded-items.jsonl"
    )
    second_records = read_jsonl(second.output_path / "artifacts.jsonl") + read_jsonl(
        second.output_path / "excluded-items.jsonl"
    )
    first_keys = {
        record["relative_path"]: record.get("source_occurrence_key")
        for record in first_records
    }
    second_keys = {
        record["relative_path"]: record.get("source_occurrence_key")
        for record in second_records
    }

    assert first_keys == second_keys
