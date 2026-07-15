from __future__ import annotations

import hashlib

from thesis_ingest.canonical_json import dumps_bytes


def make_issue(
    *,
    scan_id: str,
    stage: str,
    error_code: str,
    severity: str,
    recoverable: bool,
    message: str,
    recommended_action: str,
    created_at: str,
    ingest_record_id: str | None = None,
    relative_path: str | None = None,
    issue_id: str | None = None,
) -> dict[str, object]:
    if issue_id is None:
        issue_id = "sha256:" + hashlib.sha256(
            dumps_bytes(
                {
                    "error_code": error_code,
                    "ingest_record_id": ingest_record_id,
                    "message": message,
                    "record_type": "INGEST_ISSUE",
                    "relative_path": relative_path,
                    "scan_id": scan_id,
                    "stage": stage,
                }
            )
        ).hexdigest()
    issue: dict[str, object] = {
        "schema_version": "0.1",
        "record_type": "INGEST_ISSUE",
        "issue_id": issue_id,
        "scan_id": scan_id,
        "stage": stage,
        "error_code": error_code,
        "severity": severity,
        "recoverable": recoverable,
        "message": message,
        "recommended_action": recommended_action,
        "created_at": created_at,
    }
    if ingest_record_id is not None:
        issue["ingest_record_id"] = ingest_record_id
    if relative_path is not None:
        issue["relative_path"] = relative_path
    return issue
