from __future__ import annotations

import pytest

from thesis_ingest.classification import classify_artifact
from thesis_ingest.config import load_rule_bundle


RULES = load_rule_bundle()


@pytest.mark.parametrize(
    ("relative_path", "decision", "expected_role"),
    [
        ("任务书.docx", "ACCEPTED", "PRIMARY_REQUIREMENT"),
        ("src/main.py", "ACCEPTED", "ENGINEERING_SOURCE"),
        ("config/settings.yaml", "ACCEPTED", "ENGINEERING_CONFIG"),
        ("migrations/001_create.sql", "ACCEPTED", "ENGINEERING_CONFIG"),
        ("requirements.txt", "ACCEPTED", "ENGINEERING_CONFIG"),
        ("README.md", "ACCEPTED", "ENGINEERING_CONFIG"),
        ("screenshots/home.png", "ACCEPTED", "SOURCE_IMAGE"),
        ("results/measurements.csv", "ACCEPTED", "SOURCE_TABLE"),
        ("学校模板.docx", "ACCEPTED", "TEMPLATE"),
        ("参考文献线索.txt", "ACCEPTED", "REFERENCE_CANDIDATE"),
        ("论文正文.docx", "ACCEPTED", "PRIMARY_DOCUMENT"),
        ("历史资料/旧论文.docx", "ACCEPTED", "EXISTING_DRAFT"),
        ("vendor/pkg/index.js", "EXCLUDED", "THIRD_PARTY_DEPENDENCY"),
        ("dist/bundle.js", "EXCLUDED", "BUILD_OUTPUT"),
        ("draft.docx.bak", "EXCLUDED", "BACKUP"),
        ("tools/run.exe", "QUARANTINED", "EXECUTABLE"),
    ],
)
def test_artifact_role_rules_are_explainable(
    relative_path: str, decision: str, expected_role: str
) -> None:
    suggestion = classify_artifact(relative_path, decision, RULES)

    assert suggestion.artifact_role == expected_role
    assert suggestion.classification_reasons


def test_official_datasheet_is_reference_not_primary_document() -> None:
    suggestion = classify_artifact(
        "fixed-official-sources/device-datasheet.pdf", "ACCEPTED", RULES
    )

    assert suggestion.artifact_role == "REFERENCE_CANDIDATE"
    assert suggestion.artifact_role != "PRIMARY_DOCUMENT"


def test_extension_only_classification_confidence_is_capped_at_point_seven() -> None:
    suggestion = classify_artifact("src/unlabelled.py", "ACCEPTED", RULES)

    assert suggestion.classification_method == "EXTENSION_RULE"
    assert suggestion.classification_confidence <= 0.7


def test_unknown_text_gets_low_confidence_unknown_role() -> None:
    suggestion = classify_artifact("misc/blob.xyz", "ACCEPTED", RULES)

    assert suggestion.artifact_role == "UNKNOWN"
    assert suggestion.classification_confidence < 0.6


def test_cli_classification_authority_is_never_human_or_verified() -> None:
    suggestion = classify_artifact("论文终稿.docx", "ACCEPTED", RULES)

    assert suggestion.classification_status == "PROPOSED"
    assert suggestion.classification_authority == "AUTOMATED_SUGGESTION"
    assert "HUMAN" not in suggestion.classification_authority
    assert suggestion.artifact_role != "VERIFIED_REFERENCE"
