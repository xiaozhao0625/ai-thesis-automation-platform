from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath

from thesis_ingest.canonical_json import dumps_bytes
from thesis_ingest.config import RuleBundle


@dataclass(frozen=True)
class CandidateArtifact:
    ingest_record_id: str
    relative_path: str
    content_hash: str
    modified_at: str | None
    artifact_role: str
    ingest_decision: str
    parser_eligible: bool
    word_count: int | None
    page_count: int | None
    in_project_scope: bool


@dataclass(frozen=True)
class EngineeringRoot:
    root_path: str
    representative_ingest_record_id: str
    representative_content_hash: str
    representative_modified_at: str | None
    file_names: set[str]


@dataclass(frozen=True)
class CandidateSelection:
    record: dict[str, object] | None
    issue_records: list[dict[str, object]]


def evaluate_primary_documents(
    artifacts: list[CandidateArtifact],
    *,
    scan_id: str,
    scope_id: str,
    created_at: str,
    rules: RuleBundle,
) -> CandidateSelection:
    scoring = _scoring_document(rules)
    ineligible_roles = set(scoring["ineligible_roles"])
    eligible = [
        artifact
        for artifact in artifacts
        if artifact.ingest_decision == "ACCEPTED"
        and artifact.parser_eligible
        and artifact.artifact_role in {"PRIMARY_DOCUMENT", "EXISTING_DRAFT"}
        and artifact.artifact_role not in ineligible_roles
        and not _is_historical(artifact.relative_path)
    ]
    if not eligible:
        return _unresolved_issue(scan_id, scope_id, created_at, "PRIMARY_DOCUMENT")

    newest = max(
        (artifact.modified_at or "" for artifact in eligible),
        default="",
    )
    evaluations: list[dict[str, object]] = []
    for artifact in eligible:
        extension = PurePosixPath(artifact.relative_path).suffix.casefold()
        role_weight = float(scoring["role_weights"].get(artifact.artifact_role, 0))
        current_weight = (
            float(scoring["current_name_weight"])
            if any(
                token.casefold() in PurePosixPath(artifact.relative_path).name.casefold()
                for token in scoring["current_name_tokens"]
            )
            else 0.0
        )
        format_weight = float(scoring["format_weights"].get(extension, 0))
        word_weight = (
            float(scoring["word_count_weight"])
            if artifact.word_count is not None
            and artifact.word_count >= int(scoring["minimum_word_count"])
            else 0.0
        )
        newest_weight = (
            float(scoring["newest_mtime_weight"])
            if artifact.modified_at is not None and artifact.modified_at == newest
            else 0.0
        )
        scope_weight = (
            float(scoring["scope_weight"]) if artifact.in_project_scope else 0.0
        )
        features = {
            "ROLE_WEIGHT": role_weight,
            "CURRENT_NAME_WEIGHT": current_weight,
            "FORMAT_WEIGHT": format_weight,
            "WORD_COUNT_WEIGHT": word_weight,
            "NEWEST_MTIME_WEIGHT": newest_weight,
            "SCOPE_WEIGHT": scope_weight,
        }
        evaluation: dict[str, object] = {
            "ingest_record_id": artifact.ingest_record_id,
            "file_name": PurePosixPath(artifact.relative_path).name,
            "content_hash": artifact.content_hash,
            "modified_at": artifact.modified_at,
            "candidate_score": round(sum(features.values()), 6),
            "feature_values": features,
        }
        if artifact.page_count is not None:
            evaluation["page_count"] = artifact.page_count
        if artifact.word_count is not None:
            evaluation["word_count"] = artifact.word_count
        if artifact.page_count is not None or artifact.word_count is not None:
            evaluation["metadata_extractor"] = {
                "name": "safe-metadata-observation",
                "version": "0.1.0",
            }
        evaluations.append(evaluation)
    return _selection_from_evaluations(
        evaluations,
        scan_id=scan_id,
        scope_id=scope_id,
        selection_type="PRIMARY_DOCUMENT",
        created_at=created_at,
        rules=rules,
    )


def evaluate_engineering_roots(
    roots: list[EngineeringRoot],
    *,
    scan_id: str,
    scope_id: str,
    created_at: str,
    rules: RuleBundle,
) -> CandidateSelection:
    if not roots:
        return _unresolved_issue(
            scan_id, scope_id, created_at, "PRIMARY_ENGINEERING_ROOT"
        )
    scoring = _scoring_root(rules)
    weights = scoring["weights"]
    evaluations: list[dict[str, object]] = []
    for root in roots:
        names = {name.replace("\\", "/") for name in root.file_names}
        basenames = {PurePosixPath(name).name for name in names}
        lower_names = {name.casefold() for name in names}
        lower_basenames = {name.casefold() for name in basenames}
        source_count = sum(
            PurePosixPath(name).suffix.casefold()
            in {".c", ".cc", ".cpp", ".go", ".java", ".js", ".py", ".rs", ".ts"}
            for name in names
        )
        features = {
            "ANCHOR_WEIGHT": (
                float(weights["anchor"])
                if any(anchor.casefold() in lower_basenames for anchor in scoring["anchor_priority"])
                else 0.0
            ),
            "THREE_SOURCE_FILES_WEIGHT": (
                float(weights["three_source_files"]) if source_count >= 3 else 0.0
            ),
            "DEPENDENCY_OR_LOCK_WEIGHT": (
                float(weights["dependency_or_lock"])
                if lower_basenames
                & {
                    "requirements.txt",
                    "package-lock.json",
                    "package.json",
                    "poetry.lock",
                    "pom.xml",
                    "cargo.lock",
                    "go.mod",
                }
                else 0.0
            ),
            "TESTS_WEIGHT": (
                float(weights["tests"])
                if any(
                    name.startswith("tests/")
                    or "/tests/" in name
                    or PurePosixPath(name).name.startswith("test_")
                    for name in lower_names
                )
                else 0.0
            ),
            "MIGRATIONS_WEIGHT": (
                float(weights["migrations"])
                if any(
                    name.startswith("migrations/") or "/migrations/" in name
                    for name in lower_names
                )
                else 0.0
            ),
            "README_OR_START_WEIGHT": (
                float(weights["readme_or_start"])
                if lower_basenames & {"readme.md", "manage.py", "main.py", "app.py"}
                else 0.0
            ),
            "FRAMEWORK_CONFIG_WEIGHT": (
                float(weights["framework_config"])
                if lower_basenames
                & {"pyproject.toml", "manage.py", "package.json", "pom.xml"}
                else 0.0
            ),
        }
        evaluations.append(
            {
                "ingest_record_id": root.representative_ingest_record_id,
                "file_name": root.root_path,
                "content_hash": root.representative_content_hash,
                "modified_at": root.representative_modified_at,
                "candidate_score": round(sum(features.values()), 6),
                "feature_values": features,
            }
        )
    return _selection_from_evaluations(
        evaluations,
        scan_id=scan_id,
        scope_id=scope_id,
        selection_type="PRIMARY_ENGINEERING_ROOT",
        created_at=created_at,
        rules=rules,
    )


def _selection_from_evaluations(
    evaluations: list[dict[str, object]],
    *,
    scan_id: str,
    scope_id: str,
    selection_type: str,
    created_at: str,
    rules: RuleBundle,
) -> CandidateSelection:
    recommendation = _scoring_recommendation(rules)
    evaluations.sort(
        key=lambda item: (
            -float(item["candidate_score"]),
            str(item["ingest_record_id"]),
        )
    )
    top_score = float(evaluations[0]["candidate_score"])
    second_score = (
        float(evaluations[1]["candidate_score"]) if len(evaluations) > 1 else None
    )
    issue_records: list[dict[str, object]] = []
    if top_score < float(recommendation["minimum_top_score"]):
        status = "NO_RECOMMENDATION"
        reason = "TOP_SCORE_BELOW_THRESHOLD"
    elif second_score is not None and round(top_score - second_score, 6) <= float(
        recommendation["unique_gap_exclusive"]
    ):
        status = "TIED_REVIEW"
        reason = "TOP_SCORE_GAP_NOT_GREATER_THAN_THRESHOLD"
    else:
        status = "RECOMMENDED"
        reason = "UNIQUE_TOP_SCORE_ABOVE_THRESHOLD"

    candidate_id = _stable_id(
        {
            "candidate_scope_id": scope_id,
            "record_type": "PRIMARY_ARTIFACT_CANDIDATE",
            "scan_id": scan_id,
            "selection_type": selection_type,
        }
    )
    record: dict[str, object] = {
        "schema_version": "0.1",
        "record_type": "PRIMARY_ARTIFACT_CANDIDATE",
        "candidate_id": candidate_id,
        "scan_id": scan_id,
        "candidate_scope_id": scope_id,
        "selection_type": selection_type,
        "recommendation_status": status,
        "candidate_ingest_record_ids": [
            str(evaluation["ingest_record_id"]) for evaluation in evaluations
        ],
        "candidate_evaluations": evaluations,
        "recommendation_reasons": [reason],
        "comparison_metrics": [],
        "scoring_rule_version": rules.candidate_scoring_version,
        "requires_human_confirmation": True,
        "issue_refs": [],
        "created_at": created_at,
    }
    if status == "RECOMMENDED":
        record["recommended_ingest_record_id"] = evaluations[0]["ingest_record_id"]
        record["recommendation_score"] = top_score
    else:
        issue = _issue(
            scan_id,
            scope_id,
            (
                "PRIMARY_CANDIDATE_TIE"
                if status == "TIED_REVIEW"
                else "PROJECT_SCOPE_UNRESOLVED"
            ),
            created_at,
        )
        issue_records.append(issue)
        record["issue_refs"] = [issue["issue_id"]]
        if status == "TIED_REVIEW":
            tied = [
                evaluation
                for evaluation in evaluations
                if round(top_score - float(evaluation["candidate_score"]), 6)
                <= float(recommendation["unique_gap_exclusive"])
            ]
            record["tied_ingest_record_ids"] = [
                evaluation["ingest_record_id"] for evaluation in tied
            ]
            record["tied_score"] = top_score
    return CandidateSelection(record=record, issue_records=issue_records)


def _unresolved_issue(
    scan_id: str,
    scope_id: str,
    created_at: str,
    selection_type: str,
) -> CandidateSelection:
    return CandidateSelection(
        record=None,
        issue_records=[
            _issue(scan_id, scope_id, "PROJECT_SCOPE_UNRESOLVED", created_at)
            | {"selection_type": selection_type}
        ],
    )


def _issue(
    scan_id: str, scope_id: str, code: str, created_at: str
) -> dict[str, object]:
    return {
        "issue_id": _stable_id(
            {
                "code": code,
                "record_type": "INGEST_ISSUE",
                "scan_id": scan_id,
                "scope_id": scope_id,
            }
        ),
        "code": code,
        "created_at": created_at,
    }


def _stable_id(projection: object) -> str:
    return "sha256:" + hashlib.sha256(dumps_bytes(projection)).hexdigest()


def _scoring_document(rules: RuleBundle) -> dict[str, object]:
    return _scoring_section(rules, "document")


def _scoring_root(rules: RuleBundle) -> dict[str, object]:
    return _scoring_section(rules, "engineering_root")


def _scoring_recommendation(rules: RuleBundle) -> dict[str, object]:
    return _scoring_section(rules, "recommendation")


def _scoring_section(rules: RuleBundle, key: str) -> dict[str, object]:
    document = rules.documents["candidate-scoring.json"]
    if not isinstance(document, dict) or not isinstance(document.get(key), dict):
        raise ValueError(f"invalid candidate scoring section: {key}")
    return document[key]


def _is_historical(relative_path: str) -> bool:
    lowered = relative_path.casefold()
    return any(
        token in lowered
        for token in ("历史资料/", "历史论文/", "旧论文", "archive/")
    )
