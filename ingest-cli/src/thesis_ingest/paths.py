from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata

from thesis_ingest.canonical_json import dumps_bytes


class PathSafetyError(ValueError):
    """Raised when a path cannot be represented safely inside a SourceMount."""


@dataclass(frozen=True)
class PathPolicy:
    case_policy: str
    unicode_normalization: str
    version: str


@dataclass(frozen=True)
class NormalizedPath:
    observed_relative_path: str
    relative_path: str
    path_key: str


def normalize_relative_path(
    value: str, policy: PathPolicy
) -> NormalizedPath:
    if not isinstance(value, str) or not value:
        raise PathSafetyError("relative path must be a non-empty string")
    if policy.unicode_normalization != "NFC":
        raise PathSafetyError("only NFC path normalization is supported")
    if policy.case_policy not in {"CASE_SENSITIVE", "CASE_INSENSITIVE"}:
        raise PathSafetyError("unsupported case policy")
    if (
        value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", value)
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value)
    ):
        raise PathSafetyError("absolute, drive, UNC, and URI paths are forbidden")

    observed = value.replace("\\", "/")
    raw_segments = observed.split("/")
    if any(segment == "" for segment in raw_segments):
        raise PathSafetyError("empty path segments are forbidden")

    normalized_segments: list[str] = []
    for segment in raw_segments:
        if segment == ".":
            continue
        if segment == "..":
            raise PathSafetyError("parent path segments are forbidden")
        if ":" in segment:
            raise PathSafetyError("colons and NTFS alternate streams are forbidden")
        if any(unicodedata.category(character) == "Cc" for character in segment):
            raise PathSafetyError("NUL and control characters are forbidden")
        normalized_segments.append(unicodedata.normalize("NFC", segment))
    if not normalized_segments:
        raise PathSafetyError("relative path resolves to an empty location")

    relative_path = "/".join(normalized_segments)
    path_key = relative_path
    if policy.case_policy == "CASE_INSENSITIVE":
        path_key = unicodedata.normalize("NFC", relative_path.casefold())
    return NormalizedPath(
        observed_relative_path=observed,
        relative_path=relative_path,
        path_key=path_key,
    )


def make_ingest_record_id(
    scan_id: str, source_mount_id: str, observed_relative_path: str
) -> str:
    return _hash_projection(
        {
            "observed_relative_path": observed_relative_path,
            "scan_id": scan_id,
            "source_mount_id": source_mount_id,
        }
    )


def make_source_occurrence_key(
    source_mount_id: str, relative_path: str, content_hash: str
) -> str:
    return _hash_projection(
        {
            "content_hash": content_hash,
            "relative_path": relative_path,
            "source_mount_id": source_mount_id,
        }
    )


def calculate_root_fingerprint(
    records: list[dict[str, object]],
) -> dict[str, object]:
    projections = [
        {
            "content_hash": record.get("content_hash"),
            "hash_status": record["hash_status"],
            "relative_path": record["relative_path"],
            "size_bytes": record["size_bytes"],
        }
        for record in records
    ]
    projections.sort(
        key=lambda record: str(record["relative_path"]).encode("utf-8")
    )
    hashed_count = sum(
        record["hash_status"] == "COMPUTED" for record in projections
    )
    return {
        "algorithm": "SHA-256",
        "canonicalization_version": "RFC8785-JCS-v1",
        "scope": "RECORDED_ITEMS",
        "strength": (
            "STRONG" if hashed_count == len(projections) else "MIXED"
        ),
        "record_count": len(projections),
        "hashed_record_count": hashed_count,
        "value": _hash_bytes(dumps_bytes(projections)),
    }


def _hash_projection(value: object) -> str:
    return _hash_bytes(dumps_bytes(value))


def _hash_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()
