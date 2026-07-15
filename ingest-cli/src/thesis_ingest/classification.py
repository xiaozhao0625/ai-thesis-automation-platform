from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import PurePosixPath

from thesis_ingest.config import RuleBundle


@dataclass(frozen=True)
class ClassificationSuggestion:
    artifact_role: str
    classification_confidence: float
    classification_method: str
    classification_reasons: tuple[str, ...]
    classification_status: str = "PROPOSED"
    classification_authority: str = "AUTOMATED_SUGGESTION"


def classify_artifact(
    relative_path: str,
    decision: str,
    rules: RuleBundle,
) -> ClassificationSuggestion:
    document = rules.documents["artifact-classification.json"]
    ingest_rules = rules.documents["ingest-rules.json"]
    if not isinstance(document, dict) or not isinstance(ingest_rules, dict):
        raise ValueError("classification rules must be objects")
    lowered = relative_path.casefold()
    segments = tuple(part.casefold() for part in PurePosixPath(relative_path).parts)
    name = segments[-1]
    extension = PurePosixPath(name).suffix.casefold()

    if decision == "QUARANTINED" and extension in _values(
        ingest_rules, "executable_extensions"
    ):
        return _suggest("EXECUTABLE", 1.0, "EXTENSION_RULE", "EXECUTABLE_EXTENSION")
    if decision == "QUARANTINED":
        return _suggest(
            "SENSITIVE_DATA", 0.85, "PATH_RULE", "QUARANTINED_SENSITIVE_RISK"
        )

    third_party = _values(ingest_rules, "third_party_path_segments") | {
        ".venv",
        "venv",
        "node_modules",
    }
    if any(segment in third_party for segment in segments):
        return _suggest(
            "THIRD_PARTY_DEPENDENCY",
            0.99,
            "PATH_RULE",
            "THIRD_PARTY_PATH",
        )
    if any(
        segment in _values(ingest_rules, "build_directories")
        for segment in segments
    ):
        return _suggest("BUILD_OUTPUT", 0.95, "PATH_RULE", "BUILD_PATH")
    backup_patterns = _sequence(ingest_rules, "backup_name_patterns")
    if any(fnmatch.fnmatchcase(name, pattern.casefold()) for pattern in backup_patterns):
        return _suggest("BACKUP", 0.95, "FILE_NAME_RULE", "BACKUP_NAME")

    if _contains_any(lowered, _values(document, "requirement_name_tokens")):
        return _suggest(
            "PRIMARY_REQUIREMENT",
            0.95,
            "COMPOSITE_RULE",
            "REQUIREMENT_NAME_SIGNAL",
        )
    if _contains_any(lowered, _values(document, "template_name_tokens")):
        return _suggest("TEMPLATE", 0.95, "COMPOSITE_RULE", "TEMPLATE_NAME_SIGNAL")
    if _contains_any(lowered, _values(document, "reference_name_tokens")):
        return _suggest(
            "REFERENCE_CANDIDATE",
            0.9,
            "FILE_NAME_RULE",
            "REFERENCE_NAME_SIGNAL",
        )
    if _contains_any(
        lowered, _values(document, "official_reference_path_tokens")
    ):
        return _suggest(
            "REFERENCE_CANDIDATE",
            0.85,
            "PATH_RULE",
            "OFFICIAL_REFERENCE_PATH",
        )
    if _contains_any(name, _values(document, "result_name_tokens")):
        return _suggest(
            "ENGINEERING_RESULT",
            0.85,
            "FILE_NAME_RULE",
            "RESULT_NAME_SIGNAL",
        )
    if _contains_any(lowered, _values(document, "generated_name_tokens")):
        return _suggest(
            "GENERATED_DRAFT",
            0.9,
            "FILE_NAME_RULE",
            "GENERATED_NAME_SIGNAL",
        )
    if "论文正文" in lowered or name.startswith("正文"):
        return _suggest(
            "PRIMARY_DOCUMENT",
            0.9,
            "COMPOSITE_RULE",
            "PRIMARY_DOCUMENT_NAME_SIGNAL",
        )
    if _contains_any(lowered, _values(document, "draft_name_tokens")):
        return _suggest(
            "EXISTING_DRAFT",
            0.85,
            "COMPOSITE_RULE",
            "DRAFT_NAME_SIGNAL",
        )

    if extension in _values(document, "source_extensions"):
        return _suggest(
            "ENGINEERING_SOURCE", 0.7, "EXTENSION_RULE", "SOURCE_EXTENSION"
        )
    if extension in _values(document, "config_extensions"):
        return _suggest(
            "ENGINEERING_CONFIG", 0.7, "EXTENSION_RULE", "CONFIG_EXTENSION"
        )
    if extension in _values(document, "image_extensions"):
        return _suggest("SOURCE_IMAGE", 0.7, "EXTENSION_RULE", "IMAGE_EXTENSION")
    if extension in _values(document, "table_extensions"):
        return _suggest("SOURCE_TABLE", 0.7, "EXTENSION_RULE", "TABLE_EXTENSION")
    return _suggest("UNKNOWN", 0.3, "EXTENSION_RULE", "NO_CONFIDENT_ROLE_RULE")


def _suggest(
    role: str,
    confidence: float,
    method: str,
    reason: str,
) -> ClassificationSuggestion:
    if method == "EXTENSION_RULE":
        confidence = min(confidence, 0.7)
    return ClassificationSuggestion(
        artifact_role=role,
        classification_confidence=confidence,
        classification_method=method,
        classification_reasons=(reason,),
    )


def _sequence(document: dict[object, object], name: str) -> tuple[str, ...]:
    value = document.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid classification rule: {name}")
    return tuple(value)


def _values(document: dict[object, object], name: str) -> set[str]:
    return {value.casefold() for value in _sequence(document, name)}


def _contains_any(value: str, tokens: set[str]) -> bool:
    return any(token in value for token in tokens)
