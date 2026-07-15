from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib

from thesis_ingest.canonical_json import dumps_bytes


@dataclass(frozen=True)
class DedupRecord:
    ingest_record_id: str
    content_hash: str | None
    path_key: str
    pre_dedup_decision: str
    pre_dedup_parser_eligible: bool
    artifact_role: str
    ingest_decision: str | None = None
    parser_eligible: bool | None = None
    duplicate_group_id: str | None = None


@dataclass(frozen=True)
class DuplicateGroup:
    duplicate_group_id: str
    scan_id: str
    content_hash: str
    member_ingest_record_ids: tuple[str, ...]
    canonical_selection_status: str
    canonical_ingest_record_id: str | None

    def as_dict(self) -> dict[str, object]:
        selected = self.canonical_selection_status == "SELECTED"
        result: dict[str, object] = {
            "schema_version": "0.1",
            "record_type": "DUPLICATE_GROUP",
            "duplicate_group_id": self.duplicate_group_id,
            "scan_id": self.scan_id,
            "content_hash": self.content_hash,
            "member_ingest_record_ids": list(self.member_ingest_record_ids),
            "canonical_selection_status": self.canonical_selection_status,
            "canonical_selection_method": (
                "ACCEPTED_PARSER_ELIGIBLE_PATH_KEY_V1"
                if selected
                else "NO_ELIGIBLE_CANONICAL"
            ),
            "canonical_selection_reasons": [
                (
                    "ACCEPTED_PARSER_ELIGIBLE"
                    if selected
                    else "NO_ACCEPTED_PARSER_ELIGIBLE_MEMBER"
                )
            ],
            "selection_rule_version": "0.1.0",
        }
        if selected:
            result["canonical_ingest_record_id"] = self.canonical_ingest_record_id
        return result


@dataclass(frozen=True)
class DeduplicationResult:
    records: list[DedupRecord]
    groups: list[DuplicateGroup]


def deduplicate(
    records: list[DedupRecord],
    *,
    scan_id: str,
) -> DeduplicationResult:
    initialized = [
        replace(
            record,
            ingest_decision=record.pre_dedup_decision,
            parser_eligible=record.pre_dedup_parser_eligible,
        )
        for record in records
    ]
    indexed = {record.ingest_record_id: record for record in initialized}
    grouped: dict[str, list[DedupRecord]] = {}
    for record in initialized:
        if record.content_hash is not None:
            grouped.setdefault(record.content_hash, []).append(record)

    groups: list[DuplicateGroup] = []
    for content_hash in sorted(grouped):
        members = grouped[content_hash]
        if len(members) < 2:
            continue
        ordered_members = sorted(
            members,
            key=lambda member: (
                member.path_key.encode("utf-8"),
                member.ingest_record_id,
            ),
        )
        member_ids = tuple(member.ingest_record_id for member in ordered_members)
        group_id = _group_id(scan_id, content_hash)
        eligible = [
            member
            for member in members
            if member.pre_dedup_decision == "ACCEPTED"
            and member.pre_dedup_parser_eligible
        ]
        eligible.sort(
            key=lambda member: (
                member.artifact_role == "BACKUP",
                member.path_key.encode("utf-8"),
                member.ingest_record_id,
            )
        )
        canonical = eligible[0] if eligible else None
        if canonical is not None:
            for member in eligible:
                if member.ingest_record_id == canonical.ingest_record_id:
                    continue
                indexed[member.ingest_record_id] = replace(
                    indexed[member.ingest_record_id],
                    ingest_decision="DUPLICATE",
                    parser_eligible=False,
                    duplicate_group_id=group_id,
                )
        groups.append(
            DuplicateGroup(
                duplicate_group_id=group_id,
                scan_id=scan_id,
                content_hash=content_hash,
                member_ingest_record_ids=member_ids,
                canonical_selection_status=(
                    "SELECTED" if canonical is not None else "NO_ELIGIBLE_CANONICAL"
                ),
                canonical_ingest_record_id=(
                    canonical.ingest_record_id if canonical is not None else None
                ),
            )
        )
    output_records = [indexed[record.ingest_record_id] for record in initialized]
    return DeduplicationResult(records=output_records, groups=groups)


def _group_id(scan_id: str, content_hash: str) -> str:
    payload = dumps_bytes(
        {
            "content_hash": content_hash,
            "record_type": "DUPLICATE_GROUP",
            "scan_id": scan_id,
        }
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()
