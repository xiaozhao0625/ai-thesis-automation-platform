from __future__ import annotations

from thesis_ingest.contracts import validate_instance
from thesis_ingest.references import extract_reference_candidates


def extract(text: str) -> list[dict[str, object]]:
    return extract_reference_candidates(
        text,
        source_ingest_record_id="source-record",
        scan_id="scan-001",
        created_at="2026-07-15T08:00:00Z",
    )


def test_each_nonempty_reference_line_becomes_an_unverified_candidate() -> None:
    candidates = extract(
        "Smith J. Useful Title. 2024.\n\n张三. 中文题目. 2023.\n"
    )

    assert len(candidates) == 2
    assert all(item["record_type"] == "REFERENCE_CANDIDATE" for item in candidates)
    assert all(item["verification_status"] == "UNVERIFIED" for item in candidates)
    assert all(item["relevance_status"] == "UNKNOWN" for item in candidates)
    assert all(item["license_status"] == "UNKNOWN" for item in candidates)


def test_common_year_doi_and_url_clues_are_extracted_without_verification() -> None:
    candidate = extract(
        "Smith J. Useful Title. 2024. https://example.org/paper doi:10.1234/example.1"
    )[0]

    assert candidate["year_candidate"] == 2024
    assert candidate["doi_candidate"] == "10.1234/example.1"
    assert candidate["url_candidate"] == "https://example.org/paper"
    assert candidate["title_candidate"] == "Useful Title"
    assert candidate["author_candidates"] == ["Smith J"]


def test_source_locator_preserves_the_original_line_number() -> None:
    candidate = extract("heading-like clue\n\nAuthor. Title. 2022.")[1]

    assert candidate["source_locator"] == {
        "locator_type": "LINE_RANGE",
        "line_start": 3,
        "line_end": 3,
    }


def test_unparsed_bare_clue_keeps_an_issue_reference() -> None:
    candidate = extract("unstructured clue only")[0]

    assert candidate["issue_refs"]
    assert "title_candidate" not in candidate
    assert "author_candidates" not in candidate


def test_repeated_line_is_linked_as_duplicate_candidate_not_deleted() -> None:
    candidates = extract("Author. Title. 2024.\nAuthor. Title. 2024.")

    assert len(candidates) == 2
    assert candidates[1]["duplicate_of"] == candidates[0]["reference_candidate_id"]


def test_reference_candidate_never_contains_evidence_or_verified_fields() -> None:
    candidate = extract("Author. Title. 2024.")[0]

    forbidden = {
        "evidence_chunk_id",
        "claim_id",
        "verified_reference_id",
        "full_text_hash",
    }
    assert forbidden.isdisjoint(candidate)
    assert candidate["verification_status"] != "VERIFIED"


def test_reference_candidate_matches_frozen_schema_fragment() -> None:
    candidate = extract("Author. Title. 2024. doi:10.1234/example")[0]

    validate_instance(
        candidate,
        "artifact-ingest-record.schema.json",
        schema_fragment="#/$defs/reference_candidate",
    )
