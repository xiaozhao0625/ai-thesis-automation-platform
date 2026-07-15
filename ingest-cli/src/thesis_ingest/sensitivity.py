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
    sensitivity_reasons: tuple[dict[str, object], ...]


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
    reasons: list[dict[str, object]] = []

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
        reasons.append(
            _reason(
                "credential-name-v1",
                "CREDENTIAL",
                "FILE_NAME",
                "A credential-like file-name signal was detected.",
                0.95,
            )
        )

    if extension in {".dump", ".dmp", ".sqlite", ".sqlite3"} or (
        extension == ".sql"
        and any(token in lowered for token in {"backup", "dump", "export"})
    ):
        categories.add("DATABASE_DUMP")
        reasons.append(
            _reason(
                "database-dump-path-v1",
                "DATABASE_DUMP",
                "PATH_SEGMENT",
                "A database-dump path or extension signal was detected.",
                0.95,
            )
        )

    image_extensions = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
    if extension in image_extensions and any(
        token in lowered for token in {"face", "portrait", "student", "人脸", "头像"}
    ):
        categories.add("FACE_IMAGE")
        reasons.append(
            _reason(
                "face-image-name-v1",
                "FACE_IMAGE",
                "FILE_NAME",
                "The image file name contains a face-related signal; no recognition model was used.",
                0.75,
            )
        )

    if any(token in lowered for token in {"questionnaire", "survey", "问卷", "调查表"}):
        categories.add("QUESTIONNAIRE")
        reasons.append(
            _reason(
                "questionnaire-name-v1",
                "QUESTIONNAIRE",
                "FILE_NAME",
                "The path contains a questionnaire-related signal.",
                0.8,
            )
        )
    if any(token in lowered for token in {"interview", "访谈", "采访"}):
        categories.add("INTERVIEW")
        reasons.append(
            _reason(
                "interview-name-v1",
                "INTERVIEW",
                "FILE_NAME",
                "The path contains an interview-related signal.",
                0.8,
            )
        )

    if extension in {".avi", ".mkv", ".mov", ".mp4", ".webm"}:
        categories.add("VIDEO")
        reasons.append(
            _reason(
                "video-extension-v1",
                "VIDEO",
                "METADATA",
                "The file extension identifies a video container.",
                0.9,
            )
        )
    if extension in {".aac", ".flac", ".m4a", ".mp3", ".wav"}:
        categories.add("AUDIO")
        reasons.append(
            _reason(
                "audio-extension-v1",
                "AUDIO",
                "METADATA",
                "The file extension identifies an audio container.",
                0.9,
            )
        )

    if artifact_role == "ENGINEERING_SOURCE":
        categories.add("SOURCE_CODE")
        reasons.append(
            _reason(
                "source-code-role-v1",
                "SOURCE_CODE",
                "METADATA",
                "The automated ArtifactRole suggestion identifies source code.",
                0.9,
            )
        )

    if sample_text and _contains_personal_data(sample_text):
        categories.add("PERSONAL_DATA")
        reasons.append(
            _reason(
                "personal-data-pattern-v1",
                "PERSONAL_DATA",
                "CONTENT_PREFIX",
                "A personal-data pattern was detected in a bounded text prefix; the value was not recorded.",
                0.8,
            )
        )

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
            sensitivity_reasons=(),
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
        sensitivity_reasons=tuple(reasons),
    )


def _contains_personal_data(value: str) -> bool:
    email = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    mainland_phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    return bool(email.search(value) or mainland_phone.search(value))


def _reason(
    rule_id: str,
    category: str,
    location_kind: str,
    summary: str,
    confidence: float,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "category": category,
        "location_kind": location_kind,
        "redacted_summary": summary,
        "confidence": confidence,
    }
