from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


@dataclass(frozen=True)
class SensitivitySuggestion:
    data_classification: str
    content_categories: tuple[str, ...]
    access_recommendation: str
    model_usage_restriction: str
    sensitivity_confidence: float
    sensitivity_reasons: tuple[str, ...]


def classify_sensitivity(
    relative_path: str,
    artifact_role: str,
    *,
    sample_text: str | None = None,
) -> SensitivitySuggestion:
    lowered = relative_path.casefold()
    name = PurePosixPath(lowered).name
    extension = PurePosixPath(name).suffix
    categories: set[str] = set()
    reasons: list[str] = []

    credential_tokens = {
        ".env",
        "credential",
        "id_dsa",
        "id_ed25519",
        "id_rsa",
        "passwd",
        "password",
        "secret",
        "token",
    }
    if any(token in name for token in credential_tokens):
        categories.add("CREDENTIAL")
        reasons.append("CREDENTIAL_NAME_HEURISTIC")

    if extension in {".dump", ".dmp", ".sqlite", ".sqlite3"} or (
        extension == ".sql"
        and any(token in lowered for token in {"backup", "dump", "export"})
    ):
        categories.add("DATABASE_DUMP")
        reasons.append("DATABASE_DUMP_PATH_HEURISTIC")

    image_extensions = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
    if extension in image_extensions and any(
        token in lowered for token in {"face", "portrait", "student", "人脸", "头像"}
    ):
        categories.add("FACE_IMAGE")
        reasons.append("FACE_IMAGE_NAME_HEURISTIC")

    if any(token in lowered for token in {"questionnaire", "survey", "问卷", "调查表"}):
        categories.add("QUESTIONNAIRE")
        reasons.append("QUESTIONNAIRE_NAME_HEURISTIC")
    if any(token in lowered for token in {"interview", "访谈", "采访"}):
        categories.add("INTERVIEW")
        reasons.append("INTERVIEW_NAME_HEURISTIC")

    if extension in {".avi", ".mkv", ".mov", ".mp4", ".webm"}:
        categories.add("VIDEO")
        reasons.append("VIDEO_EXTENSION")
    if extension in {".aac", ".flac", ".m4a", ".mp3", ".wav"}:
        categories.add("AUDIO")
        reasons.append("AUDIO_EXTENSION")

    if artifact_role == "ENGINEERING_SOURCE":
        categories.add("SOURCE_CODE")
        reasons.append("SOURCE_CODE_ROLE")

    if sample_text and _contains_personal_data(sample_text):
        categories.add("PERSONAL_DATA")
        reasons.append("PERSONAL_DATA_PATTERN_HEURISTIC")

    ordered_categories = tuple(
        category
        for category in (
            "FACE_IMAGE",
            "PERSONAL_DATA",
            "QUESTIONNAIRE",
            "INTERVIEW",
            "DATABASE_DUMP",
            "CREDENTIAL",
            "SOURCE_CODE",
            "VIDEO",
            "AUDIO",
        )
        if category in categories
    )

    if categories & {"DATABASE_DUMP", "CREDENTIAL"}:
        return SensitivitySuggestion(
            data_classification="RESTRICTED",
            content_categories=ordered_categories,
            access_recommendation="SECURITY_REVIEW_REQUIRED",
            model_usage_restriction="DENY_EXTERNAL_MODEL",
            sensitivity_confidence=0.95,
            sensitivity_reasons=tuple(reasons),
        )
    if categories & {"FACE_IMAGE", "PERSONAL_DATA", "QUESTIONNAIRE", "INTERVIEW"}:
        deny_external = bool(categories & {"FACE_IMAGE", "INTERVIEW"})
        return SensitivitySuggestion(
            data_classification="SENSITIVE",
            content_categories=ordered_categories,
            access_recommendation="ROLE_RESTRICTED",
            model_usage_restriction=(
                "DENY_EXTERNAL_MODEL" if deny_external else "ALLOW_REDACTED_ONLY"
            ),
            sensitivity_confidence=0.8,
            sensitivity_reasons=tuple(reasons),
        )
    if lowered.startswith(("fixed-official-sources/", "official-reference/")):
        return SensitivitySuggestion(
            data_classification="PUBLIC",
            content_categories=ordered_categories,
            access_recommendation="STANDARD",
            model_usage_restriction="ALLOW",
            sensitivity_confidence=0.9,
            sensitivity_reasons=("FIXED_OFFICIAL_SOURCE_SCOPE",),
        )
    if artifact_role == "ENGINEERING_SOURCE":
        return SensitivitySuggestion(
            data_classification="INTERNAL",
            content_categories=ordered_categories,
            access_recommendation="RESTRICT_PREVIEW",
            model_usage_restriction="LOCAL_MODEL_ONLY",
            sensitivity_confidence=0.9,
            sensitivity_reasons=tuple(reasons),
        )
    return SensitivitySuggestion(
        data_classification="INTERNAL",
        content_categories=ordered_categories,
        access_recommendation="RESTRICT_PREVIEW",
        model_usage_restriction="LOCAL_MODEL_ONLY",
        sensitivity_confidence=0.6,
        sensitivity_reasons=tuple(reasons) or ("DEFAULT_PROJECT_INTERNAL",),
    )


def _contains_personal_data(value: str) -> bool:
    email = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    mainland_phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    return bool(email.search(value) or mainland_phone.search(value))
