from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import stat

from thesis_ingest.paths import PathPolicy, normalize_relative_path


@dataclass(frozen=True)
class DiscoveredItem:
    physical_path: Path
    observed_relative_path: str
    relative_path: str
    path_key: str
    size_bytes: int
    modified_time_ns: int
    discovery_excluded: bool = False
    path_collision: bool = False

    @classmethod
    def for_test(cls, relative_path: str, *, path_key: str) -> "DiscoveredItem":
        return cls(
            physical_path=Path(relative_path),
            observed_relative_path=relative_path,
            relative_path=relative_path,
            path_key=path_key,
            size_bytes=0,
            modified_time_ns=0,
        )

    def identity_fields(self) -> dict[str, object]:
        return {
            "observed_relative_path": self.observed_relative_path,
            "relative_path": self.relative_path,
            "path_key": self.path_key,
            "size_bytes": self.size_bytes,
            "modified_time_ns": self.modified_time_ns,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    items: list[DiscoveredItem]
    pruned_directories: list[str]
    skipped_links: list[str]
    collisions: dict[str, tuple[str, ...]]


def discover_files(
    root: Path,
    policy: PathPolicy,
    *,
    excluded_directories: set[str],
    emit_excluded_item_records: bool = False,
) -> DiscoveryResult:
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise ValueError(f"source root is not a directory: {resolved_root}")
    excluded_keys = {name.casefold() for name in excluded_directories}
    items: list[DiscoveredItem] = []
    pruned_directories: list[str] = []
    skipped_links: list[str] = []

    def walk(
        directory: Path,
        relative_segments: tuple[str, ...],
        inherited_excluded: bool,
    ) -> None:
        entries = sorted(
            os.scandir(directory),
            key=lambda entry: entry.name.encode("utf-8", errors="surrogatepass"),
        )
        for entry in entries:
            raw_relative = "/".join((*relative_segments, entry.name))
            if entry.is_symlink():
                skipped_links.append(
                    normalize_relative_path(raw_relative, policy).relative_path
                )
                continue
            metadata = entry.stat(follow_symlinks=False)
            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            if getattr(metadata, "st_file_attributes", 0) & reparse_flag:
                skipped_links.append(
                    normalize_relative_path(raw_relative, policy).relative_path
                )
                continue
            if entry.is_dir(follow_symlinks=False):
                directory_excluded = (
                    inherited_excluded or entry.name.casefold() in excluded_keys
                )
                if directory_excluded and not emit_excluded_item_records:
                    pruned_directories.append(
                        normalize_relative_path(raw_relative, policy).relative_path
                    )
                    continue
                walk(
                    Path(entry.path),
                    (*relative_segments, entry.name),
                    directory_excluded,
                )
                continue
            if not entry.is_file(follow_symlinks=False):
                skipped_links.append(
                    normalize_relative_path(raw_relative, policy).relative_path
                )
                continue
            normalized = normalize_relative_path(raw_relative, policy)
            items.append(
                DiscoveredItem(
                    physical_path=Path(entry.path).resolve(),
                    observed_relative_path=normalized.observed_relative_path,
                    relative_path=normalized.relative_path,
                    path_key=normalized.path_key,
                    size_bytes=metadata.st_size,
                    modified_time_ns=metadata.st_mtime_ns,
                    discovery_excluded=inherited_excluded,
                )
            )

    walk(resolved_root, (), False)
    items.sort(key=lambda item: item.relative_path.encode("utf-8"))
    marked_items, collisions = detect_path_collisions(items)
    pruned_directories.sort(key=lambda value: value.encode("utf-8"))
    skipped_links.sort(key=lambda value: value.encode("utf-8"))
    return DiscoveryResult(
        items=marked_items,
        pruned_directories=pruned_directories,
        skipped_links=skipped_links,
        collisions=collisions,
    )


def detect_path_collisions(
    items: list[DiscoveredItem],
) -> tuple[list[DiscoveredItem], dict[str, tuple[str, ...]]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        grouped.setdefault(item.path_key, []).append(item.relative_path)
    collisions = {
        key: tuple(sorted(paths, key=lambda value: value.encode("utf-8")))
        for key, paths in grouped.items()
        if len(paths) > 1
    }
    marked = [
        replace(item, path_collision=item.path_key in collisions) for item in items
    ]
    return marked, collisions
