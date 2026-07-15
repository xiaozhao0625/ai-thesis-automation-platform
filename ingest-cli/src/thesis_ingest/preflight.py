from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from pathlib import Path

from thesis_ingest.config import RuleBundle


@dataclass(frozen=True)
class PreflightInput:
    physical_path: Path
    relative_path: str
    discovery_excluded: bool = False
    path_collision: bool = False


@dataclass(frozen=True)
class PreflightDecision:
    decision: str
    parser_eligible: bool
    requires_review: bool
    reason_codes: tuple[str, ...]
    rule_matches: tuple[dict[str, str], ...]


def evaluate_preflight(
    item: PreflightInput,
    rules: RuleBundle,
    *,
    classification_confidence: float | None = None,
) -> PreflightDecision:
    document = rules.documents["ingest-rules.json"]
    if not isinstance(document, dict):
        raise ValueError("ingest rules document must be an object")
    relative_lower = item.relative_path.casefold()
    segments = tuple(segment.casefold() for segment in item.relative_path.split("/"))
    name = segments[-1]
    extension = Path(name).suffix.casefold()

    if item.path_collision:
        return _decision(
            "QUARANTINED",
            "PATH_NORMALIZATION_COLLISION",
            "PATH",
            "path-normalization-collision",
        )
    if item.discovery_excluded:
        return _decision(
            "EXCLUDED",
            "DIRECTORY_EXCLUDED",
            "PATH",
            "directory-excluded",
        )

    executable_extensions = _string_set(document, "executable_extensions")
    if extension in executable_extensions:
        return _decision(
            "QUARANTINED",
            "EXECUTABLE_EXTENSION",
            "EXTENSION",
            "executable-extension",
        )
    signature = _read_signature(item.physical_path)
    if signature.startswith((b"MZ", b"\x7fELF")):
        return _decision(
            "QUARANTINED",
            "EXECUTABLE_SIGNATURE",
            "CONTENT_SIGNATURE",
            "executable-signature",
        )

    dump_extensions = _string_set(document, "database_dump_extensions")
    dump_name_tokens = {"backup", "dump", "export", "snapshot"}
    is_dump = extension in dump_extensions - {".sql"} or (
        extension == ".sql"
        and any(token in relative_lower for token in dump_name_tokens)
    )
    if is_dump:
        return _decision(
            "QUARANTINED",
            "DATABASE_DUMP_RISK",
            "PATH",
            "database-dump-risk",
        )

    credential_names = _string_set(document, "credential_file_names")
    credential_tokens = _string_set(document, "credential_name_tokens")
    if name in credential_names or any(token in name for token in credential_tokens):
        return _decision(
            "QUARANTINED",
            "CREDENTIAL_RISK",
            "FILE_NAME",
            "credential-risk",
        )

    if extension in _string_set(document, "archive_extensions"):
        return _decision(
            "QUARANTINED",
            "SUSPICIOUS_ARCHIVE",
            "EXTENSION",
            "suspicious-archive",
        )

    third_party_segments = _string_set(document, "third_party_path_segments")
    if any(segment in third_party_segments for segment in segments):
        return _decision(
            "EXCLUDED",
            "THIRD_PARTY_DEPENDENCY",
            "PATH",
            "third-party-dependency",
        )
    build_segments = _string_set(document, "build_directories")
    if any(segment in build_segments for segment in segments):
        return _decision(
            "EXCLUDED",
            "BUILD_OUTPUT",
            "PATH",
            "build-output",
        )

    backup_patterns = _string_list(document, "backup_name_patterns")
    rotated_patterns = _string_list(document, "rotated_log_patterns")
    if any(
        fnmatch.fnmatchcase(name, pattern.casefold())
        for pattern in (*backup_patterns, *rotated_patterns)
    ):
        return _decision(
            "EXCLUDED",
            "BACKUP_OR_AUTOSAVE",
            "FILE_NAME",
            "backup-or-autosave",
        )

    if _looks_binary(signature) and not _is_known_binary_container(
        extension, document
    ):
        return _decision(
            "QUARANTINED",
            "UNKNOWN_BINARY",
            "CONTENT_SIGNATURE",
            "unknown-binary",
        )

    if classification_confidence is not None and classification_confidence < 0.6:
        return _decision(
            "NEEDS_REVIEW",
            "LOW_CLASSIFICATION_CONFIDENCE",
            "METADATA",
            "low-classification-confidence",
        )
    return _decision("ACCEPTED", "PRECHECK_ACCEPTED", "METADATA", "accepted")


def _decision(
    decision: str,
    reason: str,
    signal_type: str,
    rule_id: str,
) -> PreflightDecision:
    parser_eligible = decision == "ACCEPTED"
    return PreflightDecision(
        decision=decision,
        parser_eligible=parser_eligible,
        requires_review=decision == "NEEDS_REVIEW",
        reason_codes=(reason,),
        rule_matches=(
            {
                "rule_id": rule_id,
                "signal_type": signal_type,
                "reason_code": reason,
                "redacted_summary": reason.replace("_", " ").lower(),
            },
        ),
    )


def _string_list(document: dict[object, object], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid rule list: {key}")
    return tuple(value)


def _string_set(document: dict[object, object], key: str) -> set[str]:
    return {item.casefold() for item in _string_list(document, key)}


def _read_signature(path: Path, size: int = 4096) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(size)
    except OSError:
        return b""


def _looks_binary(payload: bytes) -> bool:
    if not payload:
        return False
    if b"\x00" in payload:
        return True
    printable = sum(
        byte in b"\t\n\r" or 32 <= byte <= 126 or byte >= 128 for byte in payload
    )
    return printable / len(payload) < 0.7


def _is_known_binary_container(
    extension: str, document: dict[object, object]
) -> bool:
    known = (
        _string_set(document, "known_document_extensions")
        | _string_set(document, "known_media_extensions")
    )
    return extension in known
