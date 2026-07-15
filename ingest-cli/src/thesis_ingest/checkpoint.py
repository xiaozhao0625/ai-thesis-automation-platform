from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path

from thesis_ingest.canonical_json import CanonicalJsonError, dumps_bytes, loads_strict
from thesis_ingest.hashing import HashingError, hash_file
from thesis_ingest.paths import PathPolicy, PathSafetyError, normalize_relative_path

class CheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceSnapshot:
    relative_path: str
    size_bytes: int
    modified_time_ns: int
    content_hash: str | None


@dataclass(frozen=True)
class CheckpointState:
    checkpoint_id: str
    scan_id: str
    config_hash: str
    rule_set_version: str
    path_normalization_version: str
    next_index: int
    source_snapshots: tuple[SourceSnapshot, ...]
    payload: dict[str, object]
    checkpoint_version: str = "0.1"


def save_checkpoint(path: Path, state: CheckpointState) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(destination) + ".tmp")
    payload = asdict(state)
    try:
        temporary.write_bytes(dumps_bytes(payload) + b"\n")
        os.replace(temporary, destination)
    except OSError as exc:
        raise CheckpointError(f"CHECKPOINT_WRITE_FAILED: {exc}") from exc


def load_checkpoint(
    path: Path,
    *,
    expected_scan_id: str,
    expected_config_hash: str,
    expected_rule_set_version: str,
    expected_path_normalization_version: str,
    source_root: Path,
) -> CheckpointState:
    try:
        raw = loads_strict(path.read_bytes())
        if not isinstance(raw, dict):
            raise ValueError("checkpoint root must be an object")
        snapshots_raw = raw["source_snapshots"]
        payload = raw["payload"]
        if not isinstance(snapshots_raw, list) or not isinstance(payload, dict):
            raise ValueError("invalid source snapshots or payload")
        snapshots = tuple(
            SourceSnapshot(
                relative_path=_required_str(item, "relative_path"),
                size_bytes=_required_int(item, "size_bytes"),
                modified_time_ns=_required_int(item, "modified_time_ns"),
                content_hash=(
                    item.get("content_hash")
                    if isinstance(item.get("content_hash"), str)
                    else None
                ),
            )
            for item in snapshots_raw
            if isinstance(item, dict)
        )
        if len(snapshots) != len(snapshots_raw):
            raise ValueError("invalid source snapshot entry")
        state = CheckpointState(
            checkpoint_id=_required_str(raw, "checkpoint_id"),
            scan_id=_required_str(raw, "scan_id"),
            config_hash=_required_str(raw, "config_hash"),
            rule_set_version=_required_str(raw, "rule_set_version"),
            path_normalization_version=_required_str(
                raw, "path_normalization_version"
            ),
            next_index=_required_int(raw, "next_index"),
            source_snapshots=snapshots,
            payload=payload,
            checkpoint_version=_required_str(raw, "checkpoint_version"),
        )
    except (OSError, CanonicalJsonError, KeyError, TypeError, ValueError) as exc:
        raise CheckpointError(f"CHECKPOINT_INVALID: {exc}") from exc
    if state.checkpoint_version != "0.1":
        raise CheckpointError("CHECKPOINT_VERSION_MISMATCH")
    if state.scan_id != expected_scan_id:
        raise CheckpointError("CHECKPOINT_SCAN_MISMATCH")
    if state.config_hash != expected_config_hash:
        raise CheckpointError("CHECKPOINT_CONFIG_MISMATCH")
    if state.rule_set_version != expected_rule_set_version:
        raise CheckpointError("CHECKPOINT_RULE_SET_MISMATCH")
    if state.path_normalization_version != expected_path_normalization_version:
        raise CheckpointError("CHECKPOINT_PATH_VERSION_MISMATCH")
    _verify_source_snapshots(source_root, state.source_snapshots)
    return state


def _verify_source_snapshots(
    source_root: Path, snapshots: tuple[SourceSnapshot, ...]
) -> None:
    root = source_root.resolve()
    policy = PathPolicy(
        case_policy="CASE_SENSITIVE",
        unicode_normalization="NFC",
        version="path-nfc-posix-v1",
    )
    for snapshot in snapshots:
        try:
            normalized = normalize_relative_path(snapshot.relative_path, policy)
        except PathSafetyError as exc:
            raise CheckpointError(f"CHECKPOINT_SOURCE_PATH_INVALID: {exc}") from exc
        source = (root / Path(*normalized.relative_path.split("/"))).resolve()
        if source == root or root not in source.parents:
            raise CheckpointError("CHECKPOINT_SOURCE_PATH_INVALID")
        try:
            metadata = source.stat()
        except OSError as exc:
            raise CheckpointError(f"CHECKPOINT_SOURCE_CHANGED: {exc}") from exc
        if (
            metadata.st_size != snapshot.size_bytes
            or metadata.st_mtime_ns != snapshot.modified_time_ns
        ):
            raise CheckpointError(
                f"CHECKPOINT_SOURCE_CHANGED: {snapshot.relative_path}"
            )
        if snapshot.content_hash is not None:
            try:
                current_hash = hash_file(source).content_hash
            except HashingError as exc:
                raise CheckpointError(
                    f"CHECKPOINT_SOURCE_HASH_FAILED: {snapshot.relative_path}"
                ) from exc
            if current_hash != snapshot.content_hash:
                raise CheckpointError(
                    f"CHECKPOINT_SOURCE_HASH_MISMATCH: {snapshot.relative_path}"
                )


def _required_str(value: dict[object, object], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{name} must be a non-empty string")
    return item


def _required_int(value: dict[object, object], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return item
