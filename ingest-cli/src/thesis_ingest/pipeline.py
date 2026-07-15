from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import mimetypes
from pathlib import Path
from pathlib import PurePosixPath
import re
import uuid

from thesis_ingest.candidates import (
    CandidateArtifact,
    CandidateSelection,
    EngineeringRoot,
    evaluate_engineering_roots,
    evaluate_primary_documents,
)
from thesis_ingest.canonical_json import CanonicalJsonError, dumps_bytes, loads_strict
from thesis_ingest.checkpoint import (
    CheckpointError,
    CheckpointState,
    SourceSnapshot,
    load_checkpoint,
    save_checkpoint,
)
from thesis_ingest.classification import classify_artifact
from thesis_ingest.config import ConfigError, IngestConfig, load_config
from thesis_ingest.deduplication import DedupRecord, deduplicate
from thesis_ingest.discovery import DiscoveredItem, discover_files
from thesis_ingest.hashing import FileChangedDuringHash, HashingError, hash_file
from thesis_ingest.issues import make_issue
from thesis_ingest.output import OutputError, PackageContents, publish_package
from thesis_ingest.paths import (
    PathPolicy,
    calculate_root_fingerprint,
    make_ingest_record_id,
    make_source_occurrence_key,
)
from thesis_ingest.preflight import PreflightInput, evaluate_preflight
from thesis_ingest.references import extract_reference_candidates
from thesis_ingest.sensitivity import SensitivitySuggestion, classify_sensitivity

class PipelineError(RuntimeError):
    exit_code = 10


class ScanInterrupted(PipelineError):
    exit_code = 4


@dataclass(frozen=True)
class ScanResult:
    output_path: Path
    status: str
    resumed_from_checkpoint: bool


def run_scan(
    config_path: Path,
    *,
    cli_output: str | Path | None = None,
    scan_id: str | None = None,
    fail_after_records: int | None = None,
) -> ScanResult:
    config = load_config(config_path, cli_output=cli_output)
    raw = config.raw
    source_mount = _mapping(raw, "source_mount")
    source_mount_id = _string(source_mount, "source_mount_id")
    config_hash = _sha256(dumps_bytes(raw))
    policy = PathPolicy(
        case_policy=_string(source_mount, "case_policy"),
        unicode_normalization=_string(source_mount, "unicode_normalization"),
        version=_string(source_mount, "path_normalization_version"),
    )
    if scan_id is None:
        scan_id = _find_compatible_scan_id(
            config.output_path,
            config_hash=config_hash,
            rule_set_version=_string(raw, "rule_set_version"),
            path_normalization_version=policy.version,
        ) or _new_scan_id()
    path_rules = _mapping(raw, "path_rules")
    output_options = _mapping(raw, "output")
    excluded_directories = set(_string_list(path_rules, "exclude_directories"))
    discovery = discover_files(
        config.root_path,
        policy,
        excluded_directories=excluded_directories,
        emit_excluded_item_records=bool(
            output_options.get("emit_excluded_item_records", False)
        ),
    )
    staging_root = (
        config.output_path.parent
        / f".{config.output_path.name}.staging"
        / scan_id
    )
    checkpoint_path = staging_root / "checkpoint.json"
    resumed = checkpoint_path.exists()
    checkpoint_id: str | None = None
    if resumed:
        try:
            restored = load_checkpoint(
                checkpoint_path,
                expected_scan_id=scan_id,
                expected_config_hash=config_hash,
                expected_rule_set_version=_string(raw, "rule_set_version"),
                expected_path_normalization_version=policy.version,
                source_root=config.root_path,
            )
        except CheckpointError as exc:
            if "SOURCE" in str(exc):
                raise PipelineError(f"SOURCE_MUTATED_DURING_SCAN: {exc}") from exc
            raise PipelineError(f"CHECKPOINT_INCOMPATIBLE: {exc}") from exc
        checkpoint_id = restored.checkpoint_id
        next_index = restored.next_index
        records = _dict_list(restored.payload.get("records", []))
        issues = _dict_list(restored.payload.get("issues", []))
        started_at = str(restored.payload.get("started_at"))
        snapshots = list(restored.source_snapshots)
        if next_index != len(records) or next_index != len(snapshots):
            raise PipelineError(
                "CHECKPOINT_INCOMPATIBLE: cursor, records, and snapshots differ"
            )
        discovered_prefix = tuple(
            item.relative_path for item in discovery.items[:next_index]
        )
        checkpoint_prefix = tuple(
            snapshot.relative_path for snapshot in restored.source_snapshots
        )
        if discovered_prefix != checkpoint_prefix:
            raise PipelineError(
                "SOURCE_MUTATED_DURING_SCAN: discovery order changed before cursor"
            )
    else:
        next_index = 0
        records: list[dict[str, object]] = []
        issues: list[dict[str, object]] = []
        started_at = _now()
        snapshots: list[SourceSnapshot] = []

    if next_index > len(discovery.items):
        raise PipelineError("CHECKPOINT_INCOMPATIBLE: cursor exceeds discovery size")
    checkpoint_every = int(output_options.get("checkpoint_every_records", 1))
    for index in range(next_index, len(discovery.items)):
        item = discovery.items[index]
        record, record_issues, snapshot = _process_item(
            item,
            config=config,
            scan_id=scan_id,
            observed_at=_now(),
        )
        records.append(record)
        issues.extend(record_issues)
        snapshots.append(snapshot)
        next_index = index + 1
        if next_index % checkpoint_every == 0:
            checkpoint_id = _save_pipeline_checkpoint(
                checkpoint_path,
                scan_id=scan_id,
                config_hash=config_hash,
                config=config,
                next_index=next_index,
                records=records,
                issues=issues,
                snapshots=snapshots,
                started_at=started_at,
            )
        if fail_after_records is not None and next_index >= fail_after_records:
            if next_index % checkpoint_every != 0:
                checkpoint_id = _save_pipeline_checkpoint(
                    checkpoint_path,
                    scan_id=scan_id,
                    config_hash=config_hash,
                    config=config,
                    next_index=next_index,
                    records=records,
                    issues=issues,
                    snapshots=snapshots,
                    started_at=started_at,
                )
            raise ScanInterrupted(
                f"SCAN_INTERRUPTED_AFTER_RECORDS: {next_index}; checkpoint={checkpoint_id}"
            )
    if next_index == len(discovery.items):
        checkpoint_id = _save_pipeline_checkpoint(
            checkpoint_path,
            scan_id=scan_id,
            config_hash=config_hash,
            config=config,
            next_index=next_index,
            records=records,
            issues=issues,
            snapshots=snapshots,
            started_at=started_at,
        )

    finalized_records, duplicate_groups = _apply_deduplication(records, scan_id)
    created_at = _now()
    primary_candidates, candidate_issues = _build_primary_candidates(
        finalized_records,
        raw=raw,
        scan_id=scan_id,
        created_at=created_at,
        config=config,
    )
    issues.extend(candidate_issues)
    reference_candidates, reference_issues = _build_reference_candidates(
        finalized_records,
        discovery.items,
        scan_id=scan_id,
        created_at=created_at,
    )
    issues.extend(reference_issues)
    issues.extend(
        make_issue(
            scan_id=scan_id,
            stage="PATH",
            error_code="PATH_LINK_SKIPPED",
            severity="INFO",
            recoverable=True,
            message=f"Link skipped by policy: {relative_path}",
            recommended_action="Review the link target manually if it is required.",
            created_at=created_at,
            relative_path=relative_path,
        )
        for relative_path in discovery.skipped_links
    )
    issues = _unique_records(issues, "issue_id")
    sensitive_items = _build_sensitive_items(
        finalized_records, scan_id=scan_id, created_at=created_at
    )
    artifacts = [
        record
        for record in finalized_records
        if record["ingest_decision"] in {"ACCEPTED", "NEEDS_REVIEW"}
    ]
    excluded_items = [
        record
        for record in finalized_records
        if record["ingest_decision"] in {"EXCLUDED", "QUARANTINED", "DUPLICATE"}
    ]
    finished_at = _now()
    counts = Counter(str(record["ingest_decision"]) for record in finalized_records)
    failed_files = sum(
        record["hash_status"] == "FAILED" for record in finalized_records
    )
    root_fingerprint = calculate_root_fingerprint(finalized_records)
    resume_info = {
        "resumed_from_checkpoint": resumed,
        "checkpoint_id": checkpoint_id if resumed else None,
        "checkpoint_count": 1 if resumed else 0,
    }
    count_fields = {
        "total_files": len(finalized_records),
        "accepted_files": counts["ACCEPTED"],
        "excluded_files": counts["EXCLUDED"],
        "quarantined_files": counts["QUARANTINED"],
        "duplicate_files": counts["DUPLICATE"],
        "needs_review_files": counts["NEEDS_REVIEW"],
        "failed_files": failed_files,
        "pruned_directories": len(discovery.pruned_directories),
        "issue_count": len(issues),
    }
    manifest: dict[str, object] = {
        "manifest_version": "0.1",
        "record_type": "INGEST_MANIFEST",
        "scan_id": scan_id,
        "status": "COMPLETED",
        "source_mount_id": source_mount_id,
        "binding_revision": int(source_mount["binding_revision"]),
        "config_version": _string(raw, "config_version"),
        "config_hash": config_hash,
        "path_normalization_version": policy.version,
        "rule_set_version": _string(raw, "rule_set_version"),
        "scanner_version": _string(raw, "scanner_version"),
        "root_fingerprint": root_fingerprint,
        "started_at": started_at,
        "finished_at": finished_at,
        **count_fields,
        "resume_info": resume_info,
    }
    summary = _build_summary(
        finalized_records,
        issues=issues,
        duplicate_groups=duplicate_groups,
        primary_candidates=primary_candidates,
        reference_candidates=reference_candidates,
        sensitive_items=sensitive_items,
        scan_id=scan_id,
        source_mount_id=source_mount_id,
        started_at=started_at,
        finished_at=finished_at,
        resumed=resumed,
        count_fields=count_fields,
    )
    mount_snapshot = copy.deepcopy(source_mount)
    mount_snapshot["last_scan_id"] = scan_id
    mount_snapshot["last_scan_at"] = finished_at
    mount_snapshot["root_fingerprint"] = root_fingerprint
    package = PackageContents(
        manifest=manifest,
        source_mounts={
            "schema_version": "0.1",
            "record_type": "SOURCE_MOUNT_COLLECTION",
            "source_mounts": [mount_snapshot],
        },
        artifacts=artifacts,
        excluded_items=excluded_items,
        duplicate_groups=duplicate_groups,
        primary_candidates=primary_candidates,
        reference_candidates=reference_candidates,
        sensitive_items=sensitive_items,
        ingest_issues=issues,
        summary=summary,
    )
    try:
        published = publish_package(config.output_path, package)
    except OutputError as exc:
        raise PipelineError(str(exc)) from exc
    return ScanResult(
        output_path=published,
        status="COMPLETED",
        resumed_from_checkpoint=resumed,
    )


def _process_item(
    item: DiscoveredItem,
    *,
    config: IngestConfig,
    scan_id: str,
    observed_at: str,
) -> tuple[dict[str, object], list[dict[str, object]], SourceSnapshot]:
    raw = config.raw
    source_mount = _mapping(raw, "source_mount")
    preliminary = classify_artifact(item.relative_path, "ACCEPTED", config.rule_bundle)
    preflight = evaluate_preflight(
        PreflightInput(
            physical_path=item.physical_path,
            relative_path=item.relative_path,
            discovery_excluded=item.discovery_excluded,
            path_collision=item.path_collision,
        ),
        config.rule_bundle,
        classification_confidence=preliminary.classification_confidence,
    )
    classification = classify_artifact(
        item.relative_path, preflight.decision, config.rule_bundle
    )
    sensitivity = _sensitivity_for_item(item, classification.artifact_role)
    ingest_record_id = make_ingest_record_id(
        scan_id,
        _string(source_mount, "source_mount_id"),
        item.observed_relative_path,
    )
    record_issues: list[dict[str, object]] = []
    hash_status = "SKIPPED_BY_POLICY" if item.discovery_excluded else "COMPUTED"
    content_hash: str | None = None
    source_occurrence_key: str | None = None
    decision = preflight.decision
    parser_eligible = preflight.parser_eligible
    requires_review = preflight.requires_review
    reason_codes = list(preflight.reason_codes)
    rule_matches = list(preflight.rule_matches)
    if not item.discovery_excluded:
        try:
            hash_result = hash_file(item.physical_path)
            content_hash = hash_result.content_hash
            source_occurrence_key = make_source_occurrence_key(
                _string(source_mount, "source_mount_id"),
                item.relative_path,
                content_hash,
            )
        except (FileChangedDuringHash, HashingError) as exc:
            hash_status = "FAILED"
            decision = (
                "QUARANTINED"
                if preflight.decision == "QUARANTINED"
                else "NEEDS_REVIEW"
            )
            parser_eligible = False
            requires_review = True
            error_code = (
                "FILE_CHANGED_DURING_SCAN"
                if isinstance(exc, FileChangedDuringHash)
                else "HASH_FAILED"
            )
            reason_codes.append(error_code)
            issue = make_issue(
                scan_id=scan_id,
                ingest_record_id=ingest_record_id,
                relative_path=item.relative_path,
                stage="HASH",
                error_code=error_code,
                severity="ERROR",
                recoverable=True,
                message=f"Hash could not be finalized for {item.relative_path}.",
                recommended_action="Stabilize the source file and resume the scan.",
                created_at=observed_at,
            )
            record_issues.append(issue)
            rule_matches.append(
                {
                    "rule_id": "hash-stability-check",
                    "signal_type": "HASH",
                    "reason_code": error_code,
                    "redacted_summary": "hash stability check failed",
                }
            )
    issue_for_decision = _decision_issue(
        scan_id=scan_id,
        ingest_record_id=ingest_record_id,
        relative_path=item.relative_path,
        reason_codes=reason_codes,
        created_at=observed_at,
    )
    if issue_for_decision is not None:
        record_issues.append(issue_for_decision)
    extension = _normalized_extension(item.relative_path)
    media_type = mimetypes.guess_type(item.relative_path)[0]
    record: dict[str, object] = {
        "schema_version": "0.1",
        "record_type": "ARTIFACT_INGEST_RECORD",
        "ingest_record_id": ingest_record_id,
        "scan_id": scan_id,
        "source_mount_id": _string(source_mount, "source_mount_id"),
        "binding_revision": int(source_mount["binding_revision"]),
        "observed_relative_path": item.observed_relative_path,
        "relative_path": item.relative_path,
        "path_key": item.path_key,
        "hash_status": hash_status,
        "size_bytes": item.size_bytes,
        "modified_at": _time_from_ns(item.modified_time_ns),
        "media_type": media_type.lower() if media_type else None,
        "extension": extension,
        "pre_dedup_decision": decision,
        "pre_dedup_parser_eligible": parser_eligible,
        "ingest_decision": decision,
        "decision_reason_codes": list(dict.fromkeys(reason_codes)),
        "decision_rule_matches": rule_matches,
        "requires_review": requires_review,
        "parser_eligible": parser_eligible,
        "artifact_role": classification.artifact_role,
        "classification_status": classification.classification_status,
        "classification_authority": classification.classification_authority,
        "classification_confidence": classification.classification_confidence,
        "classification_method": classification.classification_method,
        "classification_reasons": list(classification.classification_reasons),
        "data_classification": sensitivity.data_classification,
        "content_categories": list(sensitivity.content_categories),
        "access_recommendation": sensitivity.access_recommendation,
        "model_usage_restriction": sensitivity.model_usage_restriction,
        "sensitivity_confidence": sensitivity.sensitivity_confidence,
        "sensitivity_reasons": list(sensitivity.sensitivity_reasons),
        "rule_set_version": _string(raw, "rule_set_version"),
        "scanner_version": _string(raw, "scanner_version"),
        "observed_at": observed_at,
        "issue_refs": [issue["issue_id"] for issue in record_issues],
    }
    if content_hash is not None and source_occurrence_key is not None:
        record["content_hash"] = content_hash
        record["source_occurrence_key"] = source_occurrence_key
    snapshot = SourceSnapshot(
        relative_path=item.relative_path,
        size_bytes=item.size_bytes,
        modified_time_ns=item.modified_time_ns,
        content_hash=content_hash,
    )
    return record, record_issues, snapshot


def _sensitivity_for_item(
    item: DiscoveredItem, artifact_role: str
) -> SensitivitySuggestion:
    sample_text: str | None = None
    if item.physical_path.suffix.casefold() in {
        ".csv",
        ".json",
        ".md",
        ".txt",
    } and item.size_bytes <= 1024 * 1024:
        try:
            sample_text = item.physical_path.read_text("utf-8", errors="replace")[:8192]
        except OSError:
            sample_text = None
    return classify_sensitivity(
        item.relative_path,
        artifact_role,
        sample_text=sample_text,
    )


def _decision_issue(
    *,
    scan_id: str,
    ingest_record_id: str,
    relative_path: str,
    reason_codes: list[str],
    created_at: str,
) -> dict[str, object] | None:
    mapping = {
        "PATH_NORMALIZATION_COLLISION": (
            "PATH",
            "PATH_NORMALIZATION_COLLISION",
            "ERROR",
        ),
        "LOW_CLASSIFICATION_CONFIDENCE": (
            "CLASSIFICATION",
            "CLASSIFICATION_AMBIGUOUS",
            "WARNING",
        ),
        "CREDENTIAL_RISK": (
            "PRECHECK",
            "CREDENTIAL_RISK_DETECTED",
            "ERROR",
        ),
        "UNKNOWN_BINARY": ("PRECHECK", "SUSPICIOUS_BINARY", "ERROR"),
        "SUSPICIOUS_ARCHIVE": ("PRECHECK", "ARCHIVE_UNREADABLE", "ERROR"),
    }
    for reason in reason_codes:
        if reason in mapping:
            stage, error_code, severity = mapping[reason]
            return make_issue(
                scan_id=scan_id,
                ingest_record_id=ingest_record_id,
                relative_path=relative_path,
                stage=stage,
                error_code=error_code,
                severity=severity,
                recoverable=True,
                message=f"Governance review required for {relative_path}.",
                recommended_action="Review the recorded rule match before admission.",
                created_at=created_at,
            )
    return None


def _apply_deduplication(
    records: list[dict[str, object]], scan_id: str
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    result = deduplicate(
        [
            DedupRecord(
                ingest_record_id=str(record["ingest_record_id"]),
                content_hash=(
                    str(record["content_hash"])
                    if isinstance(record.get("content_hash"), str)
                    else None
                ),
                path_key=str(record["path_key"]),
                pre_dedup_decision=str(record["pre_dedup_decision"]),
                pre_dedup_parser_eligible=bool(
                    record["pre_dedup_parser_eligible"]
                ),
                artifact_role=str(record["artifact_role"]),
            )
            for record in records
        ],
        scan_id=scan_id,
    )
    updates = {record.ingest_record_id: record for record in result.records}
    finalized: list[dict[str, object]] = []
    for original in records:
        record = dict(original)
        update = updates[str(record["ingest_record_id"])]
        record["ingest_decision"] = update.ingest_decision
        record["parser_eligible"] = update.parser_eligible
        if update.duplicate_group_id is not None:
            record["duplicate_group_id"] = update.duplicate_group_id
            record["decision_reason_codes"] = list(
                dict.fromkeys(
                    [*record["decision_reason_codes"], "CONTENT_HASH_DUPLICATE"]
                )
            )
            record["decision_rule_matches"] = [
                *record["decision_rule_matches"],
                {
                    "rule_id": "sha256-exact-duplicate",
                    "signal_type": "HASH",
                    "reason_code": "CONTENT_HASH_DUPLICATE",
                    "redacted_summary": "exact sha256 duplicate",
                },
            ]
        finalized.append(record)
    return finalized, [group.as_dict() for group in result.groups]


def _build_primary_candidates(
    records: list[dict[str, object]],
    *,
    raw: dict[str, object],
    scan_id: str,
    created_at: str,
    config: IngestConfig,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    scopes_raw = raw.get("project_scopes")
    scopes = scopes_raw if isinstance(scopes_raw, list) and scopes_raw else [
        {"scope_id": "root", "relative_path_prefix": ""}
    ]
    candidates: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        scope_id = str(scope["scope_id"])
        prefix = str(scope.get("relative_path_prefix", "")).strip("/")
        scoped = [
            record
            for record in records
            if not prefix
            or str(record["relative_path"]) == prefix
            or str(record["relative_path"]).startswith(prefix + "/")
        ]
        artifacts = [
            CandidateArtifact(
                ingest_record_id=str(record["ingest_record_id"]),
                relative_path=str(record["relative_path"]),
                content_hash=str(record["content_hash"]),
                modified_at=(
                    str(record["modified_at"])
                    if isinstance(record.get("modified_at"), str)
                    else None
                ),
                artifact_role=str(record["artifact_role"]),
                ingest_decision=str(record["ingest_decision"]),
                parser_eligible=bool(record["parser_eligible"]),
                word_count=None,
                page_count=None,
                in_project_scope=True,
            )
            for record in scoped
            if isinstance(record.get("content_hash"), str)
        ]
        document_selection = evaluate_primary_documents(
            artifacts,
            scan_id=scan_id,
            scope_id=scope_id,
            created_at=created_at,
            rules=config.rule_bundle,
        )
        _append_selection(
            document_selection,
            selection_type="PRIMARY_DOCUMENT",
            scan_id=scan_id,
            created_at=created_at,
            candidates=candidates,
            issues=issues,
        )
        engineering_records = [
            record
            for record in scoped
            if record["ingest_decision"] == "ACCEPTED"
            and record["parser_eligible"] is True
            and record["artifact_role"]
            in {"ENGINEERING_SOURCE", "ENGINEERING_CONFIG"}
            and isinstance(record.get("content_hash"), str)
        ]
        roots: list[EngineeringRoot] = []
        if engineering_records:
            anchor_priority = _mapping(
                config.rule_bundle.documents["candidate-scoring.json"],
                "engineering_root",
            )["anchor_priority"]
            representative = min(
                engineering_records,
                key=lambda record: (
                    _anchor_rank(
                        PurePosixPath(str(record["relative_path"])).name,
                        anchor_priority,
                    ),
                    str(record["path_key"]).encode("utf-8"),
                ),
            )
            file_names = {
                _relative_to_scope(str(record["relative_path"]), prefix)
                for record in scoped
                if record["ingest_decision"] == "ACCEPTED"
                and record["parser_eligible"] is True
            }
            roots.append(
                EngineeringRoot(
                    root_path=prefix or ".",
                    representative_ingest_record_id=str(
                        representative["ingest_record_id"]
                    ),
                    representative_content_hash=str(representative["content_hash"]),
                    representative_modified_at=(
                        str(representative["modified_at"])
                        if isinstance(representative.get("modified_at"), str)
                        else None
                    ),
                    file_names=file_names,
                )
            )
        engineering_selection = evaluate_engineering_roots(
            roots,
            scan_id=scan_id,
            scope_id=scope_id,
            created_at=created_at,
            rules=config.rule_bundle,
        )
        _append_selection(
            engineering_selection,
            selection_type="PRIMARY_ENGINEERING_ROOT",
            scan_id=scan_id,
            created_at=created_at,
            candidates=candidates,
            issues=issues,
        )
    return candidates, _unique_records(issues, "issue_id")


def _append_selection(
    selection: CandidateSelection,
    *,
    selection_type: str,
    scan_id: str,
    created_at: str,
    candidates: list[dict[str, object]],
    issues: list[dict[str, object]],
) -> None:
    if selection.record is not None:
        candidates.append(selection.record)
    for issue in selection.issue_records:
        error_code = str(issue["code"])
        issues.append(
            make_issue(
                scan_id=scan_id,
                stage="CANDIDATE",
                error_code=error_code,
                severity="WARNING",
                recoverable=True,
                message=f"{selection_type} requires human confirmation.",
                recommended_action="Review the candidate scores and select manually.",
                created_at=created_at,
                issue_id=str(issue["issue_id"]),
            )
        )


def _build_reference_candidates(
    records: list[dict[str, object]],
    discovered: list[DiscoveredItem],
    *,
    scan_id: str,
    created_at: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    physical_by_path = {item.relative_path: item.physical_path for item in discovered}
    candidates: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    for record in records:
        if (
            record["artifact_role"] != "REFERENCE_CANDIDATE"
            or record["ingest_decision"] != "ACCEPTED"
            or record["parser_eligible"] is not True
        ):
            continue
        extension = str(record["extension"])
        if extension not in {".md", ".txt"}:
            continue
        try:
            text = physical_by_path[str(record["relative_path"])].read_text(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        extracted = extract_reference_candidates(
            text,
            source_ingest_record_id=str(record["ingest_record_id"]),
            scan_id=scan_id,
            created_at=created_at,
        )
        for candidate in extracted:
            for issue_id in candidate["issue_refs"]:
                issues.append(
                    make_issue(
                        scan_id=scan_id,
                        stage="CLASSIFICATION",
                        error_code="REFERENCE_PARSE_FAILED",
                        severity="WARNING",
                        recoverable=True,
                        message="Reference clue could not be parsed into structured fields.",
                        recommended_action="Verify and complete the reference manually.",
                        created_at=created_at,
                        ingest_record_id=str(record["ingest_record_id"]),
                        relative_path=str(record["relative_path"]),
                        issue_id=str(issue_id),
                    )
                )
        candidates.extend(extracted)
    return candidates, _unique_records(issues, "issue_id")


def _build_sensitive_items(
    records: list[dict[str, object]],
    *,
    scan_id: str,
    created_at: str,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for record in records:
        categories = record["content_categories"]
        if not isinstance(categories, list) or not categories:
            continue
        ingest_record_id = str(record["ingest_record_id"])
        item_id = _sha256(
            dumps_bytes(
                {
                    "ingest_record_id": ingest_record_id,
                    "record_type": "SENSITIVE_ITEM",
                    "scan_id": scan_id,
                }
            )
        )
        items.append(
            {
                "schema_version": "0.1",
                "record_type": "SENSITIVE_ITEM",
                "sensitive_item_id": item_id,
                "scan_id": scan_id,
                "ingest_record_id": ingest_record_id,
                "data_classification": record["data_classification"],
                "content_categories": categories,
                "access_recommendation": record["access_recommendation"],
                "model_usage_restriction": record["model_usage_restriction"],
                "sensitivity_confidence": record["sensitivity_confidence"],
                "sensitivity_reasons": record["sensitivity_reasons"],
                "requires_review": record["data_classification"]
                in {"SENSITIVE", "RESTRICTED"},
                "issue_refs": [],
                "created_at": created_at,
            }
        )
    return items


def _build_summary(
    records: list[dict[str, object]],
    *,
    issues: list[dict[str, object]],
    duplicate_groups: list[dict[str, object]],
    primary_candidates: list[dict[str, object]],
    reference_candidates: list[dict[str, object]],
    sensitive_items: list[dict[str, object]],
    scan_id: str,
    source_mount_id: str,
    started_at: str,
    finished_at: str,
    resumed: bool,
    count_fields: dict[str, int],
) -> dict[str, object]:
    role_counts = Counter(str(record["artifact_role"]) for record in records)
    media_counts = Counter(
        _media_code(record.get("media_type"), record.get("extension"))
        for record in records
    )
    classification_counts = Counter(
        str(record["data_classification"]) for record in records
    )
    severity_counts = Counter(str(issue["severity"]) for issue in issues)
    duration = max(
        0,
        int(
            (
                datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                - datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            ).total_seconds()
            * 1000
        ),
    )
    return {
        "summary_version": "0.1",
        "scan_id": scan_id,
        "source_mount_id": source_mount_id,
        "status": "COMPLETED",
        **count_fields,
        "by_artifact_role": dict(sorted(role_counts.items())),
        "by_media_type": dict(sorted(media_counts.items())),
        "by_data_classification": dict(sorted(classification_counts.items())),
        "by_issue_severity": dict(sorted(severity_counts.items())),
        "duration_ms": duration,
        "resumed_from_checkpoint": resumed,
        "checkpoint_count": 1 if resumed else 0,
        "unread_files": count_fields["failed_files"],
        "unhashed_files": sum(
            record["hash_status"] != "COMPUTED" for record in records
        ),
        "duplicate_group_count": len(duplicate_groups),
        "primary_candidate_count": len(primary_candidates),
        "reference_candidate_count": len(reference_candidates),
        "sensitive_item_count": len(sensitive_items),
    }


def _save_pipeline_checkpoint(
    path: Path,
    *,
    scan_id: str,
    config_hash: str,
    config: IngestConfig,
    next_index: int,
    records: list[dict[str, object]],
    issues: list[dict[str, object]],
    snapshots: list[SourceSnapshot],
    started_at: str,
) -> str:
    checkpoint_id = f"checkpoint-{scan_id}-{next_index}"
    save_checkpoint(
        path,
        CheckpointState(
            checkpoint_id=checkpoint_id,
            scan_id=scan_id,
            config_hash=config_hash,
            rule_set_version=_string(config.raw, "rule_set_version"),
            path_normalization_version=_string(
                config.raw, "path_normalization_version"
            ),
            next_index=next_index,
            source_snapshots=tuple(snapshots),
            payload={
                "records": records,
                "issues": issues,
                "started_at": started_at,
            },
        ),
    )
    return checkpoint_id


def _anchor_rank(name: str, priority: object) -> int:
    if not isinstance(priority, list):
        return 999
    lowered = name.casefold()
    for index, candidate in enumerate(priority):
        if isinstance(candidate, str) and candidate.casefold() == lowered:
            return index
    return len(priority) + 1


def _relative_to_scope(relative_path: str, prefix: str) -> str:
    if prefix and relative_path.startswith(prefix + "/"):
        return relative_path[len(prefix) + 1 :]
    return relative_path


def _unique_records(
    records: list[dict[str, object]], key: str
) -> list[dict[str, object]]:
    unique: dict[str, dict[str, object]] = {}
    for record in records:
        unique.setdefault(str(record[key]), record)
    return list(unique.values())


def _mapping(value: object, key: str) -> dict[str, object]:
    if isinstance(value, dict):
        nested = value.get(key)
    else:
        nested = None
    if not isinstance(nested, dict):
        raise PipelineError(f"CONFIG_INVALID: {key}")
    return nested


def _string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise PipelineError(f"CONFIG_INVALID: {key}")
    return item


def _string_list(value: dict[str, object], key: str) -> list[str]:
    item = value.get(key)
    if not isinstance(item, list) or not all(isinstance(entry, str) for entry in item):
        raise PipelineError(f"CONFIG_INVALID: {key}")
    return item


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PipelineError("CHECKPOINT_INCOMPATIBLE: payload list")
    return [dict(item) for item in value]


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _new_scan_id() -> str:
    return f"scan-{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"


def _find_compatible_scan_id(
    output_path: Path,
    *,
    config_hash: str,
    rule_set_version: str,
    path_normalization_version: str,
) -> str | None:
    staging_parent = output_path.parent / f".{output_path.name}.staging"
    if not staging_parent.is_dir():
        return None
    candidates: list[tuple[int, str]] = []
    for scan_directory in staging_parent.iterdir():
        checkpoint_path = scan_directory / "checkpoint.json"
        if not scan_directory.is_dir() or not checkpoint_path.is_file():
            continue
        try:
            raw = loads_strict(checkpoint_path.read_bytes())
            if not isinstance(raw, dict):
                continue
            scan_id = raw.get("scan_id")
            if (
                not isinstance(scan_id, str)
                or scan_id != scan_directory.name
                or raw.get("config_hash") != config_hash
                or raw.get("rule_set_version") != rule_set_version
                or raw.get("path_normalization_version")
                != path_normalization_version
            ):
                continue
            candidates.append((checkpoint_path.stat().st_mtime_ns, scan_id))
        except (CanonicalJsonError, OSError):
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[1]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _time_from_ns(value: int) -> str:
    return datetime.fromtimestamp(value / 1_000_000_000, UTC).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _media_code(value: object, extension: object) -> str:
    extension_codes = {
        ".docx": "APPLICATION_DOCX",
        ".xlsx": "APPLICATION_XLSX",
        ".pptx": "APPLICATION_PPTX",
        ".pdf": "APPLICATION_PDF",
    }
    if isinstance(extension, str) and extension in extension_codes:
        return extension_codes[extension]
    if not isinstance(value, str):
        return "UNKNOWN"
    normalized = "".join(
        character if character.isalnum() else "_" for character in value
    ).upper()
    return normalized[:64]


def _normalized_extension(relative_path: str) -> str:
    name = PurePosixPath(relative_path).name
    candidate = PurePosixPath(name).suffix.casefold()
    if re.fullmatch(r"\.[a-z0-9][a-z0-9._+-]{0,31}", candidate):
        return candidate
    if name.endswith("~"):
        candidate = PurePosixPath(name[:-1]).suffix.casefold()
        if re.fullmatch(r"\.[a-z0-9][a-z0-9._+-]{0,31}", candidate):
            return candidate
    return ""
