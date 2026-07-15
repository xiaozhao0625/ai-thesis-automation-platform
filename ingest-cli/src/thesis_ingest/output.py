from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from thesis_ingest.canonical_json import dumps_bytes
from thesis_ingest.contracts import ContractError, validate_instance


class OutputError(RuntimeError):
    pass


@dataclass
class PackageContents:
    manifest: dict[str, object]
    source_mounts: dict[str, object]
    artifacts: list[dict[str, object]]
    excluded_items: list[dict[str, object]]
    duplicate_groups: list[dict[str, object]]
    primary_candidates: list[dict[str, object]]
    reference_candidates: list[dict[str, object]]
    sensitive_items: list[dict[str, object]]
    ingest_issues: list[dict[str, object]]
    summary: dict[str, object]


OUTPUT_ROUTES: tuple[tuple[str, str, str, str], ...] = (
    (
        "source-mounts.json",
        "source_mounts",
        "source-mount.schema.json",
        "#/$defs/SourceMountCollection",
    ),
    (
        "artifacts.jsonl",
        "artifacts",
        "artifact-ingest-record.schema.json",
        "#",
    ),
    (
        "excluded-items.jsonl",
        "excluded_items",
        "artifact-ingest-record.schema.json",
        "#",
    ),
    (
        "duplicate-groups.jsonl",
        "duplicate_groups",
        "artifact-ingest-record.schema.json",
        "#/$defs/duplicate_group",
    ),
    (
        "primary-candidates.jsonl",
        "primary_candidates",
        "artifact-ingest-record.schema.json",
        "#/$defs/primary_artifact_candidate",
    ),
    (
        "reference-candidates.jsonl",
        "reference_candidates",
        "artifact-ingest-record.schema.json",
        "#/$defs/reference_candidate",
    ),
    (
        "sensitive-items.jsonl",
        "sensitive_items",
        "artifact-ingest-record.schema.json",
        "#/$defs/sensitive_item",
    ),
    (
        "ingest-issues.jsonl",
        "ingest_issues",
        "artifact-ingest-record.schema.json",
        "#/$defs/ingest_issue",
    ),
    (
        "summary.json",
        "summary",
        "ingest-manifest.schema.json",
        "#/$defs/Summary",
    ),
)


def publish_package(output_path: Path, contents: PackageContents) -> Path:
    output_path = output_path.resolve()
    if output_path.exists() and (
        not output_path.is_dir() or any(output_path.iterdir())
    ):
        raise OutputError(f"OUTPUT_TARGET_NOT_EMPTY: {output_path}")
    _validate_semantics(contents)
    scan_id = contents.manifest.get("scan_id")
    if not isinstance(scan_id, str) or not scan_id:
        raise OutputError("MANIFEST_SCAN_ID_INVALID")
    staging_root = output_path.parent / f".{output_path.name}.staging" / scan_id
    publish_root = staging_root / "publish"
    if publish_root.exists():
        raise OutputError(f"STAGING_PUBLISH_ALREADY_EXISTS: {publish_root}")
    publish_root.mkdir(parents=True, exist_ok=False)

    descriptors: list[dict[str, object]] = []
    try:
        for name, attribute, schema_name, fragment in OUTPUT_ROUTES:
            value = getattr(contents, attribute)
            payload, record_count = _encode_and_validate(
                name,
                value,
                schema_name,
                fragment,
            )
            destination = publish_root / name
            destination.write_bytes(payload)
            descriptors.append(
                {
                    "relative_path": name,
                    "content_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                    "record_count": record_count,
                    "schema_ref": schema_name,
                    "schema_fragment": fragment,
                }
            )
        manifest = dict(contents.manifest)
        manifest["output_hashes"] = descriptors
        validate_instance(manifest, "ingest-manifest.schema.json")
        (publish_root / "ingest-manifest.json").write_bytes(
            dumps_bytes(manifest) + b"\n"
        )
        if output_path.exists():
            output_path.rmdir()
        publish_root.replace(output_path)
    except (OSError, ContractError, ValueError) as exc:
        raise OutputError(f"OUTPUT_WRITE_FAILED: {exc}") from exc
    return output_path


def _encode_and_validate(
    name: str,
    value: object,
    schema_name: str,
    fragment: str,
) -> tuple[bytes, int]:
    schema_fragment = None if fragment == "#" else fragment
    if name.endswith(".jsonl"):
        if not isinstance(value, list):
            raise OutputError(f"OUTPUT_VALUE_INVALID: {name} must be a list")
        lines: list[bytes] = []
        for record in value:
            validate_instance(
                record,
                schema_name,
                schema_fragment=schema_fragment,
            )
            lines.append(dumps_bytes(record))
        return (b"\n".join(lines) + (b"\n" if lines else b""), len(lines))
    validate_instance(value, schema_name, schema_fragment=schema_fragment)
    record_count = 1
    if name == "source-mounts.json" and isinstance(value, dict):
        mounts = value.get("source_mounts")
        record_count = len(mounts) if isinstance(mounts, list) else 0
    return dumps_bytes(value) + b"\n", record_count


def _validate_semantics(contents: PackageContents) -> None:
    manifest = contents.manifest
    summary = contents.summary
    if manifest.get("status") != "COMPLETED" or summary.get("status") != "COMPLETED":
        raise OutputError("PACKAGE_STATUS_NOT_COMPLETED")
    count_names = (
        "total_files",
        "accepted_files",
        "excluded_files",
        "quarantined_files",
        "duplicate_files",
        "needs_review_files",
        "failed_files",
        "pruned_directories",
        "issue_count",
    )
    for name in count_names:
        if manifest.get(name) != summary.get(name):
            raise OutputError(f"OUTPUT_COUNT_MISMATCH: {name}")
    total = manifest.get("total_files")
    dispositions = sum(
        int(manifest.get(name, -1))
        for name in (
            "accepted_files",
            "excluded_files",
            "quarantined_files",
            "duplicate_files",
            "needs_review_files",
        )
    )
    if total != dispositions:
        raise OutputError("OUTPUT_COUNT_MISMATCH: disposition equation")
    if len(contents.artifacts) != int(manifest.get("accepted_files", -1)) + int(
        manifest.get("needs_review_files", -1)
    ):
        raise OutputError("OUTPUT_COUNT_MISMATCH: artifacts.jsonl")
    if len(contents.excluded_items) != sum(
        int(manifest.get(name, -1))
        for name in ("excluded_files", "quarantined_files", "duplicate_files")
    ):
        raise OutputError("OUTPUT_COUNT_MISMATCH: excluded-items.jsonl")
    if len(contents.ingest_issues) != int(manifest.get("issue_count", -1)):
        raise OutputError("OUTPUT_COUNT_MISMATCH: ingest-issues.jsonl")
