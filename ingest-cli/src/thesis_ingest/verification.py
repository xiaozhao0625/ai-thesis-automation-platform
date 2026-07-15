from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from thesis_ingest.canonical_json import CanonicalJsonError, loads_strict
from thesis_ingest.contracts import ContractError, validate_instance
from thesis_ingest.output import OUTPUT_ROUTES
from thesis_ingest.paths import calculate_root_fingerprint

class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerificationReport:
    status: str
    file_count: int
    record_counts: dict[str, int]


def verify_package(output_path: Path) -> VerificationReport:
    root = output_path.resolve()
    if root.is_file():
        if root.name != "ingest-manifest.json":
            raise VerificationError("MANIFEST_PATH_INVALID")
        root = root.parent
    manifest_path = root / "ingest-manifest.json"
    try:
        manifest = loads_strict(manifest_path.read_bytes())
    except (OSError, CanonicalJsonError) as exc:
        raise VerificationError(f"STRICT_JSON_INVALID: ingest-manifest.json: {exc}") from exc
    if not isinstance(manifest, dict):
        raise VerificationError("STRICT_JSON_INVALID: manifest root")
    if manifest.get("status") != "COMPLETED":
        raise VerificationError("MANIFEST_NOT_COMPLETED")
    try:
        validate_instance(manifest, "ingest-manifest.schema.json")
    except ContractError as exc:
        raise VerificationError(f"SCHEMA_VALIDATION_FAILED: {exc}") from exc

    expected_names = {"ingest-manifest.json"} | {
        route[0] for route in OUTPUT_ROUTES
    }
    actual_names = {path.name for path in root.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise VerificationError(
            f"OUTPUT_FILE_SET_MISMATCH: expected {sorted(expected_names)}, got {sorted(actual_names)}"
        )
    descriptors = manifest.get("output_hashes")
    if not isinstance(descriptors, list):
        raise VerificationError("OUTPUT_HASHES_INVALID")
    descriptor_by_name = {
        descriptor.get("relative_path"): descriptor
        for descriptor in descriptors
        if isinstance(descriptor, dict)
    }
    record_counts: dict[str, int] = {}
    parsed: dict[str, object] = {}
    for name, _attribute, schema_name, fragment in OUTPUT_ROUTES:
        descriptor = descriptor_by_name.get(name)
        if not isinstance(descriptor, dict):
            raise VerificationError(f"OUTPUT_DESCRIPTOR_MISSING: {name}")
        payload = (root / name).read_bytes()
        content_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
        if (
            descriptor.get("content_hash") != content_hash
            or descriptor.get("size_bytes") != len(payload)
        ):
            raise VerificationError(f"OUTPUT_HASH_MISMATCH: {name}")
        try:
            value, count = _parse_output(name, payload)
            schema_fragment = None if fragment == "#" else fragment
            if isinstance(value, list) and name.endswith(".jsonl"):
                for record in value:
                    validate_instance(
                        record,
                        schema_name,
                        schema_fragment=schema_fragment,
                    )
            else:
                validate_instance(
                    value,
                    schema_name,
                    schema_fragment=schema_fragment,
                )
        except CanonicalJsonError as exc:
            raise VerificationError(f"STRICT_JSON_INVALID: {name}: {exc}") from exc
        except ContractError as exc:
            raise VerificationError(f"SCHEMA_VALIDATION_FAILED: {name}: {exc}") from exc
        if descriptor.get("record_count") != count:
            raise VerificationError(f"OUTPUT_COUNT_MISMATCH: {name}")
        parsed[name] = value
        record_counts[name] = count
    _verify_semantics(manifest, parsed, record_counts)
    return VerificationReport(
        status="COMPLETED",
        file_count=len(expected_names),
        record_counts=record_counts,
    )


def _parse_output(name: str, payload: bytes) -> tuple[object, int]:
    if not name.endswith(".jsonl"):
        value = loads_strict(payload)
        count = (
            len(value.get("source_mounts", []))
            if name == "source-mounts.json" and isinstance(value, dict)
            else 1
        )
        return value, count
    if not payload:
        return [], 0
    if not payload.endswith(b"\n"):
        raise CanonicalJsonError("truncated JSONL line: missing LF terminator")
    raw_lines = payload[:-1].split(b"\n")
    if any(not line for line in raw_lines):
        raise CanonicalJsonError("empty JSONL line")
    records = [loads_strict(line) for line in raw_lines]
    return records, len(records)


def _verify_semantics(
    manifest: dict[str, object],
    parsed: dict[str, object],
    record_counts: dict[str, int],
) -> None:
    total = manifest["total_files"]
    disposition_total = sum(
        int(manifest[name])
        for name in (
            "accepted_files",
            "excluded_files",
            "quarantined_files",
            "duplicate_files",
            "needs_review_files",
        )
    )
    if total != disposition_total:
        raise VerificationError("OUTPUT_COUNT_MISMATCH: disposition equation")
    if record_counts["artifacts.jsonl"] != int(manifest["accepted_files"]) + int(
        manifest["needs_review_files"]
    ):
        raise VerificationError("OUTPUT_COUNT_MISMATCH: artifacts.jsonl")
    if record_counts["excluded-items.jsonl"] != sum(
        int(manifest[name])
        for name in ("excluded_files", "quarantined_files", "duplicate_files")
    ):
        raise VerificationError("OUTPUT_COUNT_MISMATCH: excluded-items.jsonl")
    summary = parsed["summary.json"]
    if not isinstance(summary, dict):
        raise VerificationError("SUMMARY_INVALID")
    for name in (
        "status",
        "total_files",
        "accepted_files",
        "excluded_files",
        "quarantined_files",
        "duplicate_files",
        "needs_review_files",
        "failed_files",
        "pruned_directories",
        "issue_count",
    ):
        if summary.get(name) != manifest.get(name):
            raise VerificationError(f"OUTPUT_COUNT_MISMATCH: summary {name}")
    _verify_references_and_fingerprint(manifest, parsed)


def _verify_references_and_fingerprint(
    manifest: dict[str, object],
    parsed: dict[str, object],
) -> None:
    artifacts = _record_list(parsed, "artifacts.jsonl")
    excluded = _record_list(parsed, "excluded-items.jsonl")
    records = [*artifacts, *excluded]
    record_ids = {str(record["ingest_record_id"]) for record in records}
    if len(record_ids) != len(records):
        raise VerificationError("RECORD_REFERENCE_MISSING: duplicate ingest_record_id")
    issue_records = _record_list(parsed, "ingest-issues.jsonl")
    issue_ids = {str(issue["issue_id"]) for issue in issue_records}
    reference_records = _record_list(parsed, "reference-candidates.jsonl")
    reference_ids = {
        str(reference["reference_candidate_id"]) for reference in reference_records
    }

    for record in records:
        _require_refs(record.get("issue_refs", []), issue_ids, "artifact issue")
        if record.get("scan_id") != manifest.get("scan_id"):
            raise VerificationError("RECORD_REFERENCE_MISSING: artifact scan_id")
        if record.get("source_mount_id") != manifest.get("source_mount_id"):
            raise VerificationError("RECORD_REFERENCE_MISSING: source_mount_id")

    for group in _record_list(parsed, "duplicate-groups.jsonl"):
        _require_refs(
            group.get("member_ingest_record_ids", []),
            record_ids,
            "duplicate member",
        )
        canonical = group.get("canonical_ingest_record_id")
        if canonical is not None:
            _require_refs([canonical], record_ids, "duplicate canonical")

    for candidate in _record_list(parsed, "primary-candidates.jsonl"):
        _require_refs(
            candidate.get("candidate_ingest_record_ids", []),
            record_ids,
            "primary candidate",
        )
        for key in ("recommended_ingest_record_id",):
            if candidate.get(key) is not None:
                _require_refs([candidate[key]], record_ids, key)
        _require_refs(
            candidate.get("tied_ingest_record_ids", []),
            record_ids,
            "tied candidates",
        )
        _require_refs(candidate.get("issue_refs", []), issue_ids, "candidate issue")

    for reference in reference_records:
        _require_refs(
            [reference.get("source_ingest_record_id")],
            record_ids,
            "reference source",
        )
        duplicate_of = reference.get("duplicate_of")
        if duplicate_of is not None:
            _require_refs([duplicate_of], reference_ids, "reference duplicate")
        _require_refs(reference.get("issue_refs", []), issue_ids, "reference issue")

    for sensitive in _record_list(parsed, "sensitive-items.jsonl"):
        _require_refs(
            [sensitive.get("ingest_record_id")],
            record_ids,
            "sensitive item",
        )
        _require_refs(sensitive.get("issue_refs", []), issue_ids, "sensitive issue")

    calculated = calculate_root_fingerprint(records)
    if calculated != manifest.get("root_fingerprint"):
        raise VerificationError("OUTPUT_HASH_MISMATCH: root_fingerprint")


def _record_list(
    parsed: dict[str, object], name: str
) -> list[dict[str, object]]:
    value = parsed.get(name)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise VerificationError(f"STRICT_JSON_INVALID: {name}")
    return value


def _require_refs(values: object, known: set[str], label: str) -> None:
    if not isinstance(values, list):
        raise VerificationError(f"RECORD_REFERENCE_MISSING: {label}")
    for value in values:
        if not isinstance(value, str) or value not in known:
            raise VerificationError(
                f"RECORD_REFERENCE_MISSING: {label}: {value}"
            )
