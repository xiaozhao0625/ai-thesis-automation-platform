from __future__ import annotations

from thesis_ingest.candidates import (
    CandidateArtifact,
    EngineeringRoot,
    evaluate_engineering_roots,
    evaluate_primary_documents,
)
from thesis_ingest.config import load_rule_bundle
from thesis_ingest.contracts import validate_instance


RULES = load_rule_bundle()
HASH = "sha256:" + "b" * 64
CREATED_AT = "2026-07-15T08:00:00Z"


def artifact(
    record_id: str,
    path: str,
    *,
    role: str = "EXISTING_DRAFT",
    modified_at: str = "2026-07-14T08:00:00Z",
    word_count: int | None = 1000,
    decision: str = "ACCEPTED",
    parser_eligible: bool = True,
) -> CandidateArtifact:
    return CandidateArtifact(
        ingest_record_id=record_id,
        relative_path=path,
        content_hash=HASH,
        modified_at=modified_at,
        artifact_role=role,
        ingest_decision=decision,
        parser_eligible=parser_eligible,
        word_count=word_count,
        page_count=None,
        in_project_scope=True,
    )


def test_document_score_uses_the_frozen_feature_weights() -> None:
    selection = evaluate_primary_documents(
        [
            artifact(
                "doc-a",
                "论文终稿.docx",
                role="PRIMARY_DOCUMENT",
            )
        ],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    evaluation = selection.record["candidate_evaluations"][0]
    assert evaluation["candidate_score"] == 0.95
    assert evaluation["feature_values"] == {
        "ROLE_WEIGHT": 0.3,
        "CURRENT_NAME_WEIGHT": 0.25,
        "FORMAT_WEIGHT": 0.15,
        "WORD_COUNT_WEIGHT": 0.1,
        "NEWEST_MTIME_WEIGHT": 0.05,
        "SCOPE_WEIGHT": 0.1,
    }


def test_unique_recommendation_requires_threshold_and_gap_over_point_zero_five() -> None:
    selection = evaluate_primary_documents(
        [
            artifact("best", "论文终稿.docx", role="PRIMARY_DOCUMENT"),
            artifact("other", "论文草稿.pdf", word_count=100),
        ],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert selection.record["recommendation_status"] == "RECOMMENDED"
    assert selection.record["recommended_ingest_record_id"] == "best"


def test_exact_point_zero_five_gap_is_tied_review_not_forced_choice() -> None:
    selection = evaluate_primary_documents(
        [
            artifact(
                "newer",
                "论文终稿.docx",
                modified_at="2026-07-15T08:00:00Z",
            ),
            artifact(
                "older",
                "论文终稿2.docx",
                modified_at="2026-07-14T08:00:00Z",
            ),
        ],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert selection.record["recommendation_status"] == "TIED_REVIEW"
    assert set(selection.record["tied_ingest_record_ids"]) == {"newer", "older"}
    assert "recommended_ingest_record_id" not in selection.record


def test_low_top_score_returns_no_recommendation() -> None:
    selection = evaluate_primary_documents(
        [artifact("weak", "notes.pdf", role="EXISTING_DRAFT", word_count=10)],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert selection.record["recommendation_status"] == "NO_RECOMMENDATION"
    assert "recommended_ingest_record_id" not in selection.record
    assert selection.issue_records


def test_no_observable_candidate_emits_issue_without_fake_candidate_record() -> None:
    selection = evaluate_primary_documents(
        [],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert selection.record is None
    assert selection.issue_records[0]["code"] == "PROJECT_SCOPE_UNRESOLVED"


def test_backup_dependency_and_historical_paper_are_not_candidates() -> None:
    selection = evaluate_primary_documents(
        [
            artifact("backup", "论文终稿.docx.bak", role="BACKUP"),
            artifact(
                "dependency",
                "vendor/论文终稿.pdf",
                role="THIRD_PARTY_DEPENDENCY",
                decision="EXCLUDED",
                parser_eligible=False,
            ),
            artifact("old", "历史资料/旧论文终稿.docx"),
        ],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert selection.record is None
    assert selection.issue_records[0]["code"] == "PROJECT_SCOPE_UNRESOLVED"


def test_engineering_source_is_not_a_document_candidate() -> None:
    selection = evaluate_primary_documents(
        [artifact("source", "src/main.py", role="ENGINEERING_SOURCE")],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert selection.record is None


def test_candidate_record_matches_frozen_schema_fragment() -> None:
    selection = evaluate_primary_documents(
        [artifact("doc-a", "论文终稿.docx", role="PRIMARY_DOCUMENT")],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    validate_instance(
        selection.record,
        "artifact-ingest-record.schema.json",
        schema_fragment="#/$defs/primary_artifact_candidate",
    )


def test_engineering_root_score_uses_all_frozen_signals() -> None:
    root = EngineeringRoot(
        root_path="project",
        representative_ingest_record_id="anchor",
        representative_content_hash=HASH,
        representative_modified_at="2026-07-15T08:00:00Z",
        file_names={
            "pyproject.toml",
            "requirements.txt",
            "README.md",
            "src/a.py",
            "src/b.py",
            "src/c.py",
            "tests/test_a.py",
            "migrations/001.sql",
            "manage.py",
        },
    )

    selection = evaluate_engineering_roots(
        [root],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    evaluation = selection.record["candidate_evaluations"][0]
    assert evaluation["candidate_score"] == 1.0
    assert selection.record["recommendation_status"] == "RECOMMENDED"


def test_engineering_root_supports_tied_and_no_recommendation_states() -> None:
    tied_roots = [
        EngineeringRoot(
            root_path=name,
            representative_ingest_record_id=f"anchor-{name}",
            representative_content_hash=HASH,
            representative_modified_at=CREATED_AT,
            file_names={
                "pyproject.toml",
                "requirements.txt",
                "src/a.py",
                "src/b.py",
                "src/c.py",
                "README.md",
            },
        )
        for name in ("one", "two")
    ]
    tied = evaluate_engineering_roots(
        tied_roots,
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )
    weak = evaluate_engineering_roots(
        [
            EngineeringRoot(
                root_path="weak",
                representative_ingest_record_id="anchor-weak",
                representative_content_hash=HASH,
                representative_modified_at=CREATED_AT,
                file_names={"README.md"},
            )
        ],
        scan_id="scan-001",
        scope_id="scope-001",
        created_at=CREATED_AT,
        rules=RULES,
    )

    assert tied.record["recommendation_status"] == "TIED_REVIEW"
    assert weak.record["recommendation_status"] == "NO_RECOMMENDATION"
