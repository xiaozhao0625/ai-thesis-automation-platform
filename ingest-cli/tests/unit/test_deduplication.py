from __future__ import annotations

from thesis_ingest.contracts import validate_instance
from thesis_ingest.deduplication import DedupRecord, deduplicate


HASH = "sha256:" + "a" * 64


def record(
    record_id: str,
    path_key: str,
    *,
    decision: str = "ACCEPTED",
    parser_eligible: bool = True,
    artifact_role: str = "ENGINEERING_SOURCE",
) -> DedupRecord:
    return DedupRecord(
        ingest_record_id=record_id,
        content_hash=HASH,
        path_key=path_key,
        pre_dedup_decision=decision,
        pre_dedup_parser_eligible=parser_eligible,
        artifact_role=artifact_role,
    )


def test_same_hash_different_paths_form_one_duplicate_group() -> None:
    result = deduplicate(
        [
            record("record-a", "src/a.py"),
            record("record-b", "copy/a.py"),
        ],
        scan_id="scan-001",
    )

    assert len(result.groups) == 1
    assert set(result.groups[0].member_ingest_record_ids) == {
        "record-a",
        "record-b",
    }
    assert {item.path_key for item in result.records} == {"src/a.py", "copy/a.py"}


def test_canonical_is_selected_only_from_accepted_parser_eligible_members() -> None:
    result = deduplicate(
        [
            record(
                "excluded-first",
                "a/vendor.py",
                decision="EXCLUDED",
                parser_eligible=False,
                artifact_role="THIRD_PARTY_DEPENDENCY",
            ),
            record("accepted", "z/main.py"),
        ],
        scan_id="scan-001",
    )

    group = result.groups[0]
    assert group.canonical_ingest_record_id == "accepted"
    assert group.canonical_selection_status == "SELECTED"
    by_id = {item.ingest_record_id: item for item in result.records}
    assert by_id["accepted"].ingest_decision == "ACCEPTED"
    assert by_id["excluded-first"].ingest_decision == "EXCLUDED"


def test_noncanonical_accepted_member_becomes_duplicate() -> None:
    result = deduplicate(
        [record("z-record", "z.py"), record("a-record", "a.py")],
        scan_id="scan-001",
    )

    by_id = {item.ingest_record_id: item for item in result.records}
    assert by_id["a-record"].ingest_decision == "ACCEPTED"
    assert by_id["a-record"].parser_eligible is True
    assert by_id["z-record"].ingest_decision == "DUPLICATE"
    assert by_id["z-record"].parser_eligible is False


def test_nonbackup_candidate_wins_before_path_tie_break() -> None:
    result = deduplicate(
        [
            record("backup", "a.py", artifact_role="BACKUP"),
            record("source", "z.py", artifact_role="ENGINEERING_SOURCE"),
        ],
        scan_id="scan-001",
    )

    assert result.groups[0].canonical_ingest_record_id == "source"


def test_group_without_eligible_member_has_no_fake_canonical() -> None:
    result = deduplicate(
        [
            record("excluded", "a.py", decision="EXCLUDED", parser_eligible=False),
            record(
                "quarantined",
                "b.py",
                decision="QUARANTINED",
                parser_eligible=False,
            ),
        ],
        scan_id="scan-001",
    )

    group = result.groups[0]
    assert group.canonical_selection_status == "NO_ELIGIBLE_CANONICAL"
    assert group.canonical_ingest_record_id is None
    assert all(item.ingest_decision != "DUPLICATE" for item in result.records)


def test_duplicate_group_serialization_matches_frozen_schema() -> None:
    result = deduplicate(
        [record("record-a", "a.py"), record("record-b", "b.py")],
        scan_id="scan-001",
    )

    validate_instance(
        result.groups[0].as_dict(),
        "artifact-ingest-record.schema.json",
        schema_fragment="#/$defs/duplicate_group",
    )
