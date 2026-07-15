from __future__ import annotations

import pytest

from thesis_ingest.paths import (
    PathPolicy,
    PathSafetyError,
    calculate_root_fingerprint,
    make_ingest_record_id,
    make_source_occurrence_key,
    normalize_relative_path,
)


SENSITIVE_POLICY = PathPolicy(
    case_policy="CASE_SENSITIVE",
    unicode_normalization="NFC",
    version="path-nfc-posix-v1",
)
INSENSITIVE_POLICY = PathPolicy(
    case_policy="CASE_INSENSITIVE",
    unicode_normalization="NFC",
    version="path-nfc-posix-v1",
)


def test_normalized_relative_path_uses_forward_slashes_and_nfc() -> None:
    normalized = normalize_relative_path("docs\\e\u0301.txt", SENSITIVE_POLICY)

    assert normalized.relative_path == "docs/é.txt"
    assert normalized.path_key == "docs/é.txt"
    assert "\\" not in normalized.relative_path


def test_case_insensitive_mount_preserves_display_case_but_casefolds_key() -> None:
    normalized = normalize_relative_path("Source/Über.PY", INSENSITIVE_POLICY)

    assert normalized.relative_path == "Source/Über.PY"
    assert normalized.path_key == "source/über.py"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/absolute/file.txt",
        "C:/absolute/file.txt",
        "C:\\absolute\\file.txt",
        "\\\\server\\share\\file.txt",
        "file:///tmp/file.txt",
    ],
)
def test_absolute_drive_unc_and_uri_paths_are_rejected(unsafe_path: str) -> None:
    with pytest.raises(PathSafetyError):
        normalize_relative_path(unsafe_path, SENSITIVE_POLICY)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../escape.txt",
        "folder/../../escape.txt",
        "folder//empty.txt",
        "folder/name:stream",
        "folder/name\x00.txt",
        "folder/name\x1f.txt",
    ],
)
def test_parent_empty_ads_nul_and_control_segments_are_rejected(
    unsafe_path: str,
) -> None:
    with pytest.raises(PathSafetyError):
        normalize_relative_path(unsafe_path, SENSITIVE_POLICY)


def test_dot_segments_are_removed_without_changing_logical_location() -> None:
    normalized = normalize_relative_path("docs/./chapter/./one.txt", SENSITIVE_POLICY)

    assert normalized.relative_path == "docs/chapter/one.txt"


def test_ingest_record_id_is_scan_specific() -> None:
    first = make_ingest_record_id("scan-a", "mount-a", "docs/file.txt")
    second = make_ingest_record_id("scan-b", "mount-a", "docs/file.txt")

    assert first.startswith("sha256:")
    assert first != second


def test_source_occurrence_key_uses_only_mount_path_and_content() -> None:
    content_hash = "sha256:" + "1" * 64

    first = make_source_occurrence_key("mount-a", "docs/file.txt", content_hash)
    second = make_source_occurrence_key("mount-a", "docs/file.txt", content_hash)

    assert first == second
    assert first.startswith("sha256:")


def test_root_fingerprint_is_order_independent_and_reports_strength() -> None:
    records = [
        {
            "relative_path": "b.txt",
            "content_hash": None,
            "hash_status": "SKIPPED_BY_POLICY",
            "size_bytes": 2,
        },
        {
            "relative_path": "a.txt",
            "content_hash": "sha256:" + "a" * 64,
            "hash_status": "COMPUTED",
            "size_bytes": 1,
        },
    ]

    first = calculate_root_fingerprint(records)
    second = calculate_root_fingerprint(list(reversed(records)))

    assert first == second
    assert first["record_count"] == 2
    assert first["hashed_record_count"] == 1
    assert first["strength"] == "MIXED"


def test_root_fingerprint_is_strong_when_every_record_is_hashed() -> None:
    fingerprint = calculate_root_fingerprint(
        [
            {
                "relative_path": "a.txt",
                "content_hash": "sha256:" + "a" * 64,
                "hash_status": "COMPUTED",
                "size_bytes": 1,
            }
        ]
    )

    assert fingerprint["strength"] == "STRONG"
