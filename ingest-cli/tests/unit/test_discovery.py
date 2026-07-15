from __future__ import annotations

import os
from pathlib import Path

import pytest

from thesis_ingest.discovery import (
    DiscoveredItem,
    detect_path_collisions,
    discover_files,
)
from thesis_ingest.paths import PathPolicy


POLICY = PathPolicy(
    case_policy="CASE_SENSITIVE",
    unicode_normalization="NFC",
    version="path-nfc-posix-v1",
)


def test_discovery_order_is_stable_utf8_relative_path_order(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "中.txt").write_text("c", encoding="utf-8")

    first = discover_files(tmp_path, POLICY, excluded_directories=set())
    second = discover_files(tmp_path, POLICY, excluded_directories=set())

    expected = sorted(
        ["z.txt", "a/b.txt", "中.txt"], key=lambda value: value.encode("utf-8")
    )
    assert [item.relative_path for item in first.items] == expected
    assert [item.relative_path for item in second.items] == expected


def test_excluded_directory_is_pruned_when_item_records_are_disabled(
    tmp_path: Path,
) -> None:
    dependency = tmp_path / "node_modules" / "package"
    dependency.mkdir(parents=True)
    (dependency / "index.js").write_text("ignored", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')", encoding="utf-8")

    result = discover_files(
        tmp_path,
        POLICY,
        excluded_directories={"node_modules"},
        emit_excluded_item_records=False,
    )

    assert [item.relative_path for item in result.items] == ["main.py"]
    assert result.pruned_directories == ["node_modules"]


def test_excluded_directory_can_be_metadata_enumerated_without_becoming_eligible(
    tmp_path: Path,
) -> None:
    dependency = tmp_path / ".venv" / "Lib"
    dependency.mkdir(parents=True)
    (dependency / "site.py").write_text("ignored", encoding="utf-8")

    result = discover_files(
        tmp_path,
        POLICY,
        excluded_directories={".venv"},
        emit_excluded_item_records=True,
    )

    assert len(result.items) == 1
    assert result.items[0].relative_path == ".venv/Lib/site.py"
    assert result.items[0].discovery_excluded is True
    assert result.items[0].size_bytes == len("ignored")


def test_symlink_is_not_followed_or_returned_as_a_regular_file(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = discover_files(tmp_path, POLICY, excluded_directories=set())

    assert result.items == []
    assert result.skipped_links == ["linked.txt"]


def test_collision_detection_marks_every_conflicting_item() -> None:
    items = [
        DiscoveredItem.for_test("Readme.txt", path_key="readme.txt"),
        DiscoveredItem.for_test("README.TXT", path_key="readme.txt"),
        DiscoveredItem.for_test("other.txt", path_key="other.txt"),
    ]

    marked, collisions = detect_path_collisions(items)

    assert collisions == {"readme.txt": ("README.TXT", "Readme.txt")}
    assert [item.path_collision for item in marked] == [True, True, False]


def test_discovered_item_keeps_absolute_path_internal_only(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")

    result = discover_files(tmp_path, POLICY, excluded_directories=set())
    public = result.items[0].identity_fields()

    assert result.items[0].physical_path == source.resolve()
    assert set(public) == {
        "observed_relative_path",
        "relative_path",
        "path_key",
        "size_bytes",
        "modified_time_ns",
    }
    assert str(tmp_path) not in repr(public)
