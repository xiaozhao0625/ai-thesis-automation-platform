from __future__ import annotations

import pytest

from thesis_ingest.sensitivity import classify_sensitivity


def test_official_snapshot_is_public_when_no_sensitive_signal_exists() -> None:
    result = classify_sensitivity(
        "fixed-official-sources/standard.pdf", "REFERENCE_CANDIDATE"
    )

    assert result.data_classification == "PUBLIC"
    assert result.access_recommendation == "STANDARD"
    assert result.model_usage_restriction == "ALLOW"


def test_source_code_is_internal_and_marked_as_source_code() -> None:
    result = classify_sensitivity("src/main.py", "ENGINEERING_SOURCE")

    assert result.data_classification == "INTERNAL"
    assert result.content_categories == ("SOURCE_CODE",)
    assert result.model_usage_restriction == "LOCAL_MODEL_ONLY"


def test_face_image_name_signal_is_sensitive_without_claiming_ml_detection() -> None:
    result = classify_sensitivity("screenshots/student-face.jpg", "SOURCE_IMAGE")

    assert result.data_classification == "SENSITIVE"
    assert "FACE_IMAGE" in result.content_categories
    assert any(
        reason["rule_id"] == "face-image-name-v1"
        for reason in result.sensitivity_reasons
    )
    assert all(
        "recognition model was used" in reason["redacted_summary"]
        or "MODEL_DETECTED" not in reason["redacted_summary"]
        for reason in result.sensitivity_reasons
    )


def test_personal_data_pattern_is_sensitive() -> None:
    result = classify_sensitivity(
        "survey/respondent.txt",
        "UNKNOWN",
        sample_text="邮箱 alice@example.com 电话 13800138000",
    )

    assert result.data_classification == "SENSITIVE"
    assert "PERSONAL_DATA" in result.content_categories
    assert result.model_usage_restriction == "ALLOW_REDACTED_ONLY"


def test_questionnaire_and_interview_categories_are_detected_by_name() -> None:
    questionnaire = classify_sensitivity("问卷/调查问卷.csv", "SOURCE_TABLE")
    interview = classify_sensitivity("访谈/interview-01.mp3", "UNKNOWN")

    assert questionnaire.content_categories == ("QUESTIONNAIRE",)
    assert questionnaire.data_classification == "SENSITIVE"
    assert set(interview.content_categories) == {"INTERVIEW", "AUDIO"}
    assert interview.data_classification == "SENSITIVE"


@pytest.mark.parametrize(
    ("relative_path", "expected_category"),
    [
        ("database/prod.dump", "DATABASE_DUMP"),
        ("config/secrets.json", "CREDENTIAL"),
    ],
)
def test_database_dump_and_credentials_are_restricted(
    relative_path: str, expected_category: str
) -> None:
    result = classify_sensitivity(relative_path, "SENSITIVE_DATA")

    assert result.data_classification == "RESTRICTED"
    assert expected_category in result.content_categories
    assert result.access_recommendation == "SECURITY_REVIEW_REQUIRED"
    assert result.model_usage_restriction == "DENY_EXTERNAL_MODEL"


@pytest.mark.parametrize(
    ("relative_path", "category"),
    [("media/demo.mp4", "VIDEO"), ("media/note.wav", "AUDIO")],
)
def test_video_and_audio_categories_are_expressed(
    relative_path: str, category: str
) -> None:
    result = classify_sensitivity(relative_path, "UNKNOWN")

    assert category in result.content_categories
    assert result.data_classification == "INTERNAL"


def test_default_project_material_is_internal() -> None:
    result = classify_sensitivity("docs/notes.txt", "UNKNOWN")

    assert result.data_classification == "INTERNAL"
    assert result.content_categories == ()
    assert result.sensitivity_reasons == ()
